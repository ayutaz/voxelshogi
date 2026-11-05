"""Hand-counted USD200 reallocations, no provider or paid work."""

from copy import deepcopy

import pytest

from training.tests.test_research_budget import ledger


def extended_ledger():
    from training.research_budget import activate_extension

    value = ledger()
    value["reservations"] = [
        {"task": "earlier-work", "maximum_usd": 61},
        {"task": "phase5-evaluation", "maximum_usd": 38},
    ]
    value.update(reserved_total_usd=99, remaining_unreserved_usd=1)
    value = activate_extension(value)
    value["reservations"].append({"task": "phase5-evaluation", "maximum_usd": 57})
    value.update(reserved_total_usd=156, remaining_unreserved_usd=44)
    value["research_allocation_basis"] = "existing activation to200"
    value["research_allocation_events"] = [{"basis": "existing activation to200"}]
    return value


def evidence():
    return {
        "source_commit": "b" * 40,
        "purpose": "phase6-execution",
        "estimate_maximum_usd": 2,
        "reference": "existing USD200 goal1-6; first priced operator probe2USD; no new approval or rental",
    }


def test_phase6_receives_only_unused_allocation_without_changing_total_or_history():
    from training.research_budget import budget_limits, reallocate_for_phase6

    before = extended_ledger()
    original = deepcopy(before)
    result = reallocate_for_phase6(before, phase5_limit_usd=95, evidence=evidence())
    assert before == original
    assert budget_limits(result) == (200, {"phase5": 95, "phase6": 44})
    assert (
        result["reserved_total_usd"] == 156 and result["remaining_unreserved_usd"] == 44
    )
    assert result["reservations"] == original["reservations"]
    assert (
        result["research_allocation_events"][:-1]
        == original["research_allocation_events"]
    )
    assert result["conditional_gpu_budget"] == original["conditional_gpu_budget"]
    assert result["research_allocation_rebalance"]["prior_reservation_count"] == 3
    assert result["research_allocation_events"][-1]["from"] == {
        "phase5": 138,
        "phase6": 1,
    }
    assert result["research_allocation_events"][-1]["to"] == {
        "phase5": 95,
        "phase6": 44,
    }


def test_later_reservations_keep_the_historical_prefix_and_both_caps():
    from training.research_budget import budget_limits, reallocate_for_phase6

    value = reallocate_for_phase6(
        extended_ledger(), phase5_limit_usd=95, evidence=evidence()
    )
    value["reservations"].append({"task": "phase6-operators", "maximum_usd": 2.75})
    value.update(reserved_total_usd=158.75, remaining_unreserved_usd=41.25)
    assert budget_limits(value) == (200, {"phase5": 95, "phase6": 44})
    value["reservations"].append({"task": "phase5-data", "maximum_usd": 1})
    value.update(reserved_total_usd=159.75, remaining_unreserved_usd=40.25)
    with pytest.raises(ValueError):
        budget_limits(value)


def test_phase6_cap_is_independent_of_global200():
    from training.research_budget import budget_limits, reallocate_for_phase6

    value = reallocate_for_phase6(
        extended_ledger(), phase5_limit_usd=100, evidence=evidence()
    )
    assert value["research_allocations_usd"] == {"phase5": 100, "phase6": 39}
    value["reservations"].append({"task": "phase6-training", "maximum_usd": 40})
    value.update(reserved_total_usd=196, remaining_unreserved_usd=4)
    with pytest.raises(ValueError):
        budget_limits(value)


@pytest.mark.parametrize(
    "change",
    [
        "prefix",
        "count",
        "caps",
        "caps-total",
        "total",
        "activation",
        "evidence",
        "counters",
        "marker",
    ],
)
def test_changed_history_or_unbound_allocations_are_rejected(change):
    from training.research_budget import budget_limits, reallocate_for_phase6

    value = reallocate_for_phase6(
        extended_ledger(), phase5_limit_usd=95, evidence=evidence()
    )
    if change == "prefix":
        value["reservations"][0]["tag"] = "changed-but-same-cost"
    elif change == "count":
        value["research_allocation_rebalance"]["prior_reservation_count"] = 0
    elif change == "caps":
        value["research_allocations_usd"] = {"phase5": 96, "phase6": 43}
    elif change == "caps-total":
        value["research_allocations_usd"]["phase6"] = 45
        value["research_allocation_rebalance"]["allocations_usd"]["phase6"] = 45
    elif change == "total":
        value["approved_total_usd"] = 201
    elif change == "activation":
        del value["conditional_gpu_budget"]
    elif change == "evidence":
        value["research_allocation_rebalance"]["evidence"]["reference"] = "changed"
    elif change == "counters":
        value["reserved_total_usd"] = 155
    else:
        del value["research_allocation_rebalance"]
    with pytest.raises(ValueError):
        budget_limits(value)


@pytest.mark.parametrize("limit", [True, 94, 139, 95.0, -1])
def test_reallocation_cannot_lower_phase5_below_existing_reservations_or_expand139(
    limit,
):
    from training.research_budget import reallocate_for_phase6

    value = extended_ledger()
    before = deepcopy(value)
    with pytest.raises(ValueError):
        reallocate_for_phase6(value, phase5_limit_usd=limit, evidence=evidence())
    assert value == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_commit", "bad"),
        ("purpose", "other"),
        ("estimate_maximum_usd", True),
        ("estimate_maximum_usd", 45),
        ("estimate_maximum_usd", float("nan")),
        ("reference", ""),
    ],
)
def test_bounded_concrete_evidence_is_required(field, value):
    from training.research_budget import reallocate_for_phase6

    proof = evidence()
    proof[field] = value
    with pytest.raises(ValueError):
        reallocate_for_phase6(extended_ledger(), phase5_limit_usd=95, evidence=proof)


def test_basic100_and_repeated_reallocation_cannot_gain_a_new_extension():
    from training.research_budget import reallocate_for_phase6

    with pytest.raises(ValueError):
        reallocate_for_phase6(ledger(), phase5_limit_usd=95, evidence=evidence())
    value = reallocate_for_phase6(
        extended_ledger(), phase5_limit_usd=95, evidence=evidence()
    )
    with pytest.raises(ValueError):
        reallocate_for_phase6(value, phase5_limit_usd=96, evidence=evidence())


def test_live_limits_do_not_alias_the_historical_binding():
    from training.research_budget import budget_limits, reallocate_for_phase6

    value = reallocate_for_phase6(
        extended_ledger(), phase5_limit_usd=95, evidence=evidence()
    )
    value["research_allocations_usd"].update(phase5=100, phase6=39)
    assert value["research_allocation_rebalance"]["allocations_usd"] == {
        "phase5": 95,
        "phase6": 44,
    }
    with pytest.raises(ValueError):
        budget_limits(value)
