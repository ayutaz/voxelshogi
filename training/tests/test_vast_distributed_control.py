"""Four-GPU quotes and reservation ordering on fake provider accounts only."""

import json

import pytest

from training.remote_deadline import Deadline
from training.tests.test_vast_rental_control import offer
from training.tests.test_vast_research_control import setup as single_setup
from training.vast_distributed_control import DistributedVastRental, quote_four_gpu


def four_offer():
    value = offer()
    value.update(
        num_gpus=4,
        cpu_ram=196608,
        cpu_cores_effective=32,
        dph_base=2.24,
        storage_total_cost=0.02,
        dph_total=2.26,
        inet_up_cost=0.00390625,
        inet_down_cost=0.00390625,
    )
    return value


def setup(tmp_path):
    old, api, budget, path = single_setup(tmp_path)
    plan = json.loads(path.read_text())
    plan.update(
        schema="voxelshogi-vast-distributed-plan-v1",
        purpose="phase5-distributed",
        maximum_hourly_usd=3,
        maximum_transfer_usd=1,
        maximum_usd=4,
    )
    path.write_text(json.dumps(plan))
    api.offer = four_offer()
    control = DistributedVastRental(
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
        remote_guard=lambda **kw: Deadline(kw["tag"], 4600),
    )
    return control, api, budget, path


def test_four_gpu_quote_counts_shared_disk_once_and_prices_both_directions():
    quote = quote_four_gpu(four_offer())
    assert quote["num_gpus"] == 4 and quote["disk_gb"] == 80
    assert quote["hourly_usd"] == pytest.approx(2.26)
    # Fixed conservative estimate: 40GB download + 10GB upload, $4/1024GB.
    assert quote["estimated_transfer_usd"] == pytest.approx(0.1953125)
    assert quote["transfer_reserve_usd"] == 1
    assert quote["inet_up_usd_per_gb"] == quote["inet_down_usd_per_gb"] == 0.00390625
    lower_total = four_offer()
    lower_total["dph_total"] = 2.1
    assert quote_four_gpu(lower_total)["hourly_usd"] == pytest.approx(2.26)


@pytest.mark.parametrize(
    "change",
    [
        {"num_gpus": 1},
        {"num_gpus": 2},
        {"gpu_name": "RTX 4090"},
        {"cpu_cores_effective": 20},
        {"cpu_ram": 90000},
        {"gpu_ram": 24000},
        {"verification": "deverified"},
        {"reliability2": 0.98},
        {"driver_version": "570.1"},
        {"cuda_max_good": 12.9},
        {"direct_port_count": 0},
        {"disk_space": 79},
        {"dph_base": 3.01},
        {"dph_total": 3.01},
        {"dph_total": True},
        {"dph_base": False},
        {"inet_up_cost": 0.011},
        {"inet_down_cost": 0.011},
        {"inet_up_cost": float("nan")},
        {"inet_down_cost": -0.1},
    ],
)
def test_changed_hardware_or_price_is_rejected(change):
    with pytest.raises(ValueError):
        quote_four_gpu(four_offer() | change)


def test_four_gpu_reserves_compute_plus_network_before_guard_and_paid_create(tmp_path):
    control, api, budget, _ = setup(tmp_path)
    original = json.loads(budget.read_text())["reservations"]

    def ready():
        assert not any(method == "PUT" for method, *_ in api.calls)
        ledger = json.loads(budget.read_text())
        assert ledger["reservations"][:-1] == original
        assert ledger["reservations"][-1]["maximum_usd"] == 4
        assert ledger["reservations"][-1]["task"] == "phase5-distributed"

    result = control.rent(ready)
    assert result["instance_ids"] == [456]
    assert json.loads(budget.read_text())["reserved_total_usd"] == 65
    query = next(
        data for _, endpoint, data, _ in api.calls if endpoint == "/api/v0/bundles"
    )
    assert query["ask_contract_id"] == {"eq": 123}
    assert query["num_gpus"] == {"eq": 4}
    assert query["allocated_storage"] == 80
    preflight = json.loads((control.state / "preflight.json").read_text())
    assert preflight["num_gpus"] == 4 and preflight["maximum_usd"] == 4
    assert control.terminate()["complete"] is True


@pytest.mark.parametrize(
    "change",
    [
        {"schema": "voxelshogi-vast-research-plan-v1"},
        {"purpose": "phase5-evaluation"},
        {"maximum_usd": 3},
        {"maximum_transfer_usd": 0},
        {"maximum_transfer_usd": 2},
        {"maximum_hourly_usd": 4},
    ],
)
def test_profile_or_unreserved_transfer_cost_fails_before_provider_access(
    tmp_path, change
):
    control, api, budget, path = setup(tmp_path)
    original = budget.read_bytes()
    path.write_text(json.dumps(json.loads(path.read_text()) | change))
    with pytest.raises(ValueError):
        control.rent(lambda: None)
    assert api.calls == [] and budget.read_bytes() == original


def test_credit_must_cover_the_transfer_reserve_as_well_as_compute(tmp_path):
    control, api, budget, _ = setup(tmp_path)
    before = budget.read_bytes()
    api.credit = 3.0  # Covers $2.26 compute, fails its additional $1 reserve.
    with pytest.raises(ValueError, match="credit"):
        control.rent(lambda: None)
    assert budget.read_bytes() == before and not any(m == "PUT" for m, *_ in api.calls)


@pytest.mark.parametrize("task,amount", [("other", 36), ("phase5-selfplay", 34)])
def test_compute_only_fit_cannot_ignore_network_in_shared_or_phase_cap(
    tmp_path, task, amount
):
    control, api, budget, _ = setup(tmp_path)
    ledger = json.loads(budget.read_text())
    ledger["reservations"].append({"task": task, "maximum_usd": amount})
    budget.write_text(json.dumps(ledger))
    before = budget.read_bytes()
    with pytest.raises(ValueError, match="budget"):
        control.rent(lambda: None)
    assert budget.read_bytes() == before and not any(m == "PUT" for m, *_ in api.calls)


def test_uncertain_paid_create_is_audited_and_never_repeated(tmp_path):
    control, api, _, _ = setup(tmp_path)
    api.fail_create = True
    with pytest.raises(TimeoutError):
        control.rent(lambda: None)
    with pytest.raises(ValueError, match="existing|request"):
        control.rent(lambda: None)
    assert sum(method == "PUT" for method, *_ in api.calls) == 1
    assert control.terminate()["complete"] is True


def test_distributed_cli_starts_its_matching_backup_guard(
    monkeypatch, tmp_path, capsys
):
    import subprocess
    import sys
    from types import SimpleNamespace

    from training import (
        rental_control,
        research_rental_control,
        vast_rental_control,
        vast_research_control,
    )

    state = tmp_path / "runs/control"
    state.mkdir(parents=True)
    monkeypatch.setattr(research_rental_control, "ROOT", tmp_path)
    monkeypatch.setattr(vast_rental_control, "project_key", lambda *args: "fixture")
    calls = []
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda command, **kw: calls.append(command) or SimpleNamespace(pid=123),
    )
    monkeypatch.setattr(rental_control, "wait_for_guard", lambda *args, **kw: None)

    class Control:
        GUARD_MODULE = "training.vast_distributed_control"

        def __init__(self, *args, **kwargs):
            pass

        def rent(self, ready):
            (state / "deadline.json").write_text(json.dumps({"maximum_end_at": 4600}))
            ready()
            return {"complete": False}

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "distributed-control",
            str(state),
            "rent",
            "--plan",
            str(tmp_path / "runs/plan.json"),
            "--workload",
            str(tmp_path / "runs/workload.json"),
            "--guard-run",
            "123",
        ],
    )
    vast_research_control.main(control_type=Control)
    assert calls[0][1:3] == ["-m", "training.vast_distributed_control"]
    assert "guard" in calls[0] and str(state) in calls[0]
    assert json.loads(capsys.readouterr().out) == {"complete": False}
