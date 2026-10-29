"""Control metadata only. No provider calls or paid resources."""

import hashlib
import json

import pytest

from training.tests.test_rental_control import Provider


def setup(tmp_path, **overrides):
    from training.m6_rental_control import M6Rental

    state = tmp_path / "m6-test"
    state.mkdir()
    (state / "id_ed25519.pub").write_text("ssh-ed25519 opaque fixture")
    budget = tmp_path / "budget.json"
    budget.write_text(
        json.dumps(
            {
                "approved_total_usd": 100,
                "reservations": [{"task": "m4-production", "maximum_usd": 41}],
            }
        )
    )
    approval = tmp_path / "approval.json"
    approval.write_text(
        json.dumps(
            {
                "schema": "voxelshogi-m6-rental-approval-v1",
                "approved": True,
                "maximum_usd": 24,
                "maximum_seconds": 86400,
                "maximum_hourly_usd": 1,
                "license": "Apache-2.0",
                "state_publication_approved": True,
            }
        )
    )
    api = Provider()
    api.sku = "rtx59-3-24-750-xam.1"
    values = dict(
        tag="voxelshogi-m6-test",
        budget=budget,
        approval=approval,
        phase="trial",
        maximum_seconds=14400,
        clock=lambda: 1000,
        sku=api.sku,
    )
    values.update(overrides)
    return M6Rental(state, api, **values), api, budget, approval


def test_trial_uses_four_hour_quote_and_m6_reservation_not_m4_twenty_four_hours(
    tmp_path,
):
    control, api, budget, _ = setup(tmp_path)

    def guard():
        assert not any(path.endswith("instances/rent") for path, _ in api.calls)
        assert json.loads(budget.read_text())["reservations"][-1]["task"] == "m6-trial"

    control.rent(guard)
    row = json.loads(budget.read_text())["reservations"][-1]
    assert row["maximum_usd"] == 4 and row["maximum_seconds"] == 14400
    deadline = json.loads((control.state / "deadline.json").read_text())
    assert deadline["stop_at"] == 14500 and deadline["maximum_end_at"] == 15400
    assert deadline["consumption_cap_usd"] == 4


@pytest.mark.parametrize(
    "change",
    [
        "approval",
        "purpose",
        "state",
        "license",
        "hours",
        "global",
        "m6",
        "duplicate",
        "price",
    ],
)
def test_unapproved_purpose_or_excess_budget_never_creates_resource(tmp_path, change):
    control, api, budget, approval = setup(tmp_path)
    declared = json.loads(approval.read_text())
    if change == "approval":
        declared["approved"] = False
    if change == "purpose":
        declared["schema"] = "m4-approval"
    if change == "state":
        declared["state_publication_approved"] = False
    if change == "license":
        declared["license"] = None
    if change == "hours":
        control.maximum_seconds = 14401
    if change in ("global", "m6", "duplicate"):
        value = json.loads(budget.read_text())
        value["reservations"].append(
            {
                "task": "m4-production" if change == "global" else "m6-trial",
                "maximum_usd": 59
                if change == "global"
                else 4
                if change == "duplicate"
                else 24,
                "maximum_seconds": 14400
                if change == "duplicate"
                else 72000
                if change == "m6"
                else 86400,
                "tag": control.tag if change == "duplicate" else "older",
            }
        )
        budget.write_text(json.dumps(value))
    if change == "price":
        api.price = 101
    approval.write_text(json.dumps(declared))
    with pytest.raises(ValueError):
        control.rent(lambda: None)
    assert not any(path.endswith("instances/rent") for path, _ in api.calls)


def test_main_requires_recorded_trial_estimate_and_preserves_aggregate_reservations(
    tmp_path,
):
    control, api, budget, approval = setup(
        tmp_path, phase="main", maximum_seconds=72000
    )
    with pytest.raises(ValueError, match="estimate"):
        control.rent(lambda: None)
    assert api.calls == []
    declared = json.loads(approval.read_text())
    trial = approval.parent / "trial.json"
    trial.write_text(
        json.dumps(
            {
                "schema": "voxelshogi-cuda-trial-v1",
                "verified": True,
                "same_example_order": True,
                "test_used": False,
                "config": {"device": "cuda"},
                "steps": 64,
                "full_examples_per_second_including_logging_save": 2.0,
                "peak_allocated_bytes": 1024,
            }
        )
    )
    declared["main_estimate"] = {
        "trial_sha256": hashlib.sha256(trial.read_bytes()).hexdigest(),
        "estimated_seconds": 60000,
        "maximum_seconds": 72000,
    }
    approval.write_text(json.dumps(declared))
    value = json.loads(budget.read_text())
    value["reservations"].append(
        {
            "task": "m6-trial",
            "tag": "previous",
            "maximum_usd": 4,
            "maximum_seconds": 14400,
        }
    )
    budget.write_text(json.dumps(value))
    control.rent(lambda: None)
    value = json.loads(budget.read_text())
    assert value["reserved_total_usd"] == 65
    assert value["remaining_unreserved_usd"] == 35


def test_guard_cleanup_does_not_require_live_rental_approval(tmp_path):
    control, api, _, approval = setup(tmp_path)
    control.rent(lambda: None)
    api.rows[0]["tags"] = ["voxelshogi-m6-test"]
    approval.unlink()
    assert control.terminate()["complete"] is True


def test_guard_command_keeps_the_m6_ownership_namespace(tmp_path):
    from training.rental_control import guard_command

    command = guard_command(
        tmp_path / "state",
        tmp_path / "budget.json",
        purpose="m6",
        sku="rtx59-3-24-750-xam.1",
    )
    assert command[-4:] == ["--purpose", "m6", "--sku", "rtx59-3-24-750-xam.1"]
    assert command[1:3] == ["-m", "training.rental_control"]
    assert "guard" in command


def test_parent_requires_guard_ready_with_matching_pid_tag_and_deadline(tmp_path):
    from types import SimpleNamespace

    from training.rental_control import wait_for_guard

    ready = tmp_path / "ready.json"
    child = SimpleNamespace(pid=42, poll=lambda: None)
    ticks = [0.0]

    def pause(seconds):
        ticks[0] += seconds
        ready.write_text(
            json.dumps(
                {"pid": 42, "tag": "voxelshogi-m6-test", "deadline_sha256": "a" * 64}
            )
        )

    wait_for_guard(
        ready,
        child,
        tag="voxelshogi-m6-test",
        deadline_sha256="a" * 64,
        clock=lambda: ticks[0],
        pause=pause,
    )
    assert ticks[0] > 0
    for change in ({"pid": 7}, {"tag": "other"}, {"deadline_sha256": "b" * 64}):
        ready.write_text(
            json.dumps(
                {"pid": 42, "tag": "voxelshogi-m6-test", "deadline_sha256": "a" * 64}
                | change
            )
        )
        with pytest.raises(RuntimeError, match="mismatch"):
            wait_for_guard(
                ready, child, tag="voxelshogi-m6-test", deadline_sha256="a" * 64
            )


@pytest.mark.parametrize(
    "name", ["terminal.json", "guardian-ready.json", "deadline.json"]
)
def test_consumed_control_directory_cannot_skip_a_new_guard(tmp_path, name):
    control, api, _, _ = setup(tmp_path)
    (control.state / name).write_text("{}")
    with pytest.raises(ValueError):
        control.rent(lambda: None)
    assert not any(path.endswith("instances/rent") for path, _ in api.calls)


def test_cli_does_not_treat_m6_approval_as_an_m4_rental(tmp_path, monkeypatch):
    import sys
    from pathlib import Path

    from training.rental_control import main

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "rental_control",
            "runs/m6/control",
            "rent",
            "--approval",
            str(tmp_path / "approval.json"),
        ],
    )

    def no_read(*args, **kwargs):
        raise AssertionError("must reject ambiguous purpose before credential reads")

    monkeypatch.setattr(Path, "read_text", no_read)
    with pytest.raises(SystemExit):
        main()


def test_real_guard_module_starts_from_an_isolated_control_checkout_without_network(
    tmp_path,
):
    import os
    import shutil
    import subprocess
    import sys
    import time
    from pathlib import Path

    source = Path(__file__).resolve().parents[1]
    package = tmp_path / "training"
    package.mkdir()
    for name in ("rental_control.py", "m6_rental_control.py"):
        shutil.copyfile(source / name, package / name)
    (tmp_path / ".env").write_text("CLOUDRIFT_API_KEY=opaque-test-not-a-credential\n")
    state = tmp_path / "runs/m6/control"
    state.mkdir(parents=True)
    raw = json.dumps(
        {"stop_at": time.time() + 60, "maximum_end_at": time.time() + 120}
    ).encode()
    (state / "deadline.json").write_bytes(raw)
    (state / "terminal.json").write_text("{}")  # Finish without provider access.
    runner = """import runpy, sys, urllib.request
def no_network(*args, **kwargs):
    raise AssertionError('unexpected provider access')
urllib.request.build_opener = no_network
sys.argv = ['rental_control', sys.argv[1], 'guard', '--purpose', 'm6', '--ready-file', sys.argv[2]]
runpy.run_module('training.rental_control', run_name='__main__')
"""
    ready = state / "guardian-ready.json"
    result = subprocess.run(
        [sys.executable, "-c", runner, str(state), str(ready)],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(tmp_path)},
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    value = json.loads(ready.read_text())
    assert value["tag"] == "voxelshogi-m6-control"
    assert value["deadline_sha256"] == hashlib.sha256(raw).hexdigest()
    assert value["pid"] > 0


def test_parent_rejects_dead_or_nonready_guard_without_provider_actions(tmp_path):
    from types import SimpleNamespace

    from training.rental_control import wait_for_guard

    ready = tmp_path / "missing.json"
    with pytest.raises(RuntimeError):
        wait_for_guard(
            ready,
            SimpleNamespace(pid=42, poll=lambda: 1),
            tag="m6",
            deadline_sha256="a" * 64,
        )
    ticks = [0.0]
    with pytest.raises(RuntimeError):
        wait_for_guard(
            ready,
            SimpleNamespace(pid=42, poll=lambda: None),
            tag="m6",
            deadline_sha256="a" * 64,
            clock=lambda: ticks[0],
            pause=lambda seconds: ticks.__setitem__(0, ticks[0] + seconds),
        )
