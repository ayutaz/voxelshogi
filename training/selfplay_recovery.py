"""Recover a generation boundary from paired, immutable HF releases on Linux."""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path, PurePosixPath

from training.checkpoint import atomic_json
from training.feature_cache import file_hash
from training.hub_release import STATE_REPOS, _policy, verify_release
from training.selfplay_generations import (
    _protection,
    validate_protocol,
    validate_publication,
)
from training.selfplay_release import DATASET_REPO, SCHEMA, _lease, _read, _validate


def validate_releases(releases, protocol):
    validate_protocol(protocol)
    if type(releases) is not list or not 1 <= len(releases) <= protocol["generations"]:
        raise ValueError("all committed generation releases are required")
    previous = []
    for i, release in enumerate(releases):
        if type(release) is not dict or set(release) != {"bundle", "pair"}:
            raise ValueError("expected paired release descriptor")
        bundle, pair = release["bundle"], release["pair"]
        if set(bundle) != {"schema", "run", "plans"} or bundle["schema"] != SCHEMA:
            raise ValueError("invalid generation release bundle")
        run = bundle["run"]
        if (
            run["protocol"] != protocol
            or len(run["generations"]) != i + 1
            or run["generations"][:-1] != previous
            or len(run["publications"]) != i
            or run["publications"]
            != [{"generation": j, **releases[j]["pair"]} for j in range(i)]
            or run["generations"][-1]["generation"] != i
        ):
            raise ValueError("release protocol, order or publication lineage differs")
        validate_publication(pair)
        if set(bundle["plans"]) != {"dataset", "state"}:
            raise ValueError("both generation release plans required")
        for kind, repo, repo_type in (
            ("dataset", DATASET_REPO, "dataset"),
            ("state", STATE_REPOS["selfplay-training-state"], "model"),
        ):
            plan = bundle["plans"][kind]
            _policy(plan)
            if (
                plan["repo_id"] != repo
                or plan["repo_type"] != repo_type
                or plan["source_commit"] != protocol["source_commit"]
                or pair[kind]["repo_id"] != repo
                or pair[kind]["repo_type"] != repo_type
            ):
                raise ValueError("recovery release destination/source differs")
            names = []
            for entry in plan["files"]:
                name = entry["path"]
                path = PurePosixPath(name)
                if (
                    not isinstance(name, str)
                    or path.is_absolute()
                    or path.as_posix() != name
                    or any(p in ("..", ".") or p.startswith(".") for p in path.parts)
                    or "\\" in name
                    or not path.parts
                    or type(entry["bytes"]) is not int
                    or entry["bytes"] <= 0
                ):
                    raise ValueError("unsafe recovery file descriptor")
                names.append(name)
            if (
                not 1 <= len(names) <= 100
                or len(set(names)) != len(names)
                or sum(entry["bytes"] for entry in plan["files"]) > 1024**3
            ):
                raise ValueError("invalid recovery inventory size")
        previous = run["generations"]


def recover_generations(
    releases, output, workspace, api, fetch, *, protocol, base_model, protected_inputs
):
    if sys.platform != "linux":
        raise ValueError("generation recovery requires external Linux")
    validate_releases(releases, protocol)
    _protection(protected_inputs, protocol)
    base_model, output, workspace = Path(base_model), Path(output), Path(workspace)
    if (
        base_model.is_symlink()
        or file_hash(base_model) != protocol["base_model_sha256"]
    ):
        raise ValueError("recovery base model hash differs")
    if output.exists() or output.is_symlink():
        raise ValueError("recovery requires a new output directory")
    workspace.mkdir(parents=True, exist_ok=False)
    with _lease(workspace):
        import torch

        from export.model import make_model
        from training.checkpoint import checkpoint_receipt
        from training.resume_archive import restore_run
        from training.selfplay_dataset import restore_dataset
        from training.selfplay_generations import _export

        models, training_dirs, verified = {}, {}, []
        for i, release in enumerate(releases):
            stage = workspace / f"release-{i:03d}"
            stage.mkdir()
            bundle, pair = release["bundle"], {}
            for kind in ("dataset", "state"):
                plan, receipt = bundle["plans"][kind], release["pair"][kind]
                pair[kind] = verify_release(plan, receipt, api, fetch)
                folder = stage / kind
                folder.mkdir()
                for entry in plan["files"]:
                    source = Path(
                        fetch(
                            repo_id=plan["repo_id"],
                            repo_type=plan["repo_type"],
                            revision=receipt["hub_commit"],
                            filename=entry["path"],
                        )
                    )
                    target = folder / entry["path"]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
            record = _validate(stage, bundle)
            if pair != release["pair"]:
                raise ValueError("recovery receipts differ after remote verification")
            binding = bundle["plans"]["state"]["expected_binding"]
            training_dir = workspace / f"training-{i:03d}"
            restore_run(
                stage / "state",
                training_dir,
                expected_binding=binding,
                profile="selfplay",
            )
            path, checkpoint = checkpoint_receipt(
                training_dir / "checkpoints", binding=binding
            )
            payload = torch.load(path, map_location="cpu", weights_only=True)
            if payload["progress"] != record["training_progress"]:
                raise ValueError("restored learning progress differs")
            model = make_model(0)
            model.load_state_dict(payload["model"], strict=True)
            model_path = workspace / f"model-{i:03d}.safetensors"
            if _export(model, model_path) != record["model_sha256"]:
                raise ValueError("restored child model hash differs")
            del model, payload, checkpoint
            models[i], training_dirs[i] = model_path, training_dir
            verified.append({"generation": i, **pair})
        temporary = workspace / "reconstructed"
        latest = workspace / f"release-{len(releases) - 1:03d}/dataset"
        restore_dataset(latest, temporary, expected_protocol=protocol, models=models)
        for i, directory in training_dirs.items():
            shutil.copytree(directory, temporary / f"generation-{i:03d}/training")
        run = _read(temporary / "run.json")
        run["publications"] = verified
        atomic_json(temporary / "run.json", run)
        report = {
            "schema": "voxelshogi-selfplay-recovery-v1",
            "verified": True,
            "run_id": run["run_id"],
            "generations_restored": len(releases),
            "model_sha256": [r["model_sha256"] for r in run["generations"]],
            "publications": verified,
            "scope": "HF hashes, decoded learning states, child models and Rust replay; physical VM identity must be recorded separately",
        }
        atomic_json(temporary / "recovery.json", report)
        _protection(protected_inputs, protocol)
        if file_hash(base_model) != protocol["base_model_sha256"] or output.exists():
            raise ValueError("recovery inputs/destination changed")
        output.parent.mkdir(parents=True, exist_ok=True)
        os.rename(temporary, output)
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("releases", type=Path)
    parser.add_argument("protocol", type=Path)
    parser.add_argument("base_model", type=Path)
    parser.add_argument("protected_inputs", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("workspace", type=Path)
    args = parser.parse_args()
    if sys.platform != "linux":
        parser.error("recovery requires external Linux")
    from huggingface_hub import HfApi, hf_hub_download
    from huggingface_hub.utils import build_hf_headers, get_session

    from training.hub_release import PublicationApi

    api = PublicationApi(
        HfApi(endpoint="https://huggingface.co"),
        get_session(),
        build_hf_headers(token=True),
    )
    report = recover_generations(
        _read(args.releases),
        args.output,
        args.workspace,
        api,
        hf_hub_download,
        protocol=_read(args.protocol),
        base_model=args.base_model,
        protected_inputs=args.protected_inputs,
    )
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
