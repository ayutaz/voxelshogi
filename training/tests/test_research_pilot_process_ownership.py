"""Handwritten process inventory; no real processes, models or provider calls."""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def inventory(monkeypatch, tmp_path):
    from infrastructure.research.pilot import collection

    monkeypatch.setattr(collection.sys, "platform", "linux")
    root = Path.cwd().resolve()
    base = Path("runs/p6/research-pilot")

    class Process:
        def __init__(self, pid, command, cwd=root, state="live"):
            self.pid, self.command, self.folder, self.state = pid, command, cwd, state

        def create_time(self):
            return self.pid + 0.5

        def is_running(self):
            return self.state == "live"

        def status(self):
            return self.state

        def cmdline(self):
            return self.command

        def cwd(self):
            return str(self.folder)

    command = [
        "python",
        "-m",
        "infrastructure.research.pilot.attempt",
        str(root / base / "full/continuous"),
    ]
    rows = [
        Process(
            101,
            [
                "python",
                "-m",
                "infrastructure.research.pilot.workflow",
                str(base / "workflow.json"),
            ],
        ),
        Process(102, command),
        Process(
            103,
            [
                "python",
                str(root / "infrastructure/research/pilot/attempt.py"),
                str(base / "geometry/restored"),
            ],
        ),
        Process(104, command, cwd=tmp_path),
        Process(
            105, ["python", "-m", "other.module", str(root / base / "full/continuous")]
        ),
        Process(
            106,
            [
                "python",
                "-m",
                "infrastructure.research.pilot.attempt",
                "runs/foreign/output",
            ],
        ),
        Process(107, command, state="zombie"),
        Process(os.getpid(), command),
    ]
    fake = SimpleNamespace(
        Process=lambda pid: next(p for p in rows if p.pid == pid),
        process_iter=lambda: rows,
        STATUS_ZOMBIE="zombie",
        NoSuchProcess=ProcessLookupError,
    )
    monkeypatch.setitem(sys.modules, "psutil", fake)
    expected = {"pid": 101, "create_time": 101.5, "source_commit": "a" * 40}
    return collection, base, expected, rows


def test_owned_module_child_is_counted_with_workflow_and_legacy_child(
    monkeypatch, tmp_path
):
    module, base, expected, _ = inventory(monkeypatch, tmp_path)
    result = module.inspect_process(expected, base)
    assert result["process"] == {**expected, "running": True}
    assert result["owned_compute"] == [
        {"pid": 101, "create_time": 101.5},
        {"pid": 102, "create_time": 102.5},
        {"pid": 103, "create_time": 103.5},
    ]


def test_terminal_parent_does_not_hide_a_live_module_child(monkeypatch, tmp_path):
    module, base, expected, rows = inventory(monkeypatch, tmp_path)
    rows[0].state = "zombie"
    result = module.inspect_process(expected, base)
    assert result["process"]["running"] is False
    assert {p["pid"] for p in result["owned_compute"]} == {102, 103}


def test_reused_worker_pid_is_rejected(monkeypatch, tmp_path):
    module, base, expected, _ = inventory(monkeypatch, tmp_path)
    expected["create_time"] = 100.5
    with pytest.raises(ValueError, match="PID reused"):
        module.inspect_process(expected, base)
