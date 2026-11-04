"""Approved conditional extension; pure metadata, never rent a resource."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest


def ledger():
    return {
        "approved_total_usd": 100,
        "research_allocations_usd": {"phase5": 38, "phase6": 1},
        "reserved_total_usd": 89.75,
        "remaining_unreserved_usd": 10.25,
        "reservations": [
            {"task": "earlier-work", "maximum_usd": 87},
            {"task": "phase5-evaluation", "maximum_usd": 2.75},
        ],
    }


def test_basic_budget_stays_100_until_explicit_activation():
    from training.research_budget import budget_limits

    value = ledger()
    before = deepcopy(value)
    assert budget_limits(value) == (100, {"phase5": 38, "phase6": 1})
    assert value == before


def test_activation_preserves_all_reservations_and_binds_reviewed_shortage():
    from training.research_budget import activate_extension, budget_limits

    before = ledger()
    value = activate_extension(before)
    assert before == ledger()
    assert value["approved_total_usd"] == 200
    assert value["research_allocations_usd"] == {"phase5": 138, "phase6": 1}
    assert value["reserved_total_usd"] == 89.75
    assert value["remaining_unreserved_usd"] == 110.25
    assert value["reservations"] == before["reservations"]
    assert budget_limits(value) == (200, {"phase5": 138, "phase6": 1})
    evidence = (
        Path(__file__).resolve().parents[2]
        / "docs/experiments/p53-budget-extension-2026-11-04.json"
    )
    assert (
        value["conditional_gpu_budget"]["evidence_sha256"]
        == hashlib.sha256(evidence.read_bytes()).hexdigest()
    )
    report = json.loads(evidence.read_text())
    assert report["forecast_total_usd"] == 101.25
    assert (
        report["prior_reserved_usd"]
        + sum(x["maximum_usd"] for x in report["remaining_units"])
        == 101.25
    )
    assert report["shortage_usd"] == 1.25


@pytest.mark.parametrize(
    "change", ["missing-proof", "hash", "extra", "total", "phase5", "phase6", "partial"]
)
def test_partial_or_tampered_activation_is_rejected(change):
    from training.research_budget import activate_extension, budget_limits

    value = activate_extension(ledger())
    if change == "missing-proof":
        del value["conditional_gpu_budget"]
    elif change == "hash":
        value["conditional_gpu_budget"]["evidence_sha256"] = "0" * 64
    elif change == "extra":
        value["conditional_gpu_budget"]["extra_usd"] = 200
    elif change == "total":
        value["approved_total_usd"] = 201
    elif change == "phase5":
        value["research_allocations_usd"]["phase5"] = 139
    elif change == "phase6":
        value["research_allocations_usd"]["phase6"] = 101
    else:
        value["approved_total_usd"] = 100
        value["research_allocations_usd"] = {"phase5": 38, "phase6": 1}
    with pytest.raises(ValueError):
        budget_limits(value)


@pytest.mark.parametrize(
    "change", ["already", "sum", "negative", "nan", "boolean", "prior-allocation"]
)
def test_activation_refuses_invalid_prior_ledger(change):
    from training.research_budget import activate_extension

    value = ledger()
    if change == "already":
        value = activate_extension(value)
    elif change == "sum":
        value["reserved_total_usd"] = 88
    elif change == "negative":
        value["reservations"][0]["maximum_usd"] = -1
    elif change == "nan":
        value["reservations"][0]["maximum_usd"] = float("nan")
    elif change == "boolean":
        value["reservations"][0]["maximum_usd"] = True
    else:
        value["research_allocations_usd"] = {"phase5": 37, "phase6": 2}
    before = deepcopy(value)
    with pytest.raises(ValueError):
        activate_extension(value)
    assert value.keys() == before.keys()


def test_reservation_after_activation_can_cross_100_but_still_has_phase_cap(tmp_path):
    from training.research_budget import activate_extension
    from training.tests.test_research_rental_control import setup

    control, api, path, _ = setup(tmp_path)
    value = ledger()
    value["reservations"] = [
        {"task": "earlier-work", "maximum_usd": 61},
        {"task": "phase5-evaluation", "maximum_usd": 38},
    ]
    value.update(reserved_total_usd=99, remaining_unreserved_usd=1)
    path.write_text(json.dumps(activate_extension(value)))
    control.reserve()
    actual = json.loads(path.read_text())
    assert actual["reserved_total_usd"] == 103
    assert actual["remaining_unreserved_usd"] == 97
    assert not api.calls
    actual["reservations"].append({"task": "phase5-data", "maximum_usd": 93})
    path.write_text(json.dumps(actual))
    control.tag = "voxelshogi-phase5-another"
    # Existing phase5:38+4+93=135; another4 would exceed138.
    with pytest.raises(ValueError, match="budget"):
        control.reserve()
    assert json.loads(path.read_text()) == actual


def test_extension_enforces_total_200_independently_of_phase5(tmp_path):
    from training.research_budget import activate_extension
    from training.tests.test_research_rental_control import setup

    control, api, path, _ = setup(tmp_path)
    value = ledger()
    value["reservations"] = [{"task": "earlier-work", "maximum_usd": 99}]
    value.update(reserved_total_usd=99, remaining_unreserved_usd=1)
    value = activate_extension(value)
    value["reservations"].append({"task": "phase5-data", "maximum_usd": 99})
    path.write_text(json.dumps(value))
    before = path.read_bytes()
    with pytest.raises(ValueError, match="budget"):
        control.reserve()
    assert path.read_bytes() == before and not api.calls
