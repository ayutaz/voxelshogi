"""Metadata-only opening of the already published S inference package.

Does not stage/download weights on the Mac. Linux must subsequently verify the
full immutable package with scripts/verify-public-s.mjs before web publication.
"""

import hashlib
import json
import re
from pathlib import Path

from training.hub_release import PUBLIC_S_PROFILE, PUBLIC_S_REPO, _canonical, _policy

ROOT = Path(__file__).resolve().parents[1]


def prepare_public_s_card(card):
    approval = json.loads((ROOT / "export/public-s-approval.json").read_text())
    if (
        approval["inference_repository"] != PUBLIC_S_REPO
        or approval["access_profile"] != PUBLIC_S_PROFILE
        or approval["gated"] is not False
        or approval["browser_download_approved"] is not True
        or approval["community_disabled"] is not True
    ):
        raise ValueError("explicit public S approval is required")
    encoded = card.encode("utf-8")
    if not 1 <= len(encoded) <= 8192 or not card.startswith(
        "---\nlicense: apache-2.0\n"
    ):
        raise ValueError("concise Apache-2.0 Model Card required")
    for title in (
        "Training and provenance",
        "Evaluation",
        "Inference",
        "Access and license",
    ):
        if not re.search(rf"^## {title}\n\n\S", card, re.MULTILINE):
            raise ValueError("complete concise Model Card required")
    previous = json.loads(
        (ROOT / "docs/experiments/m6-portable-release.json").read_text()
    )["publication"]
    plan = {**previous["plan"], "gated": False, "access_profile": PUBLIC_S_PROFILE}
    plan["files"] = [
        {
            "path": "README.md",
            "bytes": len(encoded),
            "sha256": hashlib.sha256(encoded).hexdigest(),
        }
        if f["path"] == "README.md"
        else dict(f)
        for f in plan["files"]
    ]
    _policy(plan)
    return plan, previous["receipt"]["hub_commit"]


def publish_public_s_card(card, api, *, execute=False):
    plan, parent = prepare_public_s_card(card)
    receipt = {
        "dry_run": not execute,
        "verified": False,
        "release_sha256": hashlib.sha256(_canonical(plan).encode()).hexdigest(),
    }
    if not execute:
        return plan, receipt
    destination = {"repo_id": PUBLIC_S_REPO, "repo_type": "model"}
    who = api.whoami()
    if who["name"] != "ayousanz" or not any(
        org["name"] == "voxelshogi" for org in who.get("orgs", [])
    ):
        raise ValueError("expected HF account/organization required")
    info = api.repo_info(**destination)
    if info.private or info.sha != parent:
        raise ValueError("public S base revision changed; review before updating")
    api.update_repo_settings(**destination, gated=False)
    api.disable_community(**destination)
    if (
        api.repo_info(**destination).gated is not False
        or api.community_disabled(**destination) is not True
    ):
        raise ValueError("ungated public S / Community OFF not confirmed")
    commit = api.commit_public_s_card(card=card.encode("utf-8"), parent_commit=parent)
    return plan, {
        **receipt,
        **destination,
        "hub_commit": commit,
        "metadata_only": True,
    }


def repair_public_s_card(card, api, failed_release):
    """One correction of our Card-only failure; all other files must be unchanged."""
    plan, original = prepare_public_s_card(card)
    receipt = failed_release["receipt"]
    if (
        failed_release["plan"] != plan
        or receipt.get("metadata_only") is not True
        or receipt.get("verified") is not False
        or receipt.get("dry_run") is not False
        or receipt.get("repo_id") != PUBLIC_S_REPO
        or receipt.get("metadata_retry", 0) != 0
        or receipt.get("release_sha256")
        != hashlib.sha256(_canonical(plan).encode()).hexdigest()
        or not re.fullmatch(r"[0-9a-f]{40}", receipt.get("hub_commit", ""))
    ):
        raise ValueError("one owned failed Card receipt required")
    who = api.whoami()
    if who["name"] != "ayousanz" or not any(
        org["name"] == "voxelshogi" for org in who.get("orgs", [])
    ):
        raise ValueError("expected HF account/organization required")
    destination = {"repo_id": PUBLIC_S_REPO, "repo_type": "model"}
    current = api.repo_info(**destination, files_metadata=True)
    baseline = api.repo_info(**destination, revision=original, files_metadata=True)

    def inventory(info):
        return {f.rfilename: (f.size, f.blob_id) for f in info.siblings}

    expected = {f["path"] for f in plan["files"]} | {".gitattributes"}
    if (
        current.private
        or current.gated is not False
        or current.sha != receipt["hub_commit"]
        or {f.rfilename for f in current.siblings} != expected
        or {f.rfilename for f in baseline.siblings} != expected
        or api.community_disabled(**destination) is not True
    ):
        raise ValueError(
            "failed metadata commit tree/settings changed; stop and review"
        )
    old, new = inventory(baseline), inventory(current)
    changed = {path for path in expected if old[path] != new[path]}
    restore = None
    if changed:
        if changed != {"fp32.onnx"}:
            raise ValueError("unrelated file changed; stop and review")
        broken = next(f for f in current.siblings if f.rfilename == "fp32.onnx")
        original_file = next(f for f in baseline.siblings if f.rfilename == "fp32.onnx")
        descriptor = next(f for f in plan["files"] if f["path"] == "fp32.onnx")
        if (
            broken.size != len(card.encode())
            or broken.lfs is None
            or broken.lfs.sha256 != hashlib.sha256(card.encode()).hexdigest()
            or original_file.size != descriptor["bytes"]
            or original_file.lfs is None
            or original_file.lfs.sha256 != descriptor["sha256"]
        ):
            raise ValueError(
                "only the exact misplaced Card may replace the original FP32"
            )
        restore = {"bytes": descriptor["bytes"], "sha256": descriptor["sha256"]}
    kwargs = {"card": card.encode(), "parent_commit": current.sha}
    if restore is not None:
        kwargs["restore_fp32"] = restore
    commit = api.commit_public_s_card(**kwargs)
    return plan, {
        **receipt,
        "hub_commit": commit,
        "previous_hub_commit": current.sha,
        "metadata_retry": 1,
        "restored_original_fp32": restore is not None,
    }
