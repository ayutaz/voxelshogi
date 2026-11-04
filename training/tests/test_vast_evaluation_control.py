"""Priced single-GPU traffic is separately reserved, using fake providers."""

import json

import pytest

from training.remote_deadline import Deadline
from training.tests.test_vast_research_control import setup as original_setup
from training.vast_evaluation_control import EvaluationVastRental, quote_evaluation


def setup(tmp_path):
    old, api, budget, path = original_setup(tmp_path)
    plan = json.loads(path.read_text())
    plan.update(
        schema="voxelshogi-vast-evaluation-plan-v1",
        maximum_seconds=10800,
        estimated_seconds=7200,
        maximum_hourly_usd=0.75,
        maximum_transfer_usd=0.5,
        maximum_usd=2.75,
    )
    path.write_text(json.dumps(plan))
    api.offer.update(
        dph_base=0.5333333333333333,
        dph_total=0.5925925925925926,
        storage_total_cost=0.05925925925925925,
        inet_up_cost=0.005208333333333333,
        inet_down_cost=0.005208333333333333,
    )
    control = EvaluationVastRental(
        old.state,
        api,
        tag=old.tag,
        budget=budget,
        plan=path,
        workload=old.workload,
        phase="phase5",
        clock=lambda: 1000,
        source_check=lambda _: None,
        other_provider_idle=lambda: None,
        remote_guard=lambda **kw: Deadline(kw["tag"], 11800),
    )
    return control, api, budget, path


def test_quote_includes_disk_once_and_both_transfer_directions(tmp_path):
    control, api, _, _ = setup(tmp_path)
    q = quote_evaluation(api.offer)
    assert q["num_gpus"] == 1 and q["disk_gb"] == 80
    assert q["hourly_usd"] == pytest.approx(0.5925925925925926)
    assert q["estimated_download_gb"] == 40 and q["estimated_upload_gb"] == 10
    assert q["estimated_transfer_usd"] == pytest.approx(0.26041666666666663)
    assert q["transfer_reserve_usd"] == 0.5
    assert control.GUARD_MODULE == "training.vast_evaluation_control"


def test_each_direction_uses_its_own_per_gb_price(tmp_path):
    _, api, _, _ = setup(tmp_path)
    quote = quote_evaluation(
        api.offer | {"inet_down_cost": 0.009, "inet_up_cost": 0.004}
    )
    assert quote["estimated_transfer_usd"] == pytest.approx(0.4)  # 40*.009+10*.004


@pytest.mark.parametrize(
    "change",
    [
        {"num_gpus": 4},
        {"verification": "deverified"},
        {"reliability2": 0.98},
        {"gpu_name": "RTX 4090"},
        {"dph_total": 0.751},
        {"dph_base": 0.751},
        {"inet_down_cost": 0.011},
        {"inet_up_cost": 0.011},
        {"inet_down_cost": float("nan")},
        {"inet_up_cost": True},
        {"cpu_cores_effective": 5},
        {"driver_version": "570.1"},
    ],
)
def test_unquoted_price_hardware_and_verification_are_rejected(tmp_path, change):
    _, api, _, _ = setup(tmp_path)
    with pytest.raises(ValueError):
        quote_evaluation(api.offer | change)


def test_compute_and_network_reserved_before_guard_and_paid_create(tmp_path):
    control, api, budget, _ = setup(tmp_path)
    original = json.loads(budget.read_text())["reservations"]

    def ready():
        ledger = json.loads(budget.read_text())
        assert ledger["reservations"][:-1] == original
        assert ledger["reservations"][-1]["maximum_usd"] == 2.75
        assert not any(method == "PUT" for method, *_ in api.calls)

    assert control.rent(ready)["instance_ids"] == [456]
    assert json.loads(budget.read_text())["reserved_total_usd"] == 63.75
    query = next(data for _, path, data, _ in api.calls if path == "/api/v0/bundles")
    assert query["num_gpus"] == {"eq": 1}
    assert control.terminate()["complete"] is True


@pytest.mark.parametrize(
    "change",
    [
        {"maximum_transfer_usd": 0},
        {"maximum_transfer_usd": 1},
        {"maximum_transfer_usd": 0, "maximum_usd": 2.25},
        {"maximum_transfer_usd": 1, "maximum_usd": 3.25},
        {"maximum_usd": 2.25},
        {"maximum_hourly_usd": 1},
        {"purpose": "phase5-distributed"},
        {"schema": "voxelshogi-vast-research-plan-v1"},
    ],
)
def test_unreserved_or_different_plan_fails_before_provider_access(tmp_path, change):
    control, api, budget, path = setup(tmp_path)
    plan = json.loads(path.read_text())
    plan.update(change)
    path.write_text(json.dumps(plan))
    before = budget.read_bytes()
    with pytest.raises(ValueError):
        control.rent(lambda: None)
    assert budget.read_bytes() == before and not api.calls


def test_credit_must_cover_transfer_as_well_as_actual_compute(tmp_path):
    control, api, budget, _ = setup(tmp_path)
    api.credit = 2.0  # Actual compute ~1.78 fits; plus reserved network0.5 does not.
    before = budget.read_bytes()
    with pytest.raises(ValueError, match="credit"):
        control.rent(lambda: None)
    assert budget.read_bytes() == before and not any(
        method == "PUT" for method, *_ in api.calls
    )


@pytest.mark.parametrize("task,amount", [("other", 36.5), ("phase5-selfplay", 35.5)])
def test_transfer_reserve_is_included_in_both_shared_and_phase_limits(
    tmp_path, task, amount
):
    control, api, budget, _ = setup(tmp_path)
    ledger = json.loads(budget.read_text())
    ledger["reservations"].append({"task": task, "maximum_usd": amount})
    budget.write_text(json.dumps(ledger))
    before = budget.read_bytes()
    with pytest.raises(ValueError, match="budget"):
        control.rent(lambda: None)
    assert budget.read_bytes() == before and not any(
        method == "PUT" for method, *_ in api.calls
    )
