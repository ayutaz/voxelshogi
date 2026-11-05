"""The Phase6 priced profile uses fake providers and the same shared ledger."""

import json

import pytest

from training.remote_deadline import Deadline
from training.tests.test_research_reallocation import evidence, extended_ledger
from training.tests.test_vast_evaluation_control import setup as evaluation_setup


def setup(tmp_path):
    from training.research_budget import reallocate_for_phase6
    from training.vast_phase6_control import Phase6VastRental

    old, api, budget, plan = evaluation_setup(tmp_path)
    value = json.loads(plan.read_text())
    value.update(schema="voxelshogi-vast-phase6-plan-v1", purpose="phase6-operators")
    plan.write_text(json.dumps(value))
    budget.write_text(
        json.dumps(
            reallocate_for_phase6(
                extended_ledger(), phase5_limit_usd=95, evidence=evidence()
            )
        )
    )
    control = Phase6VastRental(
        old.state,
        api,
        tag="voxelshogi-phase6-operators-pilot",
        budget=budget,
        plan=plan,
        workload=old.workload,
        phase="phase6",
        clock=lambda: 1000,
        source_check=lambda _: None,
        other_provider_idle=lambda: None,
        remote_guard=lambda **kw: Deadline(kw["tag"], 11800),
    )
    return control, api, budget, plan


def test_phase6_compute_and_traffic_are_reserved_before_any_paid_request(tmp_path):
    control, api, budget, _ = setup(tmp_path)
    prior = json.loads(budget.read_text())["reservations"]

    def ready():
        value = json.loads(budget.read_text())
        assert value["reservations"][:-1] == prior
        assert value["reservations"][-1]["task"] == "phase6-operators"
        assert value["reservations"][-1]["maximum_usd"] == 2.75
        assert (
            value["reserved_total_usd"] == 158.75
            and value["remaining_unreserved_usd"] == 41.25
        )
        assert not any(method == "PUT" for method, *_ in api.calls)

    assert control.rent(ready)["instance_ids"] == [456]
    assert control.GUARD_MODULE == "training.vast_phase6_control"
    assert control.terminate()["complete"] is True


@pytest.mark.parametrize(
    "purpose", ["phase6-operators", "phase6-training", "phase6-publication"]
)
def test_only_existing_phase6_purposes_are_supported(tmp_path, purpose):
    control, _, _, path = setup(tmp_path)
    plan = json.loads(path.read_text())
    plan["purpose"] = purpose
    path.write_text(json.dumps(plan))
    assert control.read_plan()["purpose"] == purpose


@pytest.mark.parametrize(
    "change",
    [
        {"purpose": "phase5-evaluation"},
        {"purpose": "phase5-data"},
        {"maximum_transfer_usd": 0},
        {"maximum_transfer_usd": 1},
        {"maximum_transfer_usd": 0, "maximum_usd": 2.25},
        {"maximum_transfer_usd": 1, "maximum_usd": 3.25},
        {"maximum_hourly_usd": 1},
        {"maximum_usd": 2.25},
    ],
)
def test_wrong_scope_or_unreserved_cost_fails_before_provider_access(tmp_path, change):
    control, api, budget, path = setup(tmp_path)
    plan = json.loads(path.read_text())
    plan.update(change)
    path.write_text(json.dumps(plan))
    before = budget.read_bytes()
    with pytest.raises(ValueError):
        control.rent(lambda: None)
    assert before == budget.read_bytes() and not api.calls
