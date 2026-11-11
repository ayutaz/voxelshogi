"""Timeout recovery through explicit fake ports, never actual HF operations."""

from types import SimpleNamespace

import pytest

from training.tests.test_hub_release import release


class Api:
    def __init__(self):
        self.exists, self.gated, self.disabled = False, False, False
        self.calls, self.failures = [], {}
        self.private = False

    def call(self, name, value=None):
        self.calls.append(name)
        remaining = self.failures.get(name, 0)
        if remaining:
            self.failures[name] -= 1
            raise TimeoutError("opaque network diagnostic must not enter events")
        return value

    def repo_exists(self, **_):
        return self.call("exists", self.exists)

    def repo_info(self, **_):
        return self.call(
            "info",
            SimpleNamespace(private=self.private, gated=self.gated, sha="b" * 40),
        )

    def community_disabled(self, **_):
        return self.call("community-read", self.disabled)

    def create_repo(self, **_):
        self.exists = True
        return self.call("create")

    def update_repo_settings(self, **_):
        self.gated = "manual"
        return self.call("settings")

    def disable_community(self, **_):
        self.disabled = True
        return self.call("community-write")

    def upload_folder(self, **_):
        return self.call("upload")


def wrapper(api, *, clock=lambda: 100, stop=lambda: False, deadline=200):
    from training.hub_recovery import RecoveryApi

    events, waits = [], []
    recovery = RecoveryApi(
        api,
        deadline=deadline,
        transient_errors=(TimeoutError,),
        clock=clock,
        wait=waits.append,
        stop_requested=stop,
        observe=events.append,
    )
    return recovery, waits, events


@pytest.mark.parametrize("method", ["exists", "info", "community-read"])
def test_reads_retry_twice_then_stop_with_fixed_hand_count(method):
    api = Api()
    api.failures[method] = 3
    recovery, waits, events = wrapper(api)
    action = {
        "exists": recovery.repo_exists,
        "info": recovery.repo_info,
        "community-read": recovery.community_disabled,
    }[method]
    with pytest.raises(TimeoutError):
        action(repo_id="voxelshogi/test", repo_type="dataset")
    assert api.calls == [method] * 3
    assert waits == [2, 4]
    assert [e["attempt"] for e in events] == [1, 2, 3]
    assert all(set(e) == {"operation", "attempt"} for e in events)


@pytest.mark.parametrize(
    "mutation,read",
    [("create", "exists"), ("settings", "info"), ("community-write", "community-read")],
)
def test_lost_mutation_response_is_read_back_and_never_repeated(mutation, read):
    api = Api()
    api.failures[mutation] = 1
    recovery, waits, _ = wrapper(api)
    action = {
        "create": recovery.create_repo,
        "settings": recovery.update_repo_settings,
        "community-write": recovery.disable_community,
    }[mutation]
    action(
        repo_id="voxelshogi/test",
        repo_type="dataset",
        **({"gated": "manual"} if mutation == "settings" else {}),
    )
    assert api.calls == [mutation, read] and waits == []


def test_uncertain_create_that_did_not_happen_does_not_create_again():
    api = Api()

    def lost(**_):
        api.calls.append("create")
        raise TimeoutError()

    api.create_repo = lost
    recovery, _, _ = wrapper(api)
    with pytest.raises(TimeoutError):
        recovery.create_repo(repo_id="voxelshogi/test", repo_type="dataset")
    assert api.calls == ["create", "exists"]


def test_existing_policy_harness_still_checks_private_gating_community_and_order(
    tmp_path,
):
    from training.hub_release import create_release_repository

    api = Api()
    api.failures = {"create": 1, "info": 1, "settings": 1, "community-write": 1}
    recovery, waits, _ = wrapper(api)
    info = create_release_repository(
        release(tmp_path), recovery, execute=True, system="linux"
    )
    assert info.gated == "manual" and not info.private and api.disabled
    assert (
        api.calls.count("create")
        == api.calls.count("settings")
        == api.calls.count("community-write")
        == 1
    )
    assert waits == [2] and "upload" not in api.calls
    api.private = True
    with pytest.raises(ValueError, match="private"):
        create_release_repository(
            release(tmp_path), recovery, execute=True, system="linux"
        )


def test_upload_timeout_propagates_without_retry_or_success_claim():
    api = Api()
    api.failures["upload"] = 1
    recovery, waits, _ = wrapper(api)
    with pytest.raises(TimeoutError):
        recovery.upload_folder(repo_id="voxelshogi/test")
    assert api.calls == ["upload"] and waits == []


@pytest.mark.parametrize(
    "clock,stop", [(lambda: 200, lambda: False), (lambda: 100, lambda: True)]
)
def test_deadline_or_stop_prevents_all_network(clock, stop):
    api = Api()
    recovery, _, _ = wrapper(api, clock=clock, stop=stop)
    with pytest.raises(InterruptedError):
        recovery.repo_exists(repo_id="voxelshogi/test")
    with pytest.raises(InterruptedError):
        recovery.create_repo(repo_id="voxelshogi/test", repo_type="dataset")
    assert api.calls == []


def test_read_completion_after_deadline_is_rejected_and_backoff_cannot_cross_it():
    api = Api()
    ticks = iter([100, 201])
    r, _, _ = wrapper(api, clock=lambda: next(ticks))
    with pytest.raises(InterruptedError):
        r.repo_exists()
    api = Api()
    api.failures["exists"] = 3
    r, waits, _ = wrapper(api, clock=lambda: 199)
    with pytest.raises(InterruptedError):
        r.repo_exists()
    assert waits == [] and api.calls == ["exists"]


def test_validation_error_is_not_retried():
    api = Api()

    def invalid(**_):
        raise ValueError("HTTP403, not a transport timeout")

    api.repo_info = invalid
    r, waits, _ = wrapper(api)
    with pytest.raises(ValueError):
        r.repo_info()
    assert waits == []


@pytest.mark.parametrize(
    "method,read",
    [("update_repo_settings", "info"), ("disable_community", "community-read")],
)
def test_unapplied_setting_timeout_requires_exact_readback(method, read):
    api = Api()

    def not_applied(**_):
        api.calls.append("write")
        raise TimeoutError()

    setattr(api, method, not_applied)
    recovery, _, _ = wrapper(api)
    kwargs = {"repo_id": "voxelshogi/test", "repo_type": "dataset"}
    if method == "update_repo_settings":
        kwargs["gated"] = "manual"
    with pytest.raises(TimeoutError):
        getattr(recovery, method)(**kwargs)
    assert api.calls == ["write", read]


@pytest.mark.parametrize(
    "deadline,errors",
    [
        (True, (TimeoutError,)),
        (float("nan"), (TimeoutError,)),
        (200, ()),
        (200, (ValueError,)),
    ],
)
def test_invalid_bounds_or_broad_retry_exception_are_rejected(deadline, errors):
    from training.hub_recovery import RecoveryApi

    with pytest.raises(ValueError):
        RecoveryApi(Api(), deadline=deadline, transient_errors=errors)
