"""Typed research state, Linux-direct HF verification and archive restoration.

The parent supplies its authenticated publication API and fixed-revision fetch
port. No credentials, provider requests, retries or Mac data relay live here.
"""

import json
import math
import shutil
import sys
import time
from pathlib import Path

REPO = "voxelshogi/voxelshogi-research-training-state-v1"


def require_linux():
    if sys.platform != "linux":
        raise ValueError("state transfer requires external Linux")


def prepare_archive(run, output):
    require_linux()
    from training.resume_archive import pack_run

    run, output = Path(run), Path(output)
    binding = json.loads((run / "run.json").read_text())["binding"]
    validate_pilot_binding(binding)
    manifest = pack_run(run, output, profile="research")
    config = binding["config"]
    progress = manifest["roles"]["latest"]["progress"]
    (output / "README.md").write_text(
        "---\nlicense: apache-2.0\n---\n# VoxelShogi M pilot resume state\n\n"
        "## Training and provenance\n"
        f"External-Linux CUDA visit-distribution pilot, source `{binding['source_commit']}`, "
        f"architecture `{config['architecture']['architecture']}`, seed {config['seed']}. "
        f"Actual saved step {progress['step']} of frozen {config['total_updates']} updates; "
        f"admission `{binding['contract']['admission_sha256']}`, full features/teacher decision binding `{binding['cache_sha256']}`. "
        "A partial state is not a completed pilot, independent seed or evidence of stronger play. Full run settings and environment are in config.json.\n\n"
        "## Resume contents\n"
        "Manifest-listed latest and, when present, fixed-val-selected best state; typed JSON and safetensors contain weights, optimizer, Python/NumPy/Torch/CUDA RNG, sampler progress, source/data/config/environment binding and training/validation events. This is a resume archive, not an inference model or public gameplay package.\n\n"
        "## Verification\n"
        "Packing validates owned checkpoint receipt hashes, typed fields and full scheduled history. Download all declared files at the published immutable Hub revision and verify each size/SHA-256 before restore_run(profile='research', expected_binding=config.binding). Actual full CUDA continuation parity requires a separate successful resume proof; publication alone is insufficient.\n\n"
        "## Access and license\n"
        "Apache-2.0, VoxelShogi contributors; retain LICENSE and source/input binding. Public repository with manual download approval and Community disabled. No provider keys, HF credentials, raw checkpoints with executable pickle, or raw position corpus are included.\n"
    )
    shutil.copyfile("LICENSE", output / "LICENSE")
    return manifest


def validate_pilot_binding(binding):
    from export.research_contract import architecture_config
    from training.research_visit_fit import VisitRunConfig, validate_binding

    validate_binding(binding)
    config = VisitRunConfig.from_value(binding["config"])
    if config.device != "cuda" or config.architecture != architecture_config(
        config.architecture.architecture
    ):
        raise ValueError("pilot state must bind actual M CUDA training")
    return config


def publish_restore(folder, control, restored, *, api, fetch, upload_budget, deadline):
    require_linux()
    if (
        type(deadline) not in (int, float)
        or not math.isfinite(deadline)
        or time.time() >= deadline
    ):
        raise InterruptedError("fixed state transfer deadline")
    from training.checkpoint import atomic_json
    from training.hub_release import plan_release, publish_release, verify_release
    from training.resume_archive import restore_run

    folder, control, restored = Path(folder), Path(control), Path(restored)
    if control.resolve().is_relative_to(folder.resolve()) or restored.exists():
        raise ValueError("use fresh owned transfer/restore directories")
    binding = json.loads((folder / "config.json").read_text())["binding"]
    validate_pilot_binding(binding)
    plan = plan_release(
        folder,
        repo_id=REPO,
        repo_type="model",
        license_id="apache-2.0",
        license_approved=True,
        source_commit=binding["source_commit"],
        artifact_role="research-training-state",
        state_publication_approved=True,
        expected_binding=binding,
    )
    # Existence means a previous upload may have happened. Reconnect and audit
    # its receipt; never resend and double-reserve after an observation failure.
    control.mkdir(parents=True, exist_ok=False)
    atomic_json(control / "publication-plan.json", plan)
    atomic_json(control / "publication-attempt.json", {"at": time.time()})
    stage = "publication"
    try:
        receipt = publish_release(
            folder, plan, api, execute=True, system="linux", upload_budget=upload_budget
        )
        atomic_json(control / "publication-receipt.json", receipt)
        stage = "verification"
        downloaded = control / "download"
        downloaded.mkdir()

        def fetch_owned(**kwargs):
            if time.time() >= deadline:
                raise InterruptedError("fixed all-file verification deadline")
            if (
                kwargs["repo_id"] != REPO
                or kwargs["repo_type"] != "model"
                or kwargs["revision"] != receipt["hub_commit"]
            ):
                raise ValueError("state fetch escaped fixed release")
            origin = Path(fetch(**kwargs))
            target = downloaded / kwargs["filename"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origin, target)
            return target

        receipt = verify_release(plan, receipt, api, fetch_owned, system="linux")
        atomic_json(control / "publication-receipt.json", receipt)
        if time.time() >= deadline:
            raise InterruptedError("fixed restore deadline")
        stage = "restoration"
        manifest = restore_run(
            downloaded, restored, expected_binding=binding, profile="research"
        )
        result = {
            "schema": "voxelshogi-research-pilot-state-transfer-v1",
            "receipt": receipt,
            "verified_files": len(plan["files"]),
            "restored": True,
            "progress": manifest["roles"]["latest"]["progress"],
            "scope": "Typed HF state all-file roundtrip and reconstruction only; continued CUDA numerical equality requires the separate resume-proof result.",
        }
        atomic_json(control / "complete.json", result)
        return result
    except BaseException as error:
        atomic_json(
            control / "failure.json",
            {"stage": stage, "error_type": type(error).__name__},
        )
        raise
