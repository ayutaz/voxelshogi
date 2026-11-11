"""Linux-only input staging and once-only pilot launch, authenticated via stdin."""

import base64
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from infrastructure.research.pilot import job
from infrastructure.research.pilot.child import child_environment
from infrastructure.research.pilot.collection import small_json
from infrastructure.research.pilot.results import fingerprint_bytes
from infrastructure.research.pilot.workflow import validate_workflow
from training.checkpoint import atomic_json
from training.evaluation_v2 import fingerprint
from training.feature_cache import file_hash
from training.state_upload_budget import upload_budget_limit


def admitted(value, owner, *, clock):
    if sys.platform != "linux":
        raise ValueError("remote pilot operations require external Linux")
    validate_workflow(value, now=clock())
    if (
        type(owner) is not dict
        or set(owner) != {"provider", "instance_id", "tag"}
        or owner["provider"] != "vast.ai"
        or type(owner["instance_id"]) is not int
        or owner["instance_id"] <= 0
        or not re.fullmatch(
            r"voxelshogi-phase6-research-pilot[1-9][0-9]*-control", str(owner["tag"])
        )
    ):
        raise ValueError("exact owned pilot host required")
    job.check_source(value["job"]["source_commit"])
    base = Path(value["job"]["base"])
    boot = small_json(base / "bootstrap-complete.json")
    if boot != {"complete": True, "source_commit": value["job"]["source_commit"]}:
        raise ValueError("exact source bootstrap must be complete")
    return base


def install_inputs(value, *, ledger_base64, owner, clock=time.time):
    base = admitted(value, owner, clock=clock)
    if any(
        (base / name).exists()
        for name in (
            "job-launch-request.json",
            "workflow-request.json",
            "job-request.json",
        )
    ):
        raise ValueError("existing launch must be reconciled")
    ledger = base64.b64decode(ledger_base64, validate=True)
    if (
        len(ledger) > 1024**2
        or fingerprint_bytes(ledger) != value["job"]["state_upload_budget_sha256"]
    ):
        raise ValueError("frozen initial ledger bytes differ")
    upload_budget_limit(json.loads(ledger))
    for name, data in (("workflow.json", value), ("owner.json", owner)):
        path = base / name
        if path.is_symlink() or path.exists() and small_json(path) != data:
            raise ValueError("staged metadata differs")
        if not path.exists():
            atomic_json(path, data)
    path = base / "state-upload-budget.json"
    if path.is_symlink() or path.exists() and path.read_bytes() != ledger:
        raise ValueError("staged ledger differs")
    if not path.exists():
        with path.open("xb") as stream:
            stream.write(ledger)
        path.chmod(0o600)
    return {
        "installed": True,
        "workflow_sha256": fingerprint(value),
        "state_upload_budget_sha256": file_hash(path),
    }


def birth_time(pid):
    import psutil

    return psutil.Process(pid).create_time()


def launch_worker(
    value, *, hf_token, owner, popen=subprocess.Popen, birth=birth_time, clock=time.time
):
    base = admitted(value, owner, clock=clock)
    if (
        not isinstance(hf_token, str)
        or not 1 <= len(hf_token) <= 65536
        or any(os.environ.get(k) for k in ("VAST_API_KEY", "CLOUDRIFT_API_KEY"))
    ):
        raise ValueError("HF-only in-memory authentication required")
    if (
        small_json(base / "workflow.json") != value
        or small_json(base / "owner.json") != owner
        or file_hash(base / "state-upload-budget.json")
        != value["job"]["state_upload_budget_sha256"]
    ):
        raise ValueError("staged workflow/owner/ledger differs")
    if any(
        (base / name).exists()
        for name in (
            "job-launch-request.json",
            "job-launch.json",
            "workflow-request.json",
            "job-request.json",
            "job.log",
        )
    ):
        raise ValueError("existing launch; inspect its PID instead of resending")
    with (base / "job-launch-request.json").open("x") as stream:
        json.dump(
            {
                "at": clock(),
                "workflow_sha256": fingerprint(value),
                "source_commit": value["job"]["source_commit"],
            },
            stream,
        )
    env = {
        **child_environment(os.environ),
        "HF_TOKEN": hf_token,
        "HF_TOKEN_PATH": "/dev/null",
        "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
        "HF_HUB_DISABLE_PROGRESS_BARS": "1",
        "HF_HUB_VERBOSITY": "error",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
    }
    with (base / "job.log").open("xb") as log:
        process = popen(
            [
                str(Path.home() / ".local/bin/uv"),
                "run",
                "--project",
                "infrastructure/cuda",
                "--locked",
                "--no-sync",
                "python",
                "-u",
                "-m",
                "infrastructure.research.pilot.workflow",
                str(base / "workflow.json"),
            ],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    result = {
        "pid": process.pid,
        "create_time": birth(process.pid),
        "source_commit": value["job"]["source_commit"],
        "workflow_sha256": fingerprint(value),
        "at": clock(),
    }
    atomic_json(base / "job-launch.json", result)
    return result


def main():
    if sys.platform != "linux":
        raise ValueError("remote pilot RPC requires external Linux")
    raw = sys.stdin.buffer.read(4 * 1024**2 + 1)
    if len(raw) > 4 * 1024**2:
        raise ValueError("oversized remote pilot request")
    request = json.loads(raw)
    if request["mode"] == "install":
        result = install_inputs(
            request["workflow"],
            ledger_base64=request["ledger_base64"],
            owner=request["owner"],
        )
    elif request["mode"] == "launch":
        result = launch_worker(
            request["workflow"],
            hf_token=request.pop("hf_token"),
            owner=request["owner"],
        )
    else:
        raise ValueError("unknown remote pilot operation")
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        print(
            json.dumps(
                {"remote_operation_complete": False, "error_type": type(error).__name__}
            ),
            flush=True,
        )
        sys.exit(1)
