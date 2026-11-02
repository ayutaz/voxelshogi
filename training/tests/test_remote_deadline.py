"""Independent control clocks and fake providers; never create paid resources."""

import pytest

TAG = "voxelshogi-phase5-deadline-test"


def spec():
    from training.remote_deadline import Deadline

    return Deadline(TAG, 5000)


class Provider:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.calls = []
        self.fail = False

    def __call__(self, path, data):
        self.calls.append((path, data))
        if self.fail:
            self.fail = False
            raise RuntimeError("provider unavailable")
        if path.endswith("/terminate"):
            self.rows[0].update(status="Inactive", resources_released=True)
            return {}
        assert path.endswith("/list")
        return {"instances": self.rows}


def active():
    return {
        "id": "owned",
        "tags": [TAG],
        "status": "Active",
        "resources_released": False,
    }


def test_deadline_rejects_invalid_scope_or_unbounded_window():
    from training.remote_deadline import Deadline

    for tag, end in [("unrelated", 5000), (TAG, True), (TAG, 15401), (TAG, 1100)]:
        with pytest.raises(ValueError):
            Deadline(tag, end).validate(now=1000)
    spec().validate(now=1000)


def test_arm_requires_successful_empty_owned_inventory():
    from training.remote_deadline import arm

    api = Provider([active()])
    with pytest.raises(ValueError, match="already"):
        arm(spec(), api, clock=lambda: 1000)
    api.rows = []
    assert arm(spec(), api, clock=lambda: 1000) == {
        "tag": TAG,
        "maximum_end_at": 5000,
        "armed_at": 1000,
    }
    assert api.calls[-1][1]["selector"] == {"ByTags": {"all": [TAG], "any": []}}


def test_remote_clock_terminates_at_stop_time_without_local_process(capsys):
    from training.remote_deadline import watch

    api = Provider([active()])
    now = [3700]
    pauses = []

    def pause(seconds):
        assert len(pauses) < 30, "termination never completed"
        pauses.append(seconds)
        now[0] += seconds

    result = watch(spec(), api, clock=lambda: now[0], pause=pause)
    assert result["complete"] and result["instance_ids"] == ["owned"]
    assert now[0] == 3860 and pauses == [60, 40, 60]
    assert [d for p, d in api.calls if p.endswith("/terminate")] == [
        {"selector": {"ById": ["owned"]}}
    ]
    import json

    assert json.loads(capsys.readouterr().out) == {
        "event": "termination_requested",
        "at": 3800,
        "instance_ids": ["owned"],
    }


def test_empty_inventory_is_not_early_success_and_errors_retry():
    from training.remote_deadline import watch

    now = [4090]
    api = Provider()
    api.fail = True

    def pause(seconds):
        now[0] += seconds

    result = watch(spec(), api, clock=lambda: now[0], pause=pause)
    assert result == {"complete": True, "instance_ids": [], "no_rental_observed": True}
    assert now[0] >= 5000


def test_wrong_owner_response_never_terminates():
    from training.remote_deadline import watch

    api = Provider([{**active(), "tags": ["other"]}])
    with pytest.raises(ValueError, match="ownership"):
        watch(spec(), api, clock=lambda: 4100, pause=lambda _: None)
    assert not any(p.endswith("/terminate") for p, _ in api.calls)


def test_release_must_be_confirmed_and_missing_seen_instance_is_not_success():
    from training.remote_deadline import watch

    now = [4100]
    api = Provider([active()])
    original = api.__call__
    calls = [0]

    def provider(path, data):
        if path.endswith("/terminate"):
            return {}
        calls[0] += 1
        if calls[0] == 2:
            return {"instances": []}
        if calls[0] >= 3:
            api.rows[0].update(status="Inactive", resources_released=True)
        return original(path, data)

    result = watch(
        spec(),
        provider,
        clock=lambda: now[0],
        pause=lambda x: now.__setitem__(0, now[0] + x),
    )
    assert result["complete"] and calls[0] >= 3 and now[0] > 4100


def test_live_guard_proof_binds_main_workflow_tag_deadline_and_running_step():
    from copy import deepcopy

    from training.remote_deadline import verify_run

    run = {
        "id": 123,
        "event": "workflow_dispatch",
        "head_branch": "main",
        "path": ".github/workflows/gpu-deadline.yml",
        "status": "in_progress",
        "display_title": f"GPU deadline: {TAG} @ 5000",
    }
    jobs = {
        "jobs": [
            {
                "name": "Independent CloudRift deadline",
                "status": "in_progress",
                "steps": [
                    {
                        "name": "Arm deadline",
                        "conclusion": "success",
                        "status": "completed",
                    },
                    {
                        "name": "Guard CloudRift deadline",
                        "status": "in_progress",
                        "conclusion": None,
                    },
                ],
            }
        ]
    }
    assert (
        verify_run(run, jobs, tag=TAG, now=1000, minimum_seconds=2000).maximum_end_at
        == 5000
    )
    for field, value in [
        ("event", "pull_request"),
        ("head_branch", "feat/untrusted"),
        ("path", "other.yml"),
        ("status", "completed"),
        ("display_title", "GPU deadline: other @ 5000"),
    ]:
        bad = {**run, field: value}
        with pytest.raises(ValueError):
            verify_run(bad, jobs, tag=TAG, now=1000, minimum_seconds=2000)
    for changed in ({"jobs": []}, {"jobs": [{**jobs["jobs"][0], "status": "queued"}]}):
        with pytest.raises(ValueError):
            verify_run(run, changed, tag=TAG, now=1000, minimum_seconds=2000)
    bad = deepcopy(jobs)
    bad["jobs"][0]["steps"][0]["conclusion"] = "failure"
    with pytest.raises(ValueError):
        verify_run(run, bad, tag=TAG, now=1000, minimum_seconds=2000)
    with pytest.raises(ValueError):
        verify_run(run, jobs, tag=TAG, now=2000, minimum_seconds=3500)


def test_provider_cancellation_requests_early_cleanup():
    from training.remote_deadline import watch

    api = Provider([active()])
    result = watch(
        spec(), api, clock=lambda: 1000, pause=lambda _: None, stopping=lambda: True
    )
    assert result["complete"]
    assert any(p.endswith("/terminate") for p, _ in api.calls)


def test_terminal_but_unreleased_is_retried():
    from training.remote_deadline import watch

    api = Provider([{**active(), "status": "Inactive"}])
    pauses = []

    def pause(seconds):
        pauses.append(seconds)
        api.rows[0]["resources_released"] = True

    result = watch(spec(), api, clock=lambda: 4100, pause=pause)
    assert result["complete"] and pauses == [60]


def test_cli_rejects_local_or_fork_execution_before_credentials(monkeypatch, tmp_path):
    import sys

    from training.remote_deadline import main

    monkeypatch.setattr(
        sys, "argv", ["remote_deadline", "arm", "--state", str(tmp_path / "state.json")]
    )
    monkeypatch.setenv("GITHUB_REPOSITORY", "someone/fork")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    with pytest.raises(SystemExit):
        main()


def test_http_client_uses_only_official_no_redirect_termination_transport(monkeypatch):
    import urllib.request

    from training.remote_deadline import client

    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return b'{"data":{"instances":[]}}'

    class Opener:
        def open(self, request, timeout):
            assert request.full_url == "https://api.cloudrift.ai/api/v1/instances/list"
            assert request.get_header("X-api-key") == "opaque-test-only"
            assert timeout == 40
            calls.append(request)
            return Response()

    def build(handler):
        assert issubclass(handler, urllib.request.HTTPRedirectHandler)
        assert handler().redirect_request(None, None, None, None, None, None) is None
        return Opener()

    monkeypatch.setattr(urllib.request, "build_opener", build)
    monkeypatch.setenv("CLOUDRIFT_API_KEY", "opaque-test-only")
    api = client()
    assert api("/api/v1/instances/list", {}) == {"instances": []}
    with pytest.raises(ValueError):
        api("/api/v1/instances/rent", {})
    assert len(calls) == 1


def test_live_guard_reads_authoritative_run_and_jobs(monkeypatch):
    import json
    import subprocess

    from training.remote_deadline import live_guard

    calls = []
    run = {
        "id": 123,
        "event": "workflow_dispatch",
        "head_branch": "main",
        "path": ".github/workflows/gpu-deadline.yml",
        "status": "in_progress",
        "display_title": f"GPU deadline: {TAG} @ 5000",
    }
    jobs = {
        "jobs": [
            {
                "name": "Independent CloudRift deadline",
                "status": "in_progress",
                "steps": [
                    {"name": "Arm deadline", "conclusion": "success"},
                    {"name": "Guard CloudRift deadline", "status": "in_progress"},
                ],
            }
        ]
    }

    def read(command, **kwargs):
        calls.append(command)
        assert command[:2] == ["gh", "api"]
        assert command[2].startswith("repos/ayutaz/voxelshogi/actions/runs/123")
        return json.dumps(jobs if "/jobs?" in command[2] else run)

    monkeypatch.setattr(subprocess, "check_output", read)
    assert live_guard(123, tag=TAG, now=1000, minimum_seconds=2000).tag == TAG
    assert len(calls) == 2
    with pytest.raises(ValueError):
        live_guard(True, tag=TAG, now=1000, minimum_seconds=2000)
    run["id"] = 456
    with pytest.raises(ValueError):
        live_guard(123, tag=TAG, now=1000, minimum_seconds=2000)


def test_http_errors_do_not_disclose_credentials_or_response(monkeypatch, capsys):
    import urllib.error
    import urllib.request

    from training.remote_deadline import client

    class Opener:
        def open(self, request, timeout):
            raise urllib.error.URLError("opaque-sensitive-provider-error")

    monkeypatch.setattr(urllib.request, "build_opener", lambda _: Opener())
    monkeypatch.setenv("CLOUDRIFT_API_KEY", "opaque-sensitive-provider-key")
    with pytest.raises(RuntimeError) as error:
        client()("/api/v1/instances/list", {})
    assert str(error.value) == "CloudRift guard request failed"
    assert capsys.readouterr().out == ""
