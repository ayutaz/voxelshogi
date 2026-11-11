"""Owned separate-process CUDA attempts with bounded stop and no credentials."""

import json
import math
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def child_environment(source):
    allowed = {
        "PATH",
        "HOME",
        "LANG",
        "LC_ALL",
        "TMPDIR",
        "PYTHONPATH",
        "LD_LIBRARY_PATH",
        "CUDA_VISIBLE_DEVICES",
        "PYTHONDONTWRITEBYTECODE",
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
    }
    return {
        **{k: v for k, v in source.items() if k in allowed},
        "CUBLAS_WORKSPACE_CONFIG": ":4096:8",
    }


def stop_owned_child(child):
    if child.poll() is not None:
        return "already-terminal"
    os.killpg(child.pid, signal.SIGTERM)
    try:
        child.wait(timeout=20)
        return "terminated"
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        child.wait(timeout=10)
        return "killed"


def review_attempt(result, inputs, *, resume, max_new_steps):
    from training.evaluation_v2 import fingerprint

    fit = result["fit"]
    total = inputs["config"]["total_updates"]
    step = fit["progress"]["step"]
    reason = fit["reason"]
    if (
        result["schema"] != "voxelshogi-research-pilot-attempt-result-v1"
        or result["source_commit"] != inputs["source_commit"]
        or result["input_contract_sha256"] != fingerprint(inputs)
        or result["teacher_decision_sha256"] != fingerprint(inputs["quality_decision"])
        or result["resume"] is not resume
        or fit["binding"]["source_commit"] != inputs["source_commit"]
        or fit["binding"]["config"] != inputs["config"]
        or fit["binding"]["cache_sha256"]
        != result["encoding"]["feature_content_sha256"]
        or type(step) is not int
        or not 0 <= step <= total
        or type(fit["new_steps"]) is not int
        or not 0 <= fit["new_steps"] <= step
        or reason not in ("complete", "max_new_steps", "stopped")
        or reason == "complete"
        and step != total
        or reason != "complete"
        and step >= total
        or reason == "max_new_steps"
        and (max_new_steps is None or fit["new_steps"] != max_new_steps)
        or any(
            type(result[k]) not in (int, float)
            or not math.isfinite(result[k])
            or result[k] < 0
            for k in (
                "preparation_seconds",
                "fitting_call_seconds",
                "whole_attempt_seconds",
            )
        )
        or not math.isclose(
            result["preparation_seconds"] + result["fitting_call_seconds"],
            result["whole_attempt_seconds"],
            rel_tol=1e-6,
            abs_tol=1e-6,
        )
    ):
        raise ValueError("child attempt result does not match frozen inputs/schedule")
    return result


def run_attempt(
    script,
    inputs,
    output,
    *,
    deadline,
    resume=False,
    max_new_steps=None,
    stop_requested=lambda: False,
):
    if sys.platform != "linux":
        raise ValueError("pilot child execution requires external Linux")
    if (
        type(deadline) not in (int, float)
        or not math.isfinite(deadline)
        or time.time() >= deadline
        or type(resume) is not bool
        or max_new_steps is not None
        and (type(max_new_steps) is not int or max_new_steps < 1)
    ):
        raise ValueError("invalid fixed child bounds")
    if stop_requested():
        raise InterruptedError("stopped before child launch")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(script),
        str(inputs),
        str(output),
        "--compute-deadline",
        str(deadline),
    ]
    if resume:
        command.append("--resume")
    if max_new_steps is not None:
        command += ["--max-new-steps", str(max_new_steps)]
    # The parent may hold HF authentication for checkpoint publication. The
    # fitting interpreter receives only this explicit runtime allowlist.
    env = child_environment(os.environ)
    log_path = output.parent / (
        output.name + ("-resume" if resume else "-start") + ".log"
    )
    if log_path.exists():
        raise ValueError("attempt log already exists; audit instead of relaunching")
    with log_path.open("x") as stream:
        child = subprocess.Popen(
            command,
            stdout=stream,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
        retired = None
        try:
            while child.poll() is None:
                if stop_requested() or time.time() >= deadline:
                    retired = stop_owned_child(child)
                    raise InterruptedError("fixed pilot child stop: " + retired)
                time.sleep(1)
            if child.returncode != 0:
                raise RuntimeError("pilot child failed; inspect owned attempt log")
            result = json.loads((output / "attempt-wrapper.json").read_text())
            return review_attempt(
                result,
                json.loads(Path(inputs).read_text()),
                resume=resume,
                max_new_steps=max_new_steps,
            )
        finally:
            if child.poll() is None:
                stop_owned_child(child)
