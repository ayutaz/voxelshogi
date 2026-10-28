"""Resource limits use injected observations, plus real owned child processes."""

import json
import sys

import psutil
import pytest


def test_limits_are_checked_at_exact_time_and_memory_boundaries():
    from training.runner import monitor

    class Process:
        pid = 123

        def poll(self):
            return None

    ticks = iter([0.0, 4.999, 5.0, 5.001])
    samples = []

    def sample(pid):
        samples.append(pid)
        return {"rss": 1024, "pressure": False, "swap": 0}

    report = monitor(
        Process(),
        seconds=5,
        rss_limit=2048,
        sample=sample,
        clock=lambda: next(ticks),
        pause=lambda _: None,
    )
    assert report["reason"] == "time" and report["elapsed"] == 5
    assert samples == [123] and report["peak_rss"] == 1024
    memory_ticks = iter([0, 0, 5])
    report = monitor(
        Process(),
        seconds=5,
        rss_limit=1024,
        sample=sample,
        clock=lambda: next(memory_ticks),
        pause=lambda _: None,
    )
    assert report["reason"] == "memory"

    class LateProcess:
        def poll(self):
            return 0

    late_ticks = iter([0, 5])
    report = monitor(
        LateProcess(), seconds=5, rss_limit=2048, clock=lambda: next(late_ticks)
    )
    assert report["reason"] == "time"  # Late completion cannot prove the deadline.


def test_pressure_and_sustained_swap_growth_stop_early():
    from training.runner import monitor

    class Process:
        pid = 123

        def poll(self):
            return None

    pressure_ticks = iter([0, 0, 5])
    result = monitor(
        Process(),
        seconds=5,
        rss_limit=4096,
        sample=lambda _: {"rss": 1, "pressure": True, "swap": 0},
        clock=lambda: next(pressure_ticks),
        pause=lambda _: None,
    )
    assert result["reason"] == "pressure"
    observations = iter([0, 65 * 1024**2, 65 * 1024**2, 65 * 1024**2])
    result = monitor(
        Process(),
        seconds=5,
        rss_limit=4096,
        sample=lambda _: {"rss": 1, "pressure": False, "swap": next(observations)},
        clock=lambda: 0,
        pause=lambda _: None,
    )
    assert result["reason"] == "swap"


def test_real_native_blocked_worker_and_descendant_are_stopped(tmp_path):
    from training.runner import run_bounded

    pidfile = tmp_path / "pids.json"
    code = """
import json, os, subprocess, sys
import psutil
from voxelshogi import Game
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
game = Game()
ready = {'pids': [os.getpid(), child.pid], 'cpu_start': psutil.Process().cpu_times().user}
with open(sys.argv[1] + '.tmp', 'w') as handle:
    json.dump(ready, handle)
os.replace(sys.argv[1] + '.tmp', sys.argv[1])
game.search(max_depth=64, max_nodes=1000000)
"""
    observed = []

    def sample(pid):
        if not pidfile.exists():
            return {"rss": 1, "pressure": False, "swap": 0}
        ready = json.loads(pidfile.read_text())
        if psutil.Process(pid).cpu_times().user - ready["cpu_start"] < 0.02:
            return {"rss": 1, "pressure": False, "swap": 0}
        observed.extend(ready["pids"])
        return {"rss": 1024, "pressure": False, "swap": 0}

    report = run_bounded(
        [sys.executable, "-c", code, str(pidfile)],
        ledger=tmp_path / "budget.json",
        seconds=5,
        rss_limit=1024,
        sample=sample,
    )
    assert report["reason"] == "memory" and report["returncode"] != 0
    assert len(set(observed)) == 2
    for pid in set(observed):
        assert (
            not psutil.pid_exists(pid)
            or psutil.Process(pid).status() == psutil.STATUS_ZOMBIE
        )


def test_success_error_and_session_budget_are_not_confused(tmp_path):
    from training.runner import run_bounded

    ledger = tmp_path / "budget.json"
    good = run_bounded(
        [sys.executable, "-c", "pass"],
        ledger=ledger,
        seconds=5,
        sample=lambda _: {"rss": 1, "pressure": False, "swap": 0},
    )
    assert good["reason"] == "completed" and good["returncode"] == 0
    bad = run_bounded(
        [sys.executable, "-c", "raise SystemExit(7)"],
        ledger=ledger,
        seconds=5,
        sample=lambda _: {"rss": 1, "pressure": False, "swap": 0},
    )
    assert bad["reason"] == "failed" and bad["returncode"] == 7
    saved = json.loads(ledger.read_text())
    assert 0 < saved["spent_seconds"] < 10
    ledger.write_text(json.dumps({"schema": 1, "spent_seconds": 600}))
    sentinel = tmp_path / "must-not-run"
    with pytest.raises(ValueError, match="session"):
        run_bounded(
            [sys.executable, "-c", f"open({str(sentinel)!r}, 'w').close()"],
            ledger=ledger,
        )
    assert not sentinel.exists()
    with pytest.raises(ValueError):
        run_bounded([sys.executable, "-c", "pass"], ledger=ledger, seconds=301)


def test_overlapping_run_cannot_acquire_same_session_budget(tmp_path):
    import fcntl

    from training.runner import run_bounded

    ledger = tmp_path / "budget.json"
    with ledger.open("w") as handle:
        handle.write('{"schema":1,"spent_seconds":0}')
        handle.flush()
        fcntl.flock(handle, fcntl.LOCK_EX)
        with pytest.raises(ValueError, match="active"):
            run_bounded([sys.executable, "-c", "pass"], ledger=ledger)


def test_observation_failure_fails_closed_and_cleans_up(tmp_path):
    from training.runner import run_bounded

    def broken(_):
        raise psutil.AccessDenied(123)

    result = run_bounded(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        ledger=tmp_path / "budget.json",
        sample=broken,
    )
    assert result["reason"] == "observation_error" and result["returncode"] != 0


def test_interrupt_after_leader_exits_still_cleans_up_descendant(tmp_path, monkeypatch):
    import os
    import signal

    import training.runner as runner

    pidfile = tmp_path / "child.pid"
    code = """
import subprocess, sys
from pathlib import Path
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
Path(sys.argv[1]).write_text(str(child.pid))
"""

    def interrupt(process, **_):
        process.wait(timeout=3)
        raise KeyboardInterrupt

    monkeypatch.setattr(runner, "monitor", interrupt)
    try:
        with pytest.raises(KeyboardInterrupt):
            runner.run_bounded(
                [sys.executable, "-c", code, str(pidfile)],
                ledger=tmp_path / "budget.json",
            )
        pid = int(pidfile.read_text())
        assert (
            not psutil.pid_exists(pid)
            or psutil.Process(pid).status() == psutil.STATUS_ZOMBIE
        )
    finally:
        if pidfile.exists():
            pid = int(pidfile.read_text())
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_cli_generates_small_dataset_and_refuses_oversized_local_job(tmp_path):
    from training.data import validate_dataset

    # Worker is launched by the supervisor with a fixed managed interpreter.
    from training.runner import generate_bounded
    from training.tests.test_data import config

    out = tmp_path / "dataset"
    result = generate_bounded(
        out, config(), ledger=tmp_path / "budget.json", seconds=10
    )
    assert result["reason"] == "completed" and result["validation"]["rows"] == 9
    assert validate_dataset(out)["games"] == 3
    validated = generate_bounded(
        out, config(), ledger=tmp_path / "budget.json", seconds=10, validate_only=True
    )
    assert (
        validated["reason"] == "completed"
        and validated["validation"] == result["validation"]
    )
    from dataclasses import replace

    with pytest.raises(ValueError, match="local"):
        generate_bounded(
            tmp_path / "large",
            replace(config(), games=100000),
            ledger=tmp_path / "new.json",
        )


def test_actual_generator_killed_before_commit_can_resume_identically(tmp_path):
    from training.data import generate_dataset
    from training.runner import generate_bounded
    from training.tests.test_data import config, files

    out, fresh = tmp_path / "interrupted", tmp_path / "fresh"
    first = generate_bounded(
        out, config(), ledger=tmp_path / "budget.json", seconds=0.01
    )
    assert first["reason"] == "time"
    second = generate_bounded(
        out, config(), ledger=tmp_path / "budget.json", seconds=10
    )
    assert second["reason"] == "completed"
    generate_dataset(fresh, config())
    assert files(out) == files(fresh)


def test_cli_exposes_generation_and_bounded_validation():
    import subprocess

    result = subprocess.run(
        [sys.executable, "-m", "training", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert (
        result.returncode == 0
        and "generate" in result.stdout
        and "validate" in result.stdout
    )
