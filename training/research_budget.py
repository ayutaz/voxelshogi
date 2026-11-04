"""Explicit, evidence-bound use of the user's conditional extra GPU budget."""

import hashlib
import math
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
    if (
        type(total) is not int
        or type(allocations) is not dict
        or any(type(value) is not int for value in allocations.values())
    ):
        raise ValueError("invalid shared project budget")
    if total == 100 and allocations == BASIC_ALLOCATIONS and marker is None:
        return 100, dict(BASIC_ALLOCATIONS)
    if (
        total == 200
        and allocations == EXTENDED_ALLOCATIONS
        and marker == extension_record()
    ):
        return 200, dict(EXTENDED_ALLOCATIONS)
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
