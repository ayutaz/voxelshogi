"""Explicit, evidence-bound use of the user's conditional extra GPU budget."""

import hashlib
import json
import math
import re
from copy import deepcopy
from pathlib import Path

BASIC_ALLOCATIONS = {"phase5": 38, "phase6": 1}
EXTENDED_ALLOCATIONS = {"phase5": 138, "phase6": 1}
EVIDENCE = (
    Path(__file__).resolve().parents[1]
    / "docs/experiments/p53-budget-extension-2026-11-04.json"
)


def extension_record():
    return {
        "schema": "voxelshogi-conditional-gpu-budget-activation-v1",
        "extra_usd": 100,
        "evidence_sha256": hashlib.sha256(EVIDENCE.read_bytes()).hexdigest(),
    }


def budget_limits(ledger):
    total = ledger.get("approved_total_usd")
    allocations = ledger.get("research_allocations_usd")
    marker = ledger.get("conditional_gpu_budget")
    rebalance = ledger.get("research_allocation_rebalance")
    if (
        type(total) is not int
        or type(allocations) is not dict
        or any(type(value) is not int for value in allocations.values())
    ):
        raise ValueError("invalid shared project budget")
    if (
        total == 100
        and allocations == BASIC_ALLOCATIONS
        and marker is None
        and rebalance is None
    ):
        return 100, dict(BASIC_ALLOCATIONS)
    if (
        total == 200
        and allocations == EXTENDED_ALLOCATIONS
        and marker == extension_record()
        and rebalance is None
    ):
        return 200, dict(EXTENDED_ALLOCATIONS)
    if total == 200 and rebalance is not None:
        if marker != extension_record():
            raise ValueError(
                "reallocation cannot activate or replace the budget approval"
            )
        _validate_rebalance(ledger, rebalance)
        return 200, dict(allocations)
    raise ValueError("project budget and explicit conditional activation differ")


def activate_extension(ledger):
    """Pure transition only; caller locks/persists after CI and ownership checks."""
    if budget_limits(ledger)[0] != 100:
        raise ValueError("conditional budget already activated")
    rows = ledger.get("reservations")
    if type(rows) is not list or any(
        type(row) is not dict
        or type(row.get("maximum_usd")) not in (int, float)
        or not math.isfinite(row["maximum_usd"])
        or row["maximum_usd"] < 0
        for row in rows
    ):
        raise ValueError("invalid prior budget reservations")
    reserved = sum(row["maximum_usd"] for row in rows)
    if (
        ledger.get("reserved_total_usd") != reserved
        or ledger.get("remaining_unreserved_usd") != 100 - reserved
        or not 0 <= reserved <= 100
    ):
        raise ValueError("prior budget counters differ")
    result = deepcopy(ledger)
    result.update(
        approved_total_usd=200,
        research_allocations_usd=dict(EXTENDED_ALLOCATIONS),
        conditional_gpu_budget=extension_record(),
        remaining_unreserved_usd=200 - reserved,
    )
    return result


def _hash(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def _rows(ledger):
    rows = ledger.get("reservations")
    if (
        type(rows) is not list
        or not rows
        or any(
            type(row) is not dict
            or type(row.get("maximum_usd")) not in (int, float)
            or not math.isfinite(row["maximum_usd"])
            or row["maximum_usd"] < 0
            for row in rows
        )
    ):
        raise ValueError("invalid reallocated research budget reservations")
    reserved = sum(row["maximum_usd"] for row in rows)
    if (
        not 0 <= reserved <= 200
        or type(ledger.get("reserved_total_usd")) not in (int, float)
        or type(ledger.get("remaining_unreserved_usd")) not in (int, float)
        or ledger["reserved_total_usd"] != reserved
        or ledger.get("remaining_unreserved_usd") != 200 - reserved
    ):
        raise ValueError("reallocated research budget counters differ")
    return rows, reserved


def _spent(rows, phase):
    return sum(
        row["maximum_usd"]
        for row in rows
        if str(row.get("task", "")).startswith(phase + "-")
    )


def _evidence(value, *, maximum):
    if (
        type(value) is not dict
        or set(value)
        != {"source_commit", "purpose", "estimate_maximum_usd", "reference"}
        or not isinstance(value["source_commit"], str)
        or re.fullmatch(r"[0-9a-f]{40}", value["source_commit"]) is None
        or value["purpose"] != "phase6-execution"
        or type(value["estimate_maximum_usd"]) not in (int, float)
        or not math.isfinite(value["estimate_maximum_usd"])
        or not 0 < value["estimate_maximum_usd"] <= maximum
        or not isinstance(value["reference"], str)
        or not value["reference"].strip()
        or len(value["reference"]) > 1024
    ):
        raise ValueError("bounded Phase6 budget evidence required")


def _validate_rebalance(ledger, record):
    allocations = ledger["research_allocations_usd"]
    if (
        set(allocations) != {"phase5", "phase6"}
        or allocations == EXTENDED_ALLOCATIONS
        or any(type(v) is not int or v <= 0 for v in allocations.values())
        or sum(allocations.values()) != 139
        or type(record) is not dict
        or set(record)
        != {
            "schema",
            "previous_allocations_usd",
            "allocations_usd",
            "prior_reservation_count",
            "prior_reservations_sha256",
            "previous_reserved_total_usd",
            "evidence",
            "evidence_sha256",
        }
        or record["schema"] != "voxelshogi-research-allocation-rebalance-v1"
        or record["previous_allocations_usd"] != EXTENDED_ALLOCATIONS
        or record["allocations_usd"] != allocations
    ):
        raise ValueError("invalid reallocated research budget limits or binding")
    rows, _ = _rows(ledger)
    count = record["prior_reservation_count"]
    if type(count) is not int or not 1 <= count <= len(rows):
        raise ValueError("invalid prior research budget prefix count")
    prefix = rows[:count]
    previous = sum(row["maximum_usd"] for row in prefix)
    if (
        _hash(prefix) != record["prior_reservations_sha256"]
        or type(record["previous_reserved_total_usd"]) not in (int, float)
        or record["previous_reserved_total_usd"] != previous
        or any(
            _spent(prefix, phase) > cap for phase, cap in EXTENDED_ALLOCATIONS.items()
        )
        or any(_spent(rows, phase) > cap for phase, cap in allocations.items())
    ):
        raise ValueError("research budget history changed or phase exceeded")
    _evidence(record["evidence"], maximum=min(allocations["phase6"], 200 - previous))
    if _hash(record["evidence"]) != record["evidence_sha256"]:
        raise ValueError("research budget evidence hash differs")


def reallocate_for_phase6(ledger, *, phase5_limit_usd, evidence):
    """Pure one-time allocation inside the already activated USD200, no spend.

    Caller persists only after CI and workload/resource audit. No old reservation,
    approval, invoice estimate or counter is reduced, replaced or activated here.
    """
    if (
        budget_limits(ledger) != (200, EXTENDED_ALLOCATIONS)
        or ledger.get("research_allocation_rebalance") is not None
    ):
        raise ValueError("reallocation requires the existing activated budget")
    rows, reserved = _rows(ledger)
    if type(phase5_limit_usd) is not int or not 1 <= phase5_limit_usd < 139:
        raise ValueError("invalid research allocation within139")
    allocations = {"phase5": phase5_limit_usd, "phase6": 139 - phase5_limit_usd}
    if allocations == EXTENDED_ALLOCATIONS or any(
        _spent(rows, phase) > cap for phase, cap in allocations.items()
    ):
        raise ValueError("research allocation cannot reduce a reserved phase")
    _evidence(evidence, maximum=min(allocations["phase6"], 200 - reserved))
    rebalanced = deepcopy(ledger)
    record = {
        "schema": "voxelshogi-research-allocation-rebalance-v1",
        "previous_allocations_usd": dict(EXTENDED_ALLOCATIONS),
        "allocations_usd": dict(allocations),
        "prior_reservation_count": len(rows),
        "prior_reservations_sha256": _hash(rows),
        "previous_reserved_total_usd": reserved,
        "evidence": deepcopy(evidence),
        "evidence_sha256": _hash(evidence),
    }
    rebalanced.update(
        research_allocations_usd=dict(allocations), research_allocation_rebalance=record
    )
    events = rebalanced.setdefault("research_allocation_events", [])
    if type(events) is not list:
        raise ValueError("research allocation history must be preserved")
    events.append(
        {
            "from": dict(EXTENDED_ALLOCATIONS),
            "to": dict(allocations),
            "basis": evidence["reference"],
            "source_commit": evidence["source_commit"],
            "evidence_sha256": _hash(evidence),
            "previous_basis": rebalanced.get("research_allocation_basis"),
        }
    )
    rebalanced["research_allocation_basis"] = evidence["reference"]
    budget_limits(rebalanced)
    return rebalanced
