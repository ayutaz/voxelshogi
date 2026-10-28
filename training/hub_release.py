"""Explicit, hash-pinned Hub releases from external Linux hosts."""

import argparse
import hashlib
import json
import platform
import re
from pathlib import Path


class PublicationApi:
    """SDK adapter for the Hub community settings not exposed by HfApi."""

    def __init__(self, api, session, headers):
        self.api, self.session, self.headers = api, session, headers

    def __getattr__(self, name):
        return getattr(self.api, name)

    def _url(self, repo_id, repo_type):
        return f"https://huggingface.co/api/{repo_type}s/{repo_id}"

    def disable_community(self, *, repo_id, repo_type):
        response = self.session.put(
            self._url(repo_id, repo_type) + "/settings",
            headers=self.headers,
            json={"discussionsDisabled": True},
            timeout=30,
        )
        response.raise_for_status()

    def community_disabled(self, *, repo_id, repo_type):
        response = self.session.get(
            self._url(repo_id, repo_type) + "/discussions",
            headers=self.headers,
            timeout=30,
        )
        if (
            response.status_code == 403
            and response.json().get("error") == "Discussions are disabled for this repo"
        ):
            return True
        response.raise_for_status()
        return False


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _policy(plan):
    if not re.fullmatch(r"voxelshogi/[A-Za-z0-9][A-Za-z0-9._-]*", plan["repo_id"]):
        raise ValueError("release destination must be voxelshogi/NAME")
    if plan["repo_type"] not in ("model", "dataset"):
        raise ValueError("release type must be model or dataset")
    if plan["private"] is not False or plan["gated"] != "manual":
        raise ValueError(
            "release requires a public repository with manual access gating"
        )
    if plan["license_approved"] is not True or not re.fullmatch(
        r"[a-z0-9][a-z0-9.-]+", plan["license"]
    ):
        raise ValueError("artifact license approval is required")
    if not re.fullmatch(r"[0-9a-f]{40}", plan["source_commit"]):
        raise ValueError("release requires an immutable source commit")


def _inventory(folder, repo_type):
    folder = Path(folder)
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("release folder must be a real directory")
    allowed_metadata = {
        "README.md",
        "LICENSE",
        "NOTICE",
        "manifest.json",
        "validation.json",
        "config.json",
        "generation.json",
        "model-card.json",
    }
    files = []
    for path in sorted(folder.rglob("*")):
        relative = path.relative_to(folder)
        if path.is_symlink() or any(part.startswith(".") for part in relative.parts):
            raise ValueError("hidden files and symlinks are not release artifacts")
        if path.is_dir():
            continue
        allowed = (
            path.name in allowed_metadata
            or (repo_type == "dataset" and path.suffix == ".parquet")
            or (
                repo_type == "model"
                and (
                    path.suffix in (".onnx", ".safetensors")
                    or path.name.endswith(".onnx.data")
                )
            )
        )
        if not allowed:
            raise ValueError(f"unexpected release artifact: {relative}")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        files.append(
            {
                "path": relative.as_posix(),
                "bytes": path.stat().st_size,
                "sha256": digest.hexdigest(),
            }
        )
    names = {f["path"] for f in files}
    if not {"README.md", "LICENSE"} <= names:
        raise ValueError("release requires a card and license file")
    suffix = ".parquet" if repo_type == "dataset" else (".onnx", ".safetensors")
    if not any(name.endswith(suffix) for name in names):
        raise ValueError("release has no data or model artifacts")
    if repo_type == "dataset" and not {"manifest.json", "validation.json"} <= names:
        raise ValueError("dataset requires manifest and validation evidence")
    return files


def plan_release(
    folder, *, repo_id, repo_type, license_id, license_approved, source_commit
):
    plan = {
        "schema": 1,
        "repo_id": repo_id,
        "repo_type": repo_type,
        "private": False,
        "gated": "manual",
        "license": license_id,
        "license_approved": license_approved,
        "source_commit": source_commit,
    }
    _policy(plan)
    card = (Path(folder) / "README.md").read_text()
    if not re.search(rf"(?m)^license:\s*{re.escape(license_id)}\s*$", card):
        raise ValueError("card license differs from approved license")
    if repo_type == "dataset":
        for title in (
            "Generation and provenance",
            "Usage and schema",
            "Verification",
            "Access and license",
        ):
            section = re.search(
                rf"^## {re.escape(title)}[ \t]*\n(.*?)(?=^## |\Z)",
                card,
                re.MULTILINE | re.DOTALL,
            )
            if section is None or not section.group(1).strip():
                raise ValueError(f"Dataset Card requires a populated section: {title}")
    plan["files"] = _inventory(folder, repo_type)
    return plan


def publish_release(folder, plan, api, *, execute=False, system=None):
    _policy(plan)
    current = plan_release(
        folder,
        repo_id=plan["repo_id"],
        repo_type=plan["repo_type"],
        license_id=plan["license"],
        license_approved=plan["license_approved"],
        source_commit=plan["source_commit"],
    )
    if current != plan:
        raise ValueError("release artifacts changed since review")
    receipt = {
        "dry_run": not execute,
        "release_sha256": hashlib.sha256(_canonical(plan).encode()).hexdigest(),
        "verified": False,
    }
    if not execute:
        return receipt
    info = create_release_repository(plan, api, execute=True, system=system)
    destination = {"repo_id": plan["repo_id"], "repo_type": plan["repo_type"]}
    commit = api.upload_folder(
        **destination,
        folder_path=str(folder),
        allow_patterns=[f["path"] for f in plan["files"]],
        parent_commit=info.sha,
        commit_message=f"Publish verified artifacts from {plan['source_commit'][:12]}",
    )
    receipt.update(
        hub_commit=commit.oid, repo_id=plan["repo_id"], repo_type=plan["repo_type"]
    )
    return receipt


def create_release_repository(plan, api, *, execute=False, system=None):
    _policy(plan)
    if not execute:
        return {"dry_run": True, "repo_id": plan["repo_id"]}
    if (system or platform.system().lower()) != "linux":
        raise ValueError("publish from external Linux; do not stage datasets on Mac")
    destination = {"repo_id": plan["repo_id"], "repo_type": plan["repo_type"]}
    if not api.repo_exists(**destination):
        api.create_repo(**destination, private=False)
    info = api.repo_info(**destination)
    if info.private:
        raise ValueError("refusing to expose an existing private repository")
    api.update_repo_settings(**destination, gated="manual")
    api.disable_community(**destination)
    if api.community_disabled(**destination) is not True:
        raise ValueError("Community OFF has not been confirmed")
    info = api.repo_info(**destination)
    if info.private or info.gated != "manual":
        raise ValueError("public/manual Hub settings have not been confirmed")
    return info


def verify_release(plan, receipt, api, fetch, *, system=None):
    _policy(plan)
    if (system or platform.system().lower()) != "linux":
        raise ValueError("verify Hub artifacts on external Linux, not Mac")
    if any(receipt[k] != plan[k] for k in ("repo_id", "repo_type")):
        raise ValueError("receipt destination mismatch")
    if (
        receipt["release_sha256"]
        != hashlib.sha256(_canonical(plan).encode()).hexdigest()
    ):
        raise ValueError("receipt release hash mismatch")
    destination = {
        "repo_id": plan["repo_id"],
        "repo_type": plan["repo_type"],
        "revision": receipt["hub_commit"],
    }
    info = api.repo_info(**destination)
    if info.private or info.gated != "manual" or info.sha != receipt["hub_commit"]:
        raise ValueError("Hub settings or immutable revision mismatch")
    if (
        api.community_disabled(repo_id=plan["repo_id"], repo_type=plan["repo_type"])
        is not True
    ):
        raise ValueError("Community OFF has not been confirmed")
    for file in plan["files"]:
        path = Path(fetch(**destination, filename=file["path"]))
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        if path.stat().st_size != file["bytes"] or digest.hexdigest() != file["sha256"]:
            raise ValueError(f"Hub file hash mismatch: {file['path']}")
    return {**receipt, "verified": True, "community_disabled": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--create-repo", action="store_true")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    api = None
    if args.execute:
        from huggingface_hub import HfApi
        from huggingface_hub.utils import build_hf_headers, get_session

        api = PublicationApi(
            HfApi(endpoint="https://huggingface.co"),
            get_session(),
            build_hf_headers(token=True),
        )
    if args.create_repo:
        info = create_release_repository(plan, api, execute=args.execute)
        receipt = {
            "repo_id": plan["repo_id"],
            "dry_run": not args.execute,
            "gated": info.gated if args.execute else "manual",
        }
    else:
        receipt = publish_release(args.folder, plan, api, execute=args.execute)
        if args.execute:
            if args.receipt:
                args.receipt.write_text(_canonical(receipt) + "\n")
            from huggingface_hub import hf_hub_download

            receipt = verify_release(plan, receipt, api, hf_hub_download)
    if args.receipt:
        args.receipt.write_text(_canonical(receipt) + "\n")
    print(_canonical(receipt))


if __name__ == "__main__":
    main()
