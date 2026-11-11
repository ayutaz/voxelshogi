"""External-Linux two-pilot job: fixed input bytes, CUDA cycles and state ledger.

No provider API or rental lives here. The owner controller supplies the frozen
source/workload/absolute deadlines after CI and hardware admission, then must
collect the small records and updated ledger before retiring its owned host.
"""

import argparse
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from infrastructure.research.pilot.attempt import validate_inputs
from training.checkpoint import atomic_json
from training.evaluation_v2 import fingerprint
from training.feature_cache import file_hash
from training.hub_release import _policy, plan_release, verify_release
from training.state_upload_budget import upload_budget_limit

LABELS = ("selfplay", "protection", "screen", "diagnosis")
BASE = "runs/p6/research-pilot"
DIAGNOSIS_FILES = [
    "LICENSE",
    "NOTICE",
    "README.md",
    "admission.parquet",
    "config.json",
    "manifest.json",
    "validation.json",
]


def require_linux():
    if sys.platform != "linux":
        raise ValueError("pilot job requires external Linux")


def validate_bundle(bundle):
    if "plan" not in bundle:
        receipt, recipe = bundle["receipt"], bundle["reconstruct"]
        policy = {
            "schema": 1,
            "repo_id": "voxelshogi/voxelshogi-research-pilot-admission-v1",
            "repo_type": "dataset",
            "private": False,
            "gated": "manual",
            "license": "cc-by-4.0",
            "license_approved": True,
            "source_commit": recipe["source_commit"],
        }
        _policy(policy)
        if (
            set(bundle) != {"receipt", "reconstruct"}
            or set(recipe) != {"source_commit", "license", "files"}
            or recipe["files"] != DIAGNOSIS_FILES
            or recipe["license"] != "cc-by-4.0"
            or receipt["repo_id"] != policy["repo_id"]
            or receipt["repo_type"] != "dataset"
            or re.fullmatch(r"[0-9a-f]{40}", str(receipt["hub_commit"])) is None
            or re.fullmatch(r"[0-9a-f]{64}", str(receipt["release_sha256"])) is None
            or receipt.get("verified") is not True
            or receipt.get("community_disabled") is not True
            or receipt.get("dry_run") is not False
        ):
            raise ValueError(
                "fixed diagnosis receipt and complete reconstruction recipe required"
            )
        return
    plan, receipt = bundle["plan"], bundle["receipt"]
    _policy(plan)
    if (
        plan["repo_type"] != "dataset"
        or receipt["repo_id"] != plan["repo_id"]
        or receipt["repo_type"] != "dataset"
        or receipt["release_sha256"] != fingerprint(plan)
        or re.fullmatch(r"[0-9a-f]{40}", str(receipt["hub_commit"])) is None
        or receipt.get("verified") is not True
        or receipt.get("community_disabled") is not True
        or receipt.get("dry_run") is not False
        or not plan["files"]
    ):
        raise ValueError("fixed verified dataset release required")
    seen = set()
    for entry in plan["files"]:
        name = Path(entry["path"])
        if (
            not name.parts
            or name.is_absolute()
            or ".." in name.parts
            or entry["path"] in seen
        ):
            raise ValueError("input release file escaped owned destination")
        seen.add(entry["path"])


def validate_job(value, *, now):
    if (
        type(value) is not dict
        or set(value)
        != {
            "schema",
            "source_commit",
            "base",
            "inputs",
            "split_step",
            "compute_deadline",
            "transfer_deadline",
            "selfplay_protocol",
            "state_upload_budget_sha256",
            "input_bundles",
            "maximum_owned_rss_bytes",
        }
        or value["schema"] != "voxelshogi-research-pilot-job-v1"
        or value["base"] != BASE
        or type(value["inputs"]) is not list
        or len(value["inputs"]) != 2
        or type(value["selfplay_protocol"]) is not dict
        or re.fullmatch(r"[0-9a-f]{64}", str(value["state_upload_budget_sha256"]))
        is None
        or type(value["split_step"]) is not int
        or type(value["maximum_owned_rss_bytes"]) is not int
        or not 1024**3 <= value["maximum_owned_rss_bytes"] <= 64 * 1024**3
        or set(value["input_bundles"]) != set(LABELS)
        or any(
            type(value[k]) not in (int, float) or not math.isfinite(value[k])
            for k in ("compute_deadline", "transfer_deadline")
        )
        or not now < value["compute_deadline"] < value["transfer_deadline"]
    ):
        raise ValueError("invalid frozen two-pilot job")
    configs = [validate_inputs(inputs)[0] for inputs in value["inputs"]]
    if (
        configs[0].architecture.architecture != "full"
        or configs[1].architecture.architecture == "full"
        or not 1 <= value["split_step"] < configs[0].total_updates
    ):
        raise ValueError("Full control, distinct M candidate and fixed split required")
    expected_paths = {
        "selfplay": BASE + "/input-selfplay",
        "protocol": BASE + "/selfplay-protocol.json",
        "protection": BASE + "/input-protection/config.json",
        "screen": BASE + "/input-screen/config.json",
        "diagnosis_manifest": BASE + "/input-diagnosis/manifest.json",
    }
    common = []
    for inputs in value["inputs"]:
        if (
            inputs["source_commit"] != value["source_commit"]
            or inputs["paths"] != expected_paths
        ):
            raise ValueError("pilot source/input locations differ")
        common.append(
            {
                **inputs,
                "config": {
                    k: v for k, v in inputs["config"].items() if k != "architecture"
                },
            }
        )
    if common[0] != common[1]:
        raise ValueError(
            "pilots require common data, teacher decision, seed and schedule"
        )
    for bundle in value["input_bundles"].values():
        validate_bundle(bundle)
    return configs


def acquire_release(bundle, destination, *, api, fetch, deadline, clock=time.time):
    require_linux()
    validate_bundle(bundle)
    if clock() >= deadline:
        raise InterruptedError("fixed input acquisition deadline")
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    if "plan" not in bundle:
        # The old diagnosis controller retained its verified receipt but not
        # its plan. Reconstruct on Linux from the original seven fixed files;
        # the trusted original whole-plan SHA must match before using data.
        receipt = bundle["receipt"]
        address = {
            "repo_id": receipt["repo_id"],
            "repo_type": "dataset",
            "revision": receipt["hub_commit"],
        }
        info = api.repo_info(**address)
        if (
            info.private
            or info.gated != "manual"
            or info.sha != receipt["hub_commit"]
            or api.community_disabled(repo_id=receipt["repo_id"], repo_type="dataset")
            is not True
        ):
            raise ValueError("diagnosis settings/revision differ")
        for name in DIAGNOSIS_FILES:
            if clock() >= deadline:
                raise InterruptedError("fixed diagnosis reconstruction deadline")
            origin = Path(fetch(**address, filename=name))
            if not origin.is_file() or origin.stat().st_size > 64 * 1024**2:
                raise ValueError("invalid diagnosis reconstruction file")
            shutil.copyfile(origin, destination / name)
        plan = plan_release(
            destination,
            repo_id=receipt["repo_id"],
            repo_type="dataset",
            license_id="cc-by-4.0",
            license_approved=True,
            source_commit=bundle["reconstruct"]["source_commit"],
        )
        if fingerprint(plan) != receipt["release_sha256"]:
            raise ValueError("reconstructed diagnosis release hash differs")
        atomic_json(
            destination.parent / (destination.name + "-release-plan.json"), plan
        )
        return verify_release(
            plan,
            receipt,
            api,
            lambda **kw: destination / kw["filename"],
            system="linux",
        )
    entries = {entry["path"]: entry for entry in bundle["plan"]["files"]}

    def owned_fetch(**kwargs):
        if clock() >= deadline:
            raise InterruptedError("fixed input acquisition deadline")
        entry = entries[kwargs["filename"]]
        origin = Path(fetch(**kwargs))
        if (
            not origin.is_file()
            or origin.stat().st_size != entry["bytes"]
            or file_hash(origin) != entry["sha256"]
        ):
            raise ValueError("input file hash differs")
        target = destination / kwargs["filename"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origin, target)
        return target

    return verify_release(
        bundle["plan"], bundle["receipt"], api, owned_fetch, system="linux"
    )


def check_source(source):
    if subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip() != source or subprocess.check_output(
        ["git", "status", "--porcelain"], text=True
    ):
        raise ValueError("pilot requires exact clean source")


def check_hardware():
    from training.cuda_preflight import (
        collect_facts,
        kernel_probe,
        validate_environment_files,
    )

    return {
        "verified": True,
        "facts": collect_facts(),
        "environment": validate_environment_files(Path.cwd()),
        "kernel": kernel_probe("cuda"),
    }


def run_job(
    value, *, api, fetch, ports=None, clock=time.time, stop_requested=lambda: False
):
    require_linux()
    from infrastructure.research.pilot.cycle import run_cycle

    configs = validate_job(value, now=clock())
    ports = (
        {
            "source": check_source,
            "hardware": check_hardware,
            "acquire": acquire_release,
            "cycle": run_cycle,
        }
        if ports is None
        else ports
    )
    if set(ports) != {"source", "hardware", "acquire", "cycle"}:
        raise ValueError("incomplete pilot job execution ports")
    base = Path(value["base"])
    if (base / "job-request.json").exists() or base.is_symlink():
        raise ValueError(
            "existing pilot request; reconnect and audit instead of restarting"
        )
    budget = base / "state-upload-budget.json"
    if (
        budget.is_symlink()
        or not budget.is_file()
        or budget.stat().st_size > 1024**2
        or file_hash(budget) != value["state_upload_budget_sha256"]
    ):
        raise ValueError("initial state upload ledger differs")
    initial = json.loads(budget.read_text())
    upload_budget_limit(initial)
    ports["source"](value["source_commit"])
    who = api.whoami()
    if who.get("name") != "ayousanz" or not any(
        org.get("name") == "voxelshogi" for org in who.get("orgs", [])
    ):
        raise ValueError("HF account/organization differs")
    hardware = ports["hardware"]()
    if hardware.get("verified") is not True or stop_requested():
        raise ValueError("actual CUDA admission or stop check failed")
    with (base / "job-request.json").open("x") as stream:
        json.dump(
            {
                "job_sha256": fingerprint(value),
                "source_commit": value["source_commit"],
                "at": clock(),
            },
            stream,
        )
    atomic_json(base / "cuda-preflight.json", hardware)
    atomic_json(base / "selfplay-protocol.json", value["selfplay_protocol"])
    current, completed = "input-verification", []
    try:
        for label in LABELS:
            if stop_requested() or clock() >= value["compute_deadline"]:
                raise InterruptedError("fixed pilot input boundary")
            receipt = ports["acquire"](
                value["input_bundles"][label],
                base / ("input-" + label),
                api=api,
                fetch=fetch,
                deadline=value["compute_deadline"],
            )
            if receipt.get("verified") is not True:
                raise ValueError("all immutable input files must be verified")
            atomic_json(base / (label + "-input-receipt.json"), receipt)
        for inputs, config in zip(value["inputs"], configs, strict=True):
            current = "fit-" + config.architecture.architecture
            atomic_json(
                base / "job-status.json",
                {
                    "stage": current,
                    "learning_complete": False,
                    "source_commit": value["source_commit"],
                },
            )
            result = ports["cycle"](
                inputs,
                base / config.architecture.architecture,
                split_step=value["split_step"],
                deadline=value["transfer_deadline"],
                compute_deadline=value["compute_deadline"],
                api=api,
                fetch=fetch,
                upload_budget=budget,
                stop_requested=stop_requested,
            )
            if (
                result.get("scientific_pilots") != 1
                or result.get("additional_independent_seeds") != 0
                or result.get("source_commit") != value["source_commit"]
                or result.get("inputs_sha256") != fingerprint(inputs)
            ):
                raise ValueError("cycle result escaped the frozen scientific job")
            completed.append(result)
    except BaseException as error:
        atomic_json(
            base / "job-failure.json",
            {
                "stage": current,
                "error_type": type(error).__name__,
                "learning_complete": False,
                "completed_scientific_pilots": len(completed),
                "host_retirement_authorized": False,
            },
        )
        raise
    finally:
        final = json.loads(budget.read_text())
        upload_budget_limit(final)
        if {k: v for k, v in final.items() if k != "reservations"} != {
            k: v for k, v in initial.items() if k != "reservations"
        } or final["reservations"][: len(initial["reservations"])] != initial[
            "reservations"
        ]:
            raise ValueError("state upload ledger history/cap changed")
        atomic_json(base / "state-budget-final.json", final)
    result = {
        "schema": "voxelshogi-research-pilot-learning-result-v1",
        "source_commit": value["source_commit"],
        "job_sha256": fingerprint(value),
        "learning_complete": True,
        "scientific_pilots": 2,
        "additional_independent_seeds": 0,
        "cycles": completed,
        "state_budget_final_sha256": fingerprint(final),
        "host_retirement_authorized": False,
        "controller_ledger_collection_required": True,
        "development_evaluation_executed": False,
        "final_holdout_evaluated": False,
    }
    atomic_json(base / "training-complete.json", result)
    return result


def sample_owned_resources():
    import psutil

    parent = psutil.Process()
    processes = [parent, *parent.children(recursive=True)]
    row = {
        "summed_owned_rss_bytes": sum(p.memory_info().rss for p in processes),
        "owned_cpu_seconds": sum(sum(p.cpu_times()[:2]) for p in processes),
    }
    try:
        output = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
        utilization, memory = (int(part.strip()) for part in output.split(","))
        row.update(gpu_utilization_percent=utilization, gpu_memory_used_mib=memory)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        row["gpu_observation_error_type"] = type(error).__name__
    return row


def observe_resources(maximum_rss, stop, done, rows, *, sample=sample_owned_resources):
    require_linux()
    while not done.is_set():
        row = {"monotonic": time.monotonic()}
        try:
            row.update(sample())
            if row["summed_owned_rss_bytes"] > maximum_rss:
                row["stop_reason"] = "owned-rss-limit"
                stop.set()
        except Exception as error:
            row["observation_error_type"] = type(error).__name__
        rows.append(row)
        done.wait(10)


def main():
    require_linux()
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("job", type=Path)
    args = parser.parse_args()
    value = json.loads(args.job.read_text())
    validate_job(value, now=time.time())
    if any(os.environ.get(k) for k in ("VAST_API_KEY", "CLOUDRIFT_API_KEY")):
        raise ValueError("provider credentials must remain on controller")
    token = os.environ.pop("HF_TOKEN")
    from httpx2 import TransportError
    from huggingface_hub import HfApi, hf_hub_download
    from huggingface_hub.utils import build_hf_headers, get_session

    from training.hub_recovery import RecoveryApi
    from training.hub_release import PublicationApi

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    api = RecoveryApi(
        PublicationApi(
            HfApi(endpoint="https://huggingface.co", token=token),
            get_session(),
            build_hf_headers(token=token),
        ),
        deadline=value["transfer_deadline"],
        transient_errors=(TimeoutError, ConnectionError, TransportError),
    )

    def fetch(**kwargs):
        return hf_hub_download(**kwargs, token=token)

    done, rows = threading.Event(), []
    observer = threading.Thread(
        target=observe_resources,
        args=(value["maximum_owned_rss_bytes"], stop, done, rows),
        daemon=True,
    )
    observer.start()
    result = None
    base = Path(value["base"])
    try:
        result = run_job(value, api=api, fetch=fetch, stop_requested=stop.is_set)
    finally:
        done.set()
        observer.join(timeout=12)
        atomic_json(base / "resource-samples.json", rows)
        atomic_json(
            base / "worker-finished.json",
            {
                "learning_complete": result is not None,
                "source_commit": value["source_commit"],
                "observer_stopped": not observer.is_alive(),
                "controller_ledger_collection_required": True,
                "host_retirement_authorized": False,
            },
        )
    print(
        json.dumps(
            {
                "learning_complete": result["learning_complete"],
                "scientific_pilots": 2,
                "source_commit": result["source_commit"],
                "controller_collection_required": True,
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException as error:
        print(
            json.dumps(
                {"learning_complete": False, "error_type": type(error).__name__}
            ),
            flush=True,
        )
        sys.exit(1)
