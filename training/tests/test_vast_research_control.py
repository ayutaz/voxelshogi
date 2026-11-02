"""Research-purpose and deadline admission on fake Vast accounts only."""

import json

import pytest

from training.remote_deadline import Deadline
from training.tests.test_research_rental_control import setup as research_setup
from training.tests.test_vast_rental_control import Provider


def setup(tmp_path):
    from training.vast_research_control import ResearchVastRental

    old, _, budget, path = research_setup(tmp_path)
    p = json.loads(path.read_text())
    for k in ["sku", "datacenter", "with_public_ip"]:
        p.pop(k)
    p.update(
        schema="voxelshogi-vast-research-plan-v1",
        offer_id=123,
        disk_gb=80,
        maximum_seconds=3600,
        maximum_usd=1,
        estimated_seconds=300,
    )
    path.write_text(json.dumps(p))
    api = Provider()
    control = ResearchVastRental(
        old.state,
        api,
        tag="voxelshogi-phase5-eval-pilot",
        budget=budget,
        plan=path,
        workload=old.workload,
        phase="phase5",
        clock=lambda: 1000,
        source_check=lambda _: None,
        other_provider_idle=lambda: None,
        remote_guard=lambda **kw: Deadline(kw["tag"], 4600),
    )
    return control, api, budget, path


def test_research_purpose_reservation_and_two_guards_precede_paid_create(tmp_path):
    c, api, budget, _ = setup(tmp_path)

    def ready():
        assert not any(method == "PUT" for method, *_ in api.calls)
        assert (
            json.loads(budget.read_text())["reservations"][-1]["task"]
            == "phase5-evaluation"
        )

    result = c.rent(ready)
    assert result == {"instance_ids": [456], "stop_at": 3640}
    d = json.loads((c.state / "deadline.json").read_text())
    assert d["maximum_end_at"] == 4540 and d["hourly_usd"] == 0.58
    assert Deadline(c.tag, 4600).stop_at < d["stop_at"]
    assert json.loads(budget.read_text())["reserved_total_usd"] == 62
    request = next(data for method, path, data, _ in api.calls if method == "PUT")
    assert request["disk"] == 80 and request["label"] == "voxelshogi-phase5-eval-pilot"
    assert request["runtype"] == "ssh_direct" and request["cancel_unavail"] is True
    assert "HF_TOKEN" not in str(request) and "CLOUDRIFT_API_KEY" not in str(request)
    assert c.attach_key() == {"success": True}
    assert c.terminate()["complete"] is True


@pytest.mark.parametrize(
    "change",
    [
        {"schema": "voxelshogi-m6-rental-approval-v1"},
        {"purpose": "m6-main"},
        {"offer_id": True},
        {"offer_id": 0},
        {"disk_gb": 81},
        {"maximum_seconds": 18000},
        {"maximum_usd": 4},
        {"maximum_hourly_usd": 2},
    ],
)
def test_invalid_research_scope_never_reads_provider_or_spends(tmp_path, change):
    c, api, budget, path = setup(tmp_path)
    p = json.loads(path.read_text())
    p.update(change)
    path.write_text(json.dumps(p))
    before = budget.read_bytes()
    with pytest.raises(ValueError):
        c.rent(lambda: None)
    assert api.calls == [] and budget.read_bytes() == before


def test_zero_balance_wrong_offer_and_cross_provider_conflict_do_not_reserve(tmp_path):
    c, api, budget, _ = setup(tmp_path)
    before = budget.read_bytes()
    api.balance = 0
    with pytest.raises(ValueError, match="balance"):
        c.rent(lambda: None)
    assert (
        budget.read_bytes() == before and not (c.state / "rent-request.json").exists()
    )
    api.balance = 10
    api.offer["id"] = 321
    with pytest.raises(ValueError, match="offer"):
        c.rent(lambda: None)
    assert budget.read_bytes() == before

    def conflict():
        raise ValueError("CloudRift owned rental")

    c.other_provider_idle = conflict
    with pytest.raises(ValueError, match="CloudRift"):
        c.rent(lambda: None)
    assert not any(method == "PUT" for method, *_ in api.calls)


def test_live_guard_and_clean_source_are_required_before_vast_access(tmp_path):
    c, api, budget, _ = setup(tmp_path)
    before = budget.read_bytes()
    c.remote_guard = None
    with pytest.raises(ValueError, match="independent"):
        c.rent(lambda: None)
    assert api.calls == [] and budget.read_bytes() == before

    def dirty(_):
        raise ValueError("dirty source")

    c.source_check = dirty
    with pytest.raises(ValueError, match="dirty"):
        c.rent(lambda: None)
    assert api.calls == []


def test_absolute_window_is_rechecked_after_preflight_and_immediately_before_put(
    tmp_path,
):
    c, api, budget, _ = setup(tmp_path)
    now = [1000]
    c.clock = lambda: now[0]

    def delay(method, path, data=None, params=None):
        result = api(method, path, data, params)
        if path.endswith("bundles"):
            now[0] += 2400
        return result

    c.api = delay
    before = budget.read_bytes()
    with pytest.raises(ValueError, match="expired|insufficient"):
        c.rent(lambda: None)
    assert budget.read_bytes() == before and not any(
        method == "PUT" for method, *_ in api.calls
    )
    c.api = api
    now[0] = 1000

    def suspended():
        now[0] = 4000

    with pytest.raises(ValueError, match="expired|insufficient"):
        c.rent(suspended)
    assert not any(method == "PUT" for method, *_ in api.calls)
    assert json.loads(budget.read_text())["reserved_total_usd"] == 62


def test_unknown_create_response_is_audited_by_label_and_cannot_restart(tmp_path):
    c, api, _, path = setup(tmp_path)
    api.fail_create = True
    with pytest.raises(TimeoutError):
        c.rent(lambda: None)
    before = sum(method == "PUT" for method, *_ in api.calls)
    with pytest.raises(ValueError, match="existing|request"):
        c.rent(lambda: None)
    assert sum(method == "PUT" for method, *_ in api.calls) == before == 1
    path.unlink()
    c.workload.unlink()
    assert c.terminate()["complete"] is True


@pytest.mark.parametrize("task,amount", [("other", 39), ("phase5-selfplay", 20)])
def test_new_vast_plan_keeps_shared_project_and_phase_reservations(
    tmp_path, task, amount
):
    c, api, budget, _ = setup(tmp_path)
    m = json.loads(budget.read_text())
    m["reservations"].append({"task": task, "maximum_usd": amount})
    budget.write_text(json.dumps(m))
    before = budget.read_bytes()
    with pytest.raises(ValueError, match="budget"):
        c.rent(lambda: None)
    assert budget.read_bytes() == before and not any(
        method == "PUT" for method, *_ in api.calls
    )


def test_cli_binds_the_actual_vast_workflow_instead_of_cloudrift(
    monkeypatch, tmp_path, capsys
):
    import sys

    from training import remote_deadline as remote
    from training import research_rental_control as common
    from training import vast_rental_control as vast
    from training import vast_research_control as module

    root = tmp_path
    state = root / "runs/control"
    state.mkdir(parents=True)
    monkeypatch.setattr(common, "ROOT", root)
    monkeypatch.setattr(vast, "project_key", lambda *args: "fixture")
    monkeypatch.setattr(vast, "VastClient", lambda key: Provider())
    calls = []
    monkeypatch.setattr(
        remote,
        "live_guard",
        lambda run_id, **kwargs: (
            calls.append((run_id, kwargs)) or Deadline(kwargs["tag"], 4600)
        ),
    )

    class Control:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

        def rent(self, ready):
            self.kwargs["remote_guard"](
                tag="voxelshogi-phase5-control", now=1000, minimum_seconds=2000
            )
            return {"complete": False}

    monkeypatch.setattr(module, "ResearchVastRental", Control)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "control",
            str(state),
            "rent",
            "--plan",
            str(root / "runs/plan.json"),
            "--workload",
            str(root / "runs/workload.json"),
            "--guard-run",
            "123",
        ],
    )
    module.main()
    assert calls == [
        (
            123,
            {
                "provider": "vast",
                "tag": "voxelshogi-phase5-control",
                "now": 1000,
                "minimum_seconds": 2000,
            },
        )
    ]
    assert json.loads(capsys.readouterr().out) == {"complete": False}
