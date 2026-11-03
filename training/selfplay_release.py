"""Generation-bound dataset/state publication with durable, fail-closed receipts.

Call after run_generations has returned and released its lock. Never use this
from on_generation: dataset packing acquires the same run lock.
"""

import argparse
import fcntl
import json
import shutil
import sys
from contextlib import contextmanager
from pathlib import Path

from training.checkpoint import atomic_json
from training.hub_release import (
    STATE_REPOS,
    plan_release,
    publish_release,
    verify_release,
)
from training.selfplay_dataset import validate_manifest
from training.selfplay_generations import _lock, validate_publication

SCHEMA = "voxelshogi-selfplay-release-v1"
DATASET_REPO = "voxelshogi/voxelshogi-selfplay-v1"


def _linux():
    if sys.platform != "linux":
        raise ValueError("selfplay publication requires external Linux")


def _read(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2 * 1024**2:
        raise ValueError("invalid release metadata")
    return json.loads(path.read_text())


@contextmanager
def _lease(stage):
    if stage.is_symlink() or not stage.is_dir():
        raise ValueError("owned release directory required")
    path = stage / ".publication.lock"
    if path.is_symlink():
        raise ValueError("symlink publication lock")
    with path.open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def _validate(stage, bundle):
    if set(bundle) != {"schema", "run", "plans"} or bundle["schema"] != SCHEMA:
        raise ValueError("invalid selfplay publication bundle")
    run, plans = bundle["run"], bundle["plans"]
    p = run["protocol"]
    data = _read(stage / "dataset/manifest.json")
    validate_manifest(data, expected_protocol=p)
    if data["run"] != run or not run["generations"]:
        raise ValueError("dataset run binding differs")
    record = run["generations"][-1]
    if len(run["publications"]) != record["generation"]:
        raise ValueError("exactly one unpublished generation required")
    if set(plans) != {"dataset", "state"}:
        raise ValueError("paired dataset/state plans required")
    state = _read(stage / "state/manifest.json")
    binding = state["binding"]
    contract = binding["contract"]
    if (
        binding != plans["state"].get("expected_binding")
        or binding["source_commit"] != p["source_commit"]
        or binding["cache_sha256"] != record["input_sha256"]
        or contract["generation"] != record["generation"]
        or contract["parent_model_sha256"] != record["parent_model_sha256"]
        or contract["architecture"] != p["architecture"]
        or state["roles"]["latest"]["progress"] != record["training_progress"]
        or record["training_progress"]["step"] < 1
    ):
        raise ValueError("state and generation binding/progress differ")
    for kind, repo, repo_type, license_id in (
        ("dataset", DATASET_REPO, "dataset", "cc-by-4.0"),
        ("state", STATE_REPOS["selfplay-training-state"], "model", "apache-2.0"),
    ):
        plan = plans[kind]
        if (
            plan["repo_id"] != repo
            or plan["repo_type"] != repo_type
            or plan["source_commit"] != p["source_commit"]
            or plan["license"] != license_id
            or plan.get("artifact_role", "artifacts")
            != ("selfplay-training-state" if kind == "state" else "artifacts")
        ):
            raise ValueError("generation publication destination/source differs")
        current = plan_release(
            stage / kind,
            repo_id=repo,
            repo_type=repo_type,
            license_id=license_id,
            license_approved=plan["license_approved"],
            source_commit=p["source_commit"],
            artifact_role=plan.get("artifact_role", "artifacts"),
            state_publication_approved=plan.get("state_publication_approved", False),
            expected_binding=plan.get("expected_binding"),
        )
        if current != plan:
            raise ValueError("staged release changed since review")
    return record


def stage_generation(run_dir, stage, *, protocol, dataset_license):
    _linux()
    from training.resume_archive import pack_run
    from training.selfplay_dataset import pack_dataset

    run_dir, stage = Path(run_dir), Path(stage)
    stage.mkdir(parents=True, exist_ok=False)
    m = pack_dataset(run_dir, stage / "dataset", expected_protocol=protocol)
    run = m["run"]
    if (
        not run["generations"]
        or len(run["publications"]) != len(run["generations"]) - 1
    ):
        raise ValueError("exactly one unpublished generation required")
    record = run["generations"][-1]
    training = run_dir / f"generation-{record['generation']:03d}/training"
    state = pack_run(training, stage / "state", profile="selfplay")
    shutil.copyfile(dataset_license, stage / "dataset/LICENSE")
    root = Path(__file__).resolve().parents[1]
    shutil.copyfile(root / "LICENSE", stage / "state/LICENSE")
    (stage / "state/README.md").write_text(
        "---\nlicense: apache-2.0\n---\n# VoxelShogi selfplay training state\n\n"
        "## Training and provenance\n"
        f"Source `{protocol['source_commit']}`; generation {record['generation']}. "
        f"Parent `{record['parent_model_sha256']}`; child `{record['model_sha256']}`. "
        f"Training input `{record['input_sha256']}`. "
        "The exact configuration and environment are in manifest.json binding.\n\n"
        "## Resume contents\n"
        "Latest model, optimizer, RNG and training progress, encoded as typed JSON "
        "and safetensors. No pickle or raw logs. This generation has completed its "
        "fixed epochs; subsequent generations create new optimizers. Replay and "
        "the frozen protocol are published separately in the paired dataset.\n\n"
        "## Verification\n"
        f"Completed progress: `{json.dumps(record['training_progress'], sort_keys=True)}`. "
        "The archive manifest binds every payload file by bytes and SHA-256. "
        "HF transfer is proven only by a separately verified fixed-revision receipt. "
        "This card does not establish playing-strength improvement.\n\n"
        "## Access and license\n"
        "Apache-2.0; Copyright 2026 ayutaz. Public repository with manual download "
        "approval; Community disabled. Use training.resume_archive.restore_run "
        "with profile=selfplay on external Linux and the expected binding.\n"
    )
    plans = {
        "dataset": plan_release(
            stage / "dataset",
            repo_id=DATASET_REPO,
            repo_type="dataset",
            license_id="cc-by-4.0",
            license_approved=True,
            source_commit=protocol["source_commit"],
        ),
        "state": plan_release(
            stage / "state",
            repo_id=STATE_REPOS["selfplay-training-state"],
            repo_type="model",
            license_id="apache-2.0",
            license_approved=True,
            source_commit=protocol["source_commit"],
            artifact_role="selfplay-training-state",
            state_publication_approved=True,
            expected_binding=state["binding"],
        ),
    }
    bundle = {"schema": SCHEMA, "run": run, "plans": plans}
    _validate(stage, bundle)
    atomic_json(stage / "bundle.json", bundle)
    return bundle


def publish_staged(run_dir, stage, api, fetch, *, upload_budget):
    _linux()
    run_dir, stage = Path(run_dir), Path(stage)
    with _lease(stage):
        bundle = _read(stage / "bundle.json")
        record = _validate(stage, bundle)
        run_path = run_dir / "run.json"
        before = _read(run_path)
        expected = bundle["run"]
        # An interrupted caller may already have committed this exact pair.
        already = json.loads(json.dumps(expected))
        pair_path = stage / "pair.json"
        if pair_path.exists():
            pair = _read(pair_path)
            validate_publication(pair)
            already["publications"].append({"generation": record["generation"], **pair})
        if before != expected and (not pair_path.exists() or before != already):
            raise ValueError("generation run changed before publication")
        pair = {}
        for kind in ("dataset", "state"):
            plan = bundle["plans"][kind]
            receipt_path = stage / f"{kind}-receipt.json"
            attempted = stage / f"{kind}-attempt.json"
            if receipt_path.exists():
                receipt = _read(receipt_path)
            else:
                if attempted.exists():
                    raise ValueError("unknown upload outcome: audit before resending")
                atomic_json(attempted, {"submitted": True})
                receipt = publish_release(
                    stage / kind,
                    plan,
                    api,
                    execute=True,
                    upload_budget=upload_budget,
                )
                atomic_json(receipt_path, receipt)
            # Recheck all remote bytes even when a previous receipt says verified.
            receipt = verify_release(plan, receipt, api, fetch)
            atomic_json(receipt_path, receipt)
            pair[kind] = receipt
        validate_publication(pair)
        atomic_json(pair_path, pair)
        with _lock(run_dir):
            current = _read(run_path)
            after = json.loads(json.dumps(expected))
            after["publications"].append({"generation": record["generation"], **pair})
            if current != expected and current != after:
                raise ValueError("generation run changed during publication")
            atomic_json(run_path, after)
        return pair


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("stage", "publish"))
    parser.add_argument("run", type=Path)
    parser.add_argument("stage", type=Path)
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--dataset-license", type=Path)
    parser.add_argument("--upload-budget", type=Path)
    args = parser.parse_args()
    _linux()
    if args.command == "stage":
        if args.protocol is None or args.dataset_license is None:
            parser.error("stage requires --protocol and --dataset-license")
        result = stage_generation(
            args.run,
            args.stage,
            protocol=_read(args.protocol),
            dataset_license=args.dataset_license,
        )
    else:
        if args.upload_budget is None:
            parser.error("publish requires the shared --upload-budget")
        from huggingface_hub import HfApi, hf_hub_download
        from huggingface_hub.utils import build_hf_headers, get_session

        from training.hub_release import PublicationApi

        api = PublicationApi(
            HfApi(endpoint="https://huggingface.co"),
            get_session(),
            build_hf_headers(token=True),
        )
        result = publish_staged(
            args.run, args.stage, api, hf_hub_download, upload_budget=args.upload_budget
        )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
