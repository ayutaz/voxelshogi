"""Actual controller composition through fake SSH/owner ports and small ledgers."""

import json
from pathlib import Path

import pytest

from training.checkpoint import atomic_json
from training.evaluation_v2 import fingerprint
from training.tests.test_research_pilot_retirement import collection_fixture


def controller_fixture(tmp_path, monkeypatch, mode="complete"):
    from infrastructure.research.pilot.control import PilotController

    value, initial, snapshot = collection_fixture(tmp_path, monkeypatch)
    state = tmp_path / "research-pilot1-control"
    state.mkdir()
    raw = (Path(value["job"]["base"]) / "state-upload-budget.json").read_bytes()
    (state / "state-upload-budget-initial.json").write_bytes(raw)
    atomic_json(state / "workflow.json", value)
    atomic_json(state / "deadline.json", {"maximum_end_at": 2000})
    atomic_json(
        state / "owner.json",
        {
            "provider": "vast.ai",
            "instance_id": 123,
            "tag": "voxelshogi-phase6-research-pilot1-control",
        },
    )
    atomic_json(
        state / "workload.json",
        {
            "admitted": True,
            "stage": "research-pilot",
            "source_commit": value["job"]["source_commit"],
            "run_label": "voxelshogi-phase6-research-pilot1-control",
            "workflow_sha256": fingerprint(value),
        },
    )
    shared = tmp_path / "shared-budget.json"
    shared.write_bytes(raw)
    events = []

    def request(kind, payload):
        events.append(kind)
        assert payload["workflow"] == value
        if kind == "install":
            return {"installed": True, "workflow_sha256": fingerprint(value)}
        if kind == "launch":
            assert payload["hf_token"] == "opaque-not-a-credential"
            if mode == "lost-launch":
                raise TimeoutError("SSH observation expired")
            return {k: v for k, v in snapshot["process"].items() if k != "running"}
        if kind in ("observe", "collect"):
            return snapshot
        raise AssertionError(kind)

    def retire():
        events.append("retire")
        assert json.loads(shared.read_text()) == snapshot["state_budget"]
        assert (state / "collection-receipt.json").is_file()
        return {"complete": True, "instances": []}

    controller = PilotController(
        state, shared_budget=shared, request=request, retire=retire, clock=lambda: 100
    )
    return controller, value, snapshot, state, events


def test_controller_launch_arms_watcher_and_watch_collects_before_delete(
    tmp_path, monkeypatch
):
    c, value, snapshot, state, events = controller_fixture(tmp_path, monkeypatch)

    def watcher():
        events.append("watcher")
        return {"pid": 99}

    c.start_worker("opaque-not-a-credential", start_watcher=watcher)
    assert events == ["install", "launch", "watcher"]
    result = c.watch(wait=lambda _: pytest.fail("finished worker should not wait"))
    assert result["resources_released"] is True
    assert events == ["install", "launch", "watcher", "observe", "collect", "retire"]
    assert (state / "pilot-retirement-request.json").is_file()
    assert (
        "opaque-not-a-credential" not in (state / "launch-submission.json").read_text()
    )


def test_controller_never_resubmits_a_launch_after_unknown_ssh_response(
    tmp_path, monkeypatch
):
    c, _, _, state, events = controller_fixture(tmp_path, monkeypatch, "lost-launch")
    with pytest.raises(TimeoutError):
        c.start_worker(
            "opaque-not-a-credential", start_watcher=lambda: pytest.fail("watcher")
        )
    with pytest.raises(ValueError):
        c.start_worker(
            "opaque-not-a-credential", start_watcher=lambda: pytest.fail("watcher")
        )
    assert events == ["install", "launch"]
    assert (state / "launch-submission.json").is_file()


def test_controller_never_repeats_delete_and_rejects_wrong_workload(
    tmp_path, monkeypatch
):
    c, _, snapshot, state, events = controller_fixture(tmp_path, monkeypatch)
    atomic_json(
        state / "job-launch.json",
        {k: v for k, v in snapshot["process"].items() if k != "running"},
    )
    c.watch(wait=lambda _: None)
    with pytest.raises(ValueError):
        c.watch(wait=lambda _: None)
    assert events.count("retire") == 1


def test_vast_ssh_coordinates_must_match_the_recorded_owner(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from infrastructure.research.pilot import control

    c, _, _, state, _ = controller_fixture(tmp_path, monkeypatch)
    atomic_json(state / "rent-response.json", {"instance_ids": [123]})
    atomic_json(state / "owner.json", {**c.owner, "instance_id": 124})
    session = object.__new__(control.VastTransport)
    session.state = state
    session.workload = {"run_label": c.owner["tag"]}
    session.rental = SimpleNamespace(
        owned=lambda: [
            {
                "id": 123,
                "actual_status": "running",
                "ssh_host": "example.invalid",
                "ssh_port": 2222,
            }
        ]
    )
    calls = []
    monkeypatch.setattr(
        control.subprocess,
        "run",
        lambda *a, **k: calls.append(a) or SimpleNamespace(stdout=b"{}"),
    )
    with pytest.raises(ValueError):
        session.shell("true")
    assert calls == []


def test_direct_retirement_entry_also_refuses_resending_delete(tmp_path, monkeypatch):
    c, _, snapshot, state, events = controller_fixture(tmp_path, monkeypatch)
    atomic_json(
        state / "job-launch.json",
        {k: v for k, v in snapshot["process"].items() if k != "running"},
    )
    c.watch(wait=lambda _: None)
    with pytest.raises(FileExistsError):
        c.retire_once()
    assert events.count("retire") == 1
