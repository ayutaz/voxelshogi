"""One owned process group, bounded by wall time, RSS and a session ledger."""

import fcntl
import json
import math
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import psutil

MAX_SECONDS = 300
SESSION_SECONDS = 600
MAX_RSS = 1024**3
THREAD_ENV = {
    name: "1"
    for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "ARROW_NUM_THREADS",
    )
}


def sample_resources(pid):
    root = psutil.Process(pid)
    processes = [root, *root.children(recursive=True)]
    rss = 0
    for process in processes:
        try:
            rss += process.memory_info().rss
        except psutil.NoSuchProcess:
            pass
    memory = psutil.virtual_memory()
    # Available-memory pressure proxy is portable. It is recorded as such, not
    # presented as macOS's Activity Monitor pressure gauge or GPU memory.
    return {
        "rss": rss,
        "pressure": memory.available < max(512 * 1024**2, memory.total * 0.10),
        "swap": psutil.swap_memory().used,
    }


def monitor(
    process,
    *,
    seconds,
    rss_limit,
    sample=sample_resources,
    clock=time.monotonic,
    pause=time.sleep,
):
    start, peak, initial_swap, swap_growth = clock(), 0, None, 0
    while True:
        elapsed = max(0.0, clock() - start)
        code = process.poll()
        if elapsed >= seconds:
            return {"reason": "time", "elapsed": elapsed, "peak_rss": peak}
        if code is not None:
            return {
                "reason": "completed" if code == 0 else "failed",
                "elapsed": elapsed,
                "peak_rss": peak,
            }
        try:
            observation = sample(process.pid)
            rss = observation["rss"]
            if type(rss) is not int or rss < 0:
                raise ValueError("invalid RSS observation")
            peak = max(peak, rss)
            initial_swap = observation["swap"] if initial_swap is None else initial_swap
            swap_growth = (
                swap_growth + 1
                if observation["swap"] - initial_swap >= 64 * 1024**2
                else 0
            )
            reason = (
                "memory"
                if rss >= rss_limit
                else "pressure"
                if observation["pressure"]
                else "swap"
                if swap_growth >= 3
                else None
            )
            if reason:
                return {"reason": reason, "elapsed": elapsed, "peak_rss": peak}
        except (psutil.Error, OSError, ValueError, KeyError) as error:
            # A child may exit between poll and observation. Otherwise stop;
            # inaccessible resource information is not permission to run blind.
            if process.poll() is None:
                return {
                    "reason": "observation_error",
                    "elapsed": elapsed,
                    "peak_rss": peak,
                    "error": type(error).__name__,
                }
        pause(min(0.1, max(0.001, seconds - elapsed)))


def _stop_group(process):
    # The group was created by this invocation; never target unrelated processes.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass
    # Also remove a TERM-resistant descendant after the group leader has exited.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=3)
    # A group leader may already be reaped while its orphaned descendants are
    # still receiving KILL. Verify the group has no live member before returning.
    deadline = time.monotonic() + 1
    while True:
        live = []
        for pid in psutil.pids():
            try:
                if (
                    os.getpgid(pid) == process.pid
                    and psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
                ):
                    live.append(pid)
            except ProcessLookupError, psutil.NoSuchProcess:
                pass
            except PermissionError:
                # Reading another user's process group may be forbidden; the
                # processes in our newly created group belong to this user.
                continue
        if not live:
            return
        if time.monotonic() >= deadline:
            raise RuntimeError("owned process group did not stop")
        time.sleep(0.01)


def run_bounded(
    command,
    *,
    ledger,
    seconds=MAX_SECONDS,
    rss_limit=MAX_RSS,
    sample=sample_resources,
    log=None,
):
    if (
        isinstance(seconds, bool)
        or not isinstance(seconds, (int, float))
        or not math.isfinite(seconds)
        or not 0 < seconds <= MAX_SECONDS
        or type(rss_limit) is not int
        or not 0 < rss_limit <= MAX_RSS
    ):
        raise ValueError("invalid local limits")
    ledger = Path(ledger)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a+") as budget:
        try:
            fcntl.flock(budget, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("another session job is active") from error
        budget.seek(0)
        text = budget.read()
        saved = json.loads(text) if text else {"schema": 1, "spent_seconds": 0}
        spent = saved.get("spent_seconds")
        if (
            set(saved) != {"schema", "spent_seconds"}
            or saved["schema"] != 1
            or type(spent) not in (int, float)
            or not math.isfinite(spent)
            or spent < 0
        ):
            raise ValueError("invalid session budget")
        remaining = SESSION_SECONDS - spent
        if remaining <= 0:
            raise ValueError("session budget exhausted")
        seconds = min(seconds, remaining)

        def save(value):
            budget.seek(0)
            budget.truncate()
            budget.write(json.dumps({"schema": 1, "spent_seconds": value}) + "\n")
            budget.flush()
            os.fsync(budget.fileno())

        # Reserve first. A killed supervisor consumes its reservation rather than
        # granting an unlimited retry after its file lock is released.
        save(spent + seconds)
        process, started, cleaned = None, time.monotonic(), False
        try:
            process = subprocess.Popen(
                command,
                start_new_session=True,
                env={**os.environ, **THREAD_ENV},
                stdout=log,
                stderr=log,
            )
            report = monitor(
                process, seconds=seconds, rss_limit=rss_limit, sample=sample
            )
            _stop_group(process)
            cleaned = True
            report["returncode"] = process.returncode
            return report
        finally:
            if process is not None and not cleaned:
                _stop_group(process)
            save(spent + min(seconds, max(0.0, time.monotonic() - started)))


def generate_bounded(
    directory, config, *, ledger, seconds=MAX_SECONDS, validate_only=False
):
    from .data import canonical

    if (
        config.games > 16
        or config.max_plies > 64
        or config.max_depth > 4
        or config.max_nodes > 10000
    ):
        raise ValueError("local job exceeds small-generation limits")
    directory = Path(directory).resolve()
    directory.parent.mkdir(parents=True, exist_ok=True)
    report_file = directory.with_name(directory.name + ".validation.json")
    report_file.unlink(missing_ok=True)
    with directory.with_name(directory.name + ".worker.log").open("w") as log:
        result = run_bounded(
            [
                sys.executable,
                "-m",
                "training.worker",
                str(directory),
                canonical(config.value()),
                str(report_file),
                "validate" if validate_only else "generate",
            ],
            ledger=ledger,
            seconds=seconds,
            log=log,
        )
    if result["reason"] == "completed":
        if not report_file.exists():
            raise ValueError("successful worker has no validation report")
        result["validation"] = json.loads(report_file.read_text())
    return result
