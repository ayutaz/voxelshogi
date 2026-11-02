"""Exact-label destruction, no paid creation, and actual provider-bound run proof."""

from copy import deepcopy

import pytest

from training.remote_deadline import Deadline, arm, watch
from training.tests.test_remote_deadline import TAG
from training.tests.test_vast_rental_control import Provider


def adapter(api):
    from training.remote_vast_deadline import VastDeadlineApi

    return VastDeadlineApi(api, tag=TAG)


def spec():
    return Deadline(TAG, 5000)


def test_arm_probes_complete_inventory_and_refuses_an_existing_label():
    p = Provider()
    a = adapter(p)
    assert arm(spec(), a, clock=lambda: 1000)["tag"] == TAG
    p.rows = [{"id": 456, "label": TAG, "actual_status": "running"}]
    with pytest.raises(ValueError, match="already"):
        arm(spec(), a, clock=lambda: 1000)
    assert not any(method in ["PUT", "POST", "DELETE"] for method, *_ in p.calls)


def test_independent_clock_destroys_only_exact_owned_label_and_confirms_absence(capsys):
    p = Provider()
    p.rows = [
        {"id": 456, "label": TAG, "actual_status": "running"},
        {"id": 999, "label": "unrelated", "actual_status": "running"},
    ]

    # The provider fixture below preserves the unrelated instance on destruction.
    def api(method, path, data=None, params=None):
        if method == "DELETE":
            assert path == "/api/v0/instances/456"
            p.calls.append((method, path, data, params))
            p.rows = [r for r in p.rows if r["id"] != 456]
            return {"success": True}
        return p(method, path, data, params)

    now = [3700]

    def pause(seconds):
        now[0] += seconds

    result = watch(spec(), adapter(api), clock=lambda: now[0], pause=pause)
    assert result == {"complete": True, "instance_ids": [456]}
    assert now[0] == 3860 and p.rows[0]["id"] == 999
    assert [x[1] for x in p.calls if x[0] == "DELETE"] == ["/api/v0/instances/456"]
    assert "termination_requested" in capsys.readouterr().out


def test_missing_without_destroy_ack_is_not_release_confirmation():
    p = Provider()
    p.rows = [{"id": 456, "label": TAG, "actual_status": "running"}]
    a = adapter(p)
    from training.remote_deadline import owned

    assert owned(spec(), a)[0]["resources_released"] is False
    p.rows = []
    assert owned(spec(), a) == []  # shared watch retains seen IDs and cannot complete.


def test_failed_ack_retained_rows_and_relabel_are_never_confirmed():
    p = Provider()
    p.rows = [{"id": 456, "label": TAG, "actual_status": "running"}]
    a = adapter(p)
    from training.remote_deadline import owned

    owned(spec(), a)
    p.retain_after_delete = True
    a("/api/v1/instances/terminate", {"selector": {"ById": [456]}})
    retained = owned(spec(), a)
    assert [row["id"] for row in retained] == [456]
    assert retained[0]["resources_released"] is False
    p.rows[0]["label"] = "other"
    with pytest.raises(ValueError, match="ownership|label"):
        a("/api/v1/instances/terminate", {"selector": {"ById": [456]}})
    with pytest.raises(ValueError):
        a("/api/v1/instances/terminate", {"selector": {"ById": [999]}})
    with pytest.raises(ValueError):
        a("/api/v1/instances/rent", {})


def test_unsuccessful_destroy_does_not_acknowledge_missing_row():
    p = Provider()
    p.rows = [{"id": 456, "label": TAG, "actual_status": "running"}]

    def api(method, path, data=None, params=None):
        if method == "DELETE":
            return {"success": False}
        return p(method, path, data, params)

    a = adapter(api)
    from training.remote_deadline import owned

    owned(spec(), a)
    with pytest.raises(RuntimeError):
        a("/api/v1/instances/terminate", {"selector": {"ById": [456]}})
    p.rows = []
    assert owned(spec(), a) == []


def test_guard_proof_cannot_substitute_cloudrift_or_another_provider():
    from training.remote_deadline import verify_run

    run = {
        "event": "workflow_dispatch",
        "head_branch": "main",
        "path": ".github/workflows/vast-deadline.yml",
        "status": "in_progress",
        "display_title": f"Vast deadline: {TAG} @ 5000",
    }
    jobs = {
        "jobs": [
            {
                "name": "Independent Vast.ai deadline",
                "status": "in_progress",
                "steps": [
                    {"name": "Arm deadline", "conclusion": "success"},
                    {"name": "Guard Vast.ai deadline", "status": "in_progress"},
                ],
            }
        ]
    }
    assert (
        verify_run(
            run, jobs, tag=TAG, now=1000, minimum_seconds=2000, provider="vast"
        ).maximum_end_at
        == 5000
    )
    with pytest.raises(ValueError):
        verify_run(run, jobs, tag=TAG, now=1000, minimum_seconds=2000)
    bad = deepcopy(run)
    bad.update(
        path=".github/workflows/gpu-deadline.yml",
        display_title=f"GPU deadline: {TAG} @ 5000",
    )
    with pytest.raises(ValueError):
        verify_run(bad, jobs, tag=TAG, now=1000, minimum_seconds=2000, provider="vast")


def test_remote_vast_client_has_no_rental_route_and_sanitizes_transport_errors(
    monkeypatch,
):
    import urllib.error

    from training import remote_vast_deadline as remote

    monkeypatch.setenv("VAST_API_KEY", "credential-marker-never-logged")

    def raw(method, path, data=None, params=None):
        raise urllib.error.URLError("credential-marker-never-logged")

    monkeypatch.setattr(remote, "VastClient", lambda key: raw)
    a = remote.client(TAG)
    with pytest.raises(ValueError, match="rental"):
        a("/api/v1/instances/rent", {})
    from training.remote_deadline import owned

    with pytest.raises(RuntimeError) as caught:
        owned(spec(), a)
    assert str(caught.value) == "Vast.ai guard request failed"
    assert "credential-marker" not in str(caught.value)


def test_vast_main_arms_only_on_main_and_uses_only_inventory(
    monkeypatch, tmp_path, capsys
):
    import json
    import sys

    from training import remote_deadline as remote
    from training import remote_vast_deadline as vast

    p = Provider()
    monkeypatch.setattr(vast, "client", lambda tag: adapter(p))
    monkeypatch.setenv("GITHUB_REPOSITORY", "ayutaz/voxelshogi")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    monkeypatch.setenv("RENTAL_TAG", TAG)
    monkeypatch.setenv("MAXIMUM_END_AT", "5000")
    monkeypatch.setattr(remote.time, "time", lambda: 1000)
    # arm's default clock is bound at import, so substitute only that clock.
    actual_arm = remote.arm
    monkeypatch.setattr(
        remote, "arm", lambda s, a: actual_arm(s, a, clock=lambda: 1000)
    )
    state = tmp_path / "arm.json"
    monkeypatch.setattr(sys, "argv", ["remote_vast", "arm", "--state", str(state)])
    remote.main(provider="vast")
    assert json.loads(state.read_text())["tag"] == TAG
    assert json.loads(capsys.readouterr().out)["maximum_end_at"] == 5000
    assert all(method == "GET" for method, *_ in p.calls)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/feature")
    with pytest.raises(SystemExit):
        remote.main(provider="vast")


def test_vast_workflow_uses_main_environment_no_artifacts_and_only_step_secret():
    from pathlib import Path

    workflow = (
        Path(__file__).resolve().parents[2] / ".github/workflows/vast-deadline.yml"
    ).read_text()
    assert "github.ref == 'refs/heads/main'" in workflow
    assert "environment: gpu-control" in workflow and "contents: read" in workflow
    assert "workflow_dispatch:" in workflow and "pull_request:" not in workflow
    assert "cancel-in-progress: false" in workflow and "upload-artifact" not in workflow
    assert workflow.count("VAST_API_KEY: ${{ secrets.VAST_API_KEY }}") == 2
    assert "persist-credentials: false" in workflow


def test_delete_requires_a_previously_observed_owned_id():
    p = Provider()
    p.rows = [{"id": 456, "label": TAG, "actual_status": "running"}]
    with pytest.raises(ValueError, match="previously owned"):
        adapter(p)("/api/v1/instances/terminate", {"selector": {"ById": [456]}})
    assert not any(method == "DELETE" for method, *_ in p.calls)
