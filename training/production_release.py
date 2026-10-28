"""Assemble and publish validated production data without losing pilot configs."""

import argparse
import hashlib
import json
import math
import os
import platform
import re
import shutil
from pathlib import Path

from training.hub_release import (
    PublicationApi,
    create_release_repository,
    plan_release,
    publish_release,
    verify_release,
)
from training.rental_control import QUOTES, SKU

REPO = "voxelshogi/voxelshogi-synthetic-v1"
CONFIG_NAME = "production-64"


class PinnedParentApi:
    def __init__(self, api, parent):
        self.api, self.parent = api, parent

    def __getattr__(self, name):
        return getattr(self.api, name)

    def repo_info(self, **kwargs):
        info = self.api.repo_info(**kwargs)
        if not kwargs.get("revision") and info.sha != self.parent:
            raise ValueError("Hub parent changed before upload")
        return info


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(canonical(value) + "\n")
    temporary.replace(path)


def production_job(source_commit, *, hourly_usd, sku=SKU):
    if (
        not re.fullmatch(r"[0-9a-f]{40}", source_commit)
        or type(hourly_usd) not in (int, float)
        or not math.isfinite(hourly_usd)
        or not 0 < hourly_usd <= 1
        or sku not in QUOTES
    ):
        raise ValueError("source or rate differs from approved production quote")
    return {
        "schema": 1,
        "purpose": "production",
        "provider": "cloudrift",
        "approved": True,
        "approved_seconds": QUOTES[sku] - 4500,
        "hourly_usd": hourly_usd,
        "max_cost_usd": QUOTES[sku] / 3600,
        "workers": 4,
        "minimum_eligible_rows": 100000,
        "gpu_model": "rtx5090",
        "config": {
            "engine_commit": source_commit,
            "seed": 17,
            "games": 1800,
            "max_plies": 64,
            "sources": ["random", "rules", "search"],
            "initial": None,
            "max_depth": 2,
            "max_nodes": 10000,
            "table_capacity": 4096,
            "search_opening_plies": 16,
        },
    }


def validate_completed(output):
    from training.production import validate_job

    output = Path(output)
    job = json.loads((output / "job.json").read_text())
    validate_job(job, system="linux", ci=False)
    if job["purpose"] != "production":
        raise ValueError("only production output may use this release")
    report = json.loads((output / "report.json").read_text())
    source = job["config"]["engine_commit"]
    if (
        report.get("complete") is not True
        or report.get("regenerated_bytes_match") is not True
        or report.get("supervisor", {}).get("reason") != "completed"
    ):
        raise ValueError("generation, validation and regeneration must all complete")
    if (
        report["source_commit"] != source
        or report["context"]["source_commit"] != source
    ):
        raise ValueError("production source differs")
    validation = report["validation"]
    if validation["eligible_rows"] < 100000 or validation["eligible_teachers"] <= 0:
        raise ValueError("production has insufficient nonduplicate data or teachers")
    manifest = json.loads((output / "first/manifest.json").read_text())
    if manifest.get("complete") is not True or manifest["config"] != job["config"]:
        raise ValueError("production manifest differs from job")
    if (
        manifest.get("schema") != "voxelshogi-dataset-v1"
        or manifest.get("ruleset_id") != "voxelshogi-standard-v1"
    ):
        raise ValueError("production schema or ruleset differs")
    shards = manifest["shards"]
    names = [entry["file"] for entry in shards]
    if not all(re.fullmatch(r"game-[0-9]{6}\.parquet", name) for name in names) or len(
        set(names)
    ) != len(names):
        raise ValueError("production contains invalid shard paths")
    if (
        len(shards) != job["config"]["games"]
        or validation["games"] != len(shards)
        or validation["rows"] != sum(s["rows"] for s in shards)
    ):
        raise ValueError("production game/row count differs")
    if (
        validation["eligible_rows"] + validation["duplicates"] != validation["rows"]
        or sum(validation["eligible_sources"].values()) != validation["eligible_rows"]
        or sum(validation["eligible_splits"].values()) != validation["eligible_rows"]
    ):
        raise ValueError("production eligible counts differ")
    first = output / "first"
    if first.is_symlink():
        raise ValueError("production folder cannot be a symlink")
    actual = {}
    for path in first.iterdir():
        if (
            path.is_symlink()
            or not path.is_file()
            or path.name not in {*names, "manifest.json", ".voxelshogi-dataset-v1"}
        ):
            raise ValueError("unlisted production artifact")
        actual[path.name] = digest(path)
    if actual != report["files"] or any(
        actual.get(s["file"]) != s["sha256"] for s in shards
    ):
        raise ValueError("production file hashes differ")
    return job, report, manifest


def parquet_split(path):
    import pyarrow.parquet as pq

    splits = set(pq.read_table(path, columns=["split"]).column("split").to_pylist())
    if len(splits) != 1 or not splits <= {"train", "val", "test"}:
        raise ValueError("a game must remain in one valid split")
    return splits.pop()


def stage_release(
    output, previous, destination, previous_plan, *, split_for_file=parquet_split
):
    job, report, manifest = validate_completed(output)
    previous, destination = Path(previous), Path(destination)
    # Copy precisely the previously verified files, never a download cache/log.
    for file in previous_plan["files"]:
        path = previous / file["path"]
        if (
            path.is_symlink()
            or path.stat().st_size != file["bytes"]
            or digest(path) != file["sha256"]
        ):
            raise ValueError("previous release hash differs")
    destination.mkdir(exist_ok=False)
    for file in previous_plan["files"]:
        target = destination / file["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(previous / file["path"], target)
    index_data = json.loads((previous / "manifest.json").read_text())
    reports = json.loads((previous / "validation.json").read_text())["reports"]
    if CONFIG_NAME in index_data["configurations"]:
        raise ValueError("production config already exists; preserve its release")
    production = destination / CONFIG_NAME
    production.mkdir()
    for entry in manifest["shards"]:
        shutil.copyfile(
            Path(output) / "first" / entry["file"], production / entry["file"]
        )
    shutil.copyfile(Path(output) / "first/manifest.json", production / "manifest.json")
    save(
        production / "generation.json",
        {
            "config": job["config"],
            "workers": job["workers"],
            "source_commit": report["source_commit"],
        },
    )
    save(production / "validation.json", report)
    reports[CONFIG_NAME] = report
    index_data["schema"] = "voxelshogi-dataset-release-v1"
    index_data["source_commit"] = report["source_commit"]
    index_data["configurations"][CONFIG_NAME] = {
        "manifest": f"{CONFIG_NAME}/manifest.json",
        "manifest_sha256": digest(production / "manifest.json"),
        "validation": f"{CONFIG_NAME}/validation.json",
        "source_commit": report["source_commit"],
    }
    save(destination / "manifest.json", index_data)
    save(
        destination / "validation.json",
        {
            "schema": 1,
            "source_commit": report["source_commit"],
            "all_complete": True,
            "reports": reports,
        },
    )
    metadata = [
        "---",
        "license: cc-by-4.0",
        "pretty_name: VoxelShogi Synthetic v1",
        "tags:",
        "- voxelshogi",
        "- synthetic",
        "- shogi",
        "- game-ai",
        "configs:",
    ]
    table, origins, breakdowns = [], [], []
    for name in index_data["configurations"]:
        if not re.fullmatch(r"[a-z0-9-]+", name):
            raise ValueError("invalid config name")
        cm = json.loads((destination / name / "manifest.json").read_text())
        splits = {}
        for entry in cm["shards"]:
            path = destination / name / entry["file"]
            split = split_for_file(path)
            if split not in ("train", "val", "test"):
                raise ValueError("invalid source split")
            splits.setdefault(split, []).append(f"{name}/{entry['file']}")
        metadata += ["- config_name: " + name]
        if name == CONFIG_NAME:
            metadata += ["  default: true"]
        metadata += ["  data_files:"]
        for split, files in sorted(splits.items()):
            metadata += [
                "  - split: " + ("validation" if split == "val" else split),
                "    path:",
            ] + ["    - " + json.dumps(file) for file in files]
        counts = reports[name]["validation"]
        table.append(
            f"| {name} | {counts['games']} | {counts['rows']} | {counts['rows'] - counts['eligible_rows']} | {counts['eligible_rows']} | {counts['eligible_teachers']} |"
        )
        breakdowns.append(
            f"- `{name}`: nonduplicate sources {canonical(counts.get('eligible_sources', {}))}; "
            f"nonduplicate splits {canonical(counts.get('eligible_splits', {}))}."
        )
        origins.append(
            f"- `{name}`: source `{cm['config']['engine_commit']}`, seed {cm['config']['seed']}. See `{name}/generation.json`, `manifest.json` and `validation.json`."
        )
    settings = job["config"]
    generation_description = (
        f"Generated and fully replay-validated on CloudRift Linux with Python 3.14.9 and a pinned uv.lock. "
        f"Rust is the only rules implementation. Ruleset: voxelshogi-standard-v1; row schema: voxelshogi-dataset-v1. "
        f"Production uses {settings['games']:,} games, cycling sources {', '.join(settings['sources'])}, "
        f"at most {settings['max_plies']} plies, depth {settings['max_depth']} / {settings['max_nodes']:,} nodes, "
        f"TT {settings['table_capacity']:,}, {settings['search_opening_plies']} seeded opening plies and {job['workers']} workers. "
        "Actual counts above include early termination. Settings and source commits remain separate for historical pilots."
    )
    metadata += [
        "---",
        "",
        "# VoxelShogi Synthetic v1",
        "",
        "Self-generated standard single-king 9×9×9 shogi data for reproducible AI research. No third-party game records are included.",
        "",
        "| Config | Games | Rows | Excluded duplicate rows | Nonduplicate positions | Nonduplicate search teachers |",
        "|---|---:|---:|---:|---:|---:|",
        *table,
        "",
        *breakdowns,
        "",
        "## Generation and provenance",
        "",
        *origins,
        "",
        generation_description,
        "",
        "Limitations: configurations overlap and their eligible counts must not be added as independent samples. Production is truncated at 64 plies and does not provide natural win/loss labels for every game. Search scores use material/terminal units, not win probabilities; bounded search is not proof of optimal play. Random/rules moves are not best-move teachers. During the seeded opening, played_move can differ from the teacher best_move. Final truncated positions have no search teacher.",
        "",
        "Every game belongs to one split. HF validation corresponds to row split val. Exclude duplicate_of != null from fitting and evaluation; retain such rows only for replay. Fit best-move supervision only where teacher_valid is true and duplicate_of is null. Nonduplicate positions and usable search teachers are separate counts. Fix the Hub revision and training/test protocol before use.",
        "",
        "## Usage and schema",
        "",
        "After manual access approval, install the datasets client and load the production-64 config with datasets.load_dataset('voxelshogi/voxelshogi-synthetic-v1', 'production-64', revision='<the published Hub commit>', token=True). Replace the revision placeholder with the fixed release commit shown on the Hub. Pilots remain available as separate configs.",
        "",
        f"Field types and semantics: https://github.com/ayutaz/voxelshogi/blob/{report['source_commit']}/docs/M4_DATA_CONTRACT.md . Rows contain game_id/ply/source/split/ruleset_id, initial/history/vsfen/hash/side, legal_moves/legal_actions/in_check/finished/result, evaluation/teacher/teacher_valid, played_move/termination/duplicate_of. Apply the duplicate and teacher filters above. Do not treat truncated games as draws or limited search values as measured probabilities.",
        "",
        "## Verification",
        "",
        "All histories, legal moves, played actions, teachers and cross-game duplicates were fully validated. Production was fully regenerated in the same pinned environment and every Parquet/manifest hash matched. Root manifest.json indexes the independent configurations; each configuration retains its original manifest, generation settings and validation evidence. To reproduce, check out the recorded source with its lockfile on external Linux, use that config's generation.json and run generation plus full validation and full regeneration. Compare every byte/hash with its manifest and validation evidence. Timing/RSS observations are separate from deterministic data.",
        "",
        "## Access and license",
        "",
        "Public repository, gated=manual: request access on Hugging Face and download after human approval. Community discussions and pull requests are OFF. These synthetic data are CC-BY-4.0; see LICENSE. Attribution: ayutaz and VoxelShogi contributors, VoxelShogi Synthetic v1, with configuration source commit and release Hub revision. Code is separately Apache-2.0; future trained-model licensing is separate. No logs, credentials, intermediate files, ownership markers, third-party sources or duplicate regeneration copies are released.",
        "",
    ]
    (destination / "README.md").write_text("\n".join(metadata))
    return plan_release(
        destination,
        repo_id=REPO,
        repo_type="dataset",
        license_id="cc-by-4.0",
        license_approved=True,
        source_commit=report["source_commit"],
    )


def preflight_repository(api, previous_plan, expected_revision):
    if previous_plan["repo_id"] != REPO or previous_plan["repo_type"] != "dataset":
        raise ValueError("production destination differs")
    info = api.repo_info(repo_id=REPO, repo_type="dataset")
    if info.sha != expected_revision:
        raise ValueError("Hub parent changed before generation")
    prepared = create_release_repository(
        previous_plan, api, execute=True, system="linux"
    )
    if prepared.sha != expected_revision:
        raise ValueError("Hub parent changed during preflight")
    return {
        "repo_id": REPO,
        "private": prepared.private,
        "gated": prepared.gated,
        "community_disabled": True,
        "hub_parent": prepared.sha,
    }


def verify_downloaded(plan, receipt, api, download, destination):
    cached = Path(
        download(
            repo_id=plan["repo_id"],
            repo_type=plan["repo_type"],
            revision=receipt["hub_commit"],
            allow_patterns=[file["path"] for file in plan["files"]],
            local_dir=destination,
            max_workers=8,
        )
    )
    return verify_release(
        plan,
        receipt,
        api,
        lambda **kw: cached / kw["filename"],
        system="linux",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    job_parser = commands.add_parser("job")
    job_parser.add_argument("output", type=Path)
    job_parser.add_argument("--source", required=True)
    job_parser.add_argument("--hourly-usd", type=float, default=1)
    job_parser.add_argument("--sku", choices=tuple(QUOTES), default=SKU)
    for command in ("preflight", "publish"):
        release_parser = commands.add_parser(command)
        release_parser.add_argument("output", type=Path, help="Production output")
    args = parser.parse_args()
    if args.command == "job":
        save(
            args.output,
            production_job(args.source, hourly_usd=args.hourly_usd, sku=args.sku),
        )
        return
    if platform.system() != "Linux":
        parser.error("publish only from external Linux")
    from huggingface_hub import HfApi, snapshot_download
    from huggingface_hub.utils import build_hf_headers, get_session

    root = Path(__file__).resolve().parents[1]
    if not args.output.resolve().is_relative_to(root / "runs"):
        parser.error("production output must remain under runs/")
    token = os.environ.pop("HF_TOKEN")
    api = PublicationApi(
        HfApi(endpoint="https://huggingface.co", token=token),
        get_session(),
        build_hf_headers(token=token),
    )
    previous = json.loads(
        (root / "docs/experiments/m4-hf-pilot-release-2026-10-28.json").read_text()
    )
    base = args.output / "publication"
    base.mkdir(parents=True, exist_ok=True)
    if args.command == "preflight":
        account = api.whoami()
        if account.get("name") != "ayousanz" or not any(
            org.get("name") == "voxelshogi" for org in account.get("orgs", [])
        ):
            raise ValueError("HF account or organization differs")
        proof = preflight_repository(
            api, previous["plan"], previous["receipt"]["hub_commit"]
        )
        save(base / "preflight.json", proof)
        print(canonical(proof))
        return
    folder, plan_path, receipt_path = (
        base / "release",
        base / "plan.json",
        base / "receipt.json",
    )
    if plan_path.exists():
        plan = json.loads(plan_path.read_text())
    else:
        if (
            api.repo_info(repo_id=REPO, repo_type="dataset").sha
            != previous["receipt"]["hub_commit"]
        ):
            raise ValueError("Hub parent changed; do not overwrite another release")
        create_release_repository(previous["plan"], api, execute=True)
        old = base / "previous"
        snapshot_download(
            endpoint="https://huggingface.co",
            repo_id=REPO,
            repo_type="dataset",
            revision=previous["receipt"]["hub_commit"],
            allow_patterns=[f["path"] for f in previous["plan"]["files"]],
            local_dir=old,
            token=token,
        )
        plan = stage_release(args.output, old, folder, previous["plan"])
        save(plan_path, plan)
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
    else:
        parent = previous["receipt"]["hub_commit"]

        receipt = publish_release(
            folder, plan, PinnedParentApi(api, parent), execute=True
        )
        save(receipt_path, receipt)
    receipt = verify_downloaded(
        plan,
        receipt,
        api,
        lambda **kw: snapshot_download(
            endpoint="https://huggingface.co", token=token, **kw
        ),
        base / "verification-cache",
    )
    save(receipt_path, receipt)
    save(base / "complete.json", {"complete": True, "receipt": receipt, "plan": plan})
    print(
        canonical(
            {
                "complete": True,
                "hub_commit": receipt["hub_commit"],
                "files": len(plan["files"]),
            }
        )
    )


if __name__ == "__main__":
    main()
