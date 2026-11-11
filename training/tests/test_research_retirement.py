"""Controller-side retirement order on fake clocks and owned browser jobs."""

import pytest


def snapshot(*, running=False, complete=True, finished=True):
    records = {"worker-finished.json": {"complete": complete}} if finished else {}
    if complete:
        records["complete.json"] = {"complete": True, "source_commit": "a" * 40}
        records["publication-receipt.json"] = {
            "verified": True,
            "community_disabled": True,
            "dry_run": False,
            "repo_type": "dataset",
            "repo_id": "voxelshogi/voxelshogi-research-browser-v1",
            "hub_commit": "b" * 40,
            "release_sha256": "c" * 64,
        }
    else:
        records["failure.json"] = {"complete": False, "error_type": "ReadTimeout"}
    return {
        "process": {
            "running": running,
            "pid": 7,
            "create_time": 10.5,
            "source_commit": "a" * 40,
        },
        "records": records,
    }


def test_completion_is_collected_before_early_retirement_without_waiting_deadline():
    from training.research_retirement import watch_browser

    events, pauses, saved = [], [], []
    observations = iter([snapshot(running=True), snapshot()])

    def observe():
        events.append("observe")
        return next(observations)

    def collect():
        events.append("collect")
        return snapshot()

    def retire():
        events.append("retire")
        return {"complete": True, "instances": []}

    result = watch_browser(
        observe,
        collect,
        retire,
        deadline=10000,
        clock=lambda: 100,
        wait=pauses.append,
        save=saved.append,
    )
    assert events == ["observe", "observe", "collect", "retire"]
    assert pauses == [60]
    assert result["resources_released"] and result["job_complete"]
    assert saved[-1] == result


def test_terminal_failure_diagnosis_is_preserved_and_retired_without_success_claim():
    from training.research_retirement import watch_browser

    events = []

    def retire():
        events.append("retire")
        return {"complete": True, "instances": []}

    result = watch_browser(
        lambda: snapshot(complete=False),
        lambda: snapshot(complete=False),
        retire,
        deadline=1000,
        clock=lambda: 100,
        save=lambda v: events.append(v["event"]),
    )
    assert events.index("evidence-preserved") < events.index("retire")
    assert result["resources_released"] and not result["job_complete"]


@pytest.mark.parametrize(
    "change",
    [
        lambda s: s["process"].update(running=True),
        lambda s: s["records"].pop("worker-finished.json"),
        lambda s: s["records"]["publication-receipt.json"].update(verified=False),
        lambda s: s["records"].pop("complete.json"),
        lambda s: s["process"].update(pid=8),
        lambda s: s["records"]["publication-receipt.json"].update(
            community_disabled=False
        ),
        lambda s: s["records"]["complete.json"].update(source_commit="d" * 40),
    ],
)
def test_collection_must_prove_finished_and_preserve_success_receipt(change):
    from training.research_retirement import watch_browser

    bad = snapshot()
    change(bad)
    result = watch_browser(
        lambda: snapshot(),
        lambda: bad,
        lambda: (_ for _ in ()).throw(AssertionError("unsafe retirement")),
        deadline=1000,
        clock=lambda: 100,
    )
    assert not result["resources_released"]
    assert result["event"] == "preservation-incomplete"


def test_malformed_observation_cannot_trigger_retirement():
    from training.research_retirement import watch_browser

    with pytest.raises(ValueError):
        watch_browser(
            lambda: {"process": {"running": None}, "records": {}},
            lambda: None,
            lambda: pytest.fail("retire"),
            deadline=1000,
            clock=lambda: 100,
        )


def test_live_process_at_deadline_is_not_killed_by_finish_watcher():
    from training.research_retirement import watch_browser

    result = watch_browser(
        lambda: pytest.fail("observe"),
        lambda: pytest.fail("collect"),
        lambda: pytest.fail("retire"),
        deadline=100,
        clock=lambda: 100,
    )
    assert (
        result["event"] == "independent-guard-required"
        and not result["resources_released"]
    )


def test_collect_error_preserves_unknown_state_for_existing_independent_guard():
    from training.research_retirement import watch_browser

    def collect():
        raise TimeoutError()

    with pytest.raises(TimeoutError):
        watch_browser(
            lambda: snapshot(),
            collect,
            lambda: pytest.fail("retire"),
            deadline=1000,
            clock=lambda: 100,
        )


def test_unconfirmed_deletion_is_not_retried_or_claimed_as_released():
    from training.research_retirement import watch_browser

    calls = []

    def retire():
        calls.append(1)
        return {"complete": False, "instances": [{"id": 7}]}

    result = watch_browser(
        lambda: snapshot(), lambda: snapshot(), retire, deadline=1000, clock=lambda: 100
    )
    assert calls == [1] and not result["resources_released"] and result["job_complete"]
