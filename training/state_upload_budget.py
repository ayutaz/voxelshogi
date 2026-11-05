"""Pure, explicitly approved capacity migration; never writes or uploads state."""

import hashlib
import json
import re
from copy import deepcopy

BASIC_MAXIMUM = 1024**3
EXTENDED_MAXIMUM = 2 * 1024**3
RESEARCH_MAXIMUM = 32 * 1024**3


def _prefix_hash(rows):
    return hashlib.sha256(
        json.dumps(
            rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def _approval_reference(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 1024


def upload_budget_limit(value):
    """Validate the fixed cap and preserve the extension's historical prefix."""
    if type(value) is not dict:
        raise ValueError("invalid training-state upload budget")
    rows = value.get("reservations")
    if type(rows) is not list or any(
        type(row) is not dict
        or set(row) != {"release_sha256", "maximum_bytes"}
        or not isinstance(row["release_sha256"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", row["release_sha256"])
        or type(row["maximum_bytes"]) is not int
        or row["maximum_bytes"] <= 0
        for row in rows
    ):
        raise ValueError("invalid training-state upload reservations")
    if len({row["release_sha256"] for row in rows}) != len(rows):
        raise ValueError("duplicate historical training-state upload reservation")
    maximum = value.get("approved_maximum_new_bytes")
    if type(maximum) is not int:
        raise ValueError("invalid training-state upload budget")
    if value.get("schema") == "voxelshogi-state-upload-budget-v1":
        if maximum != BASIC_MAXIMUM or "extension" in value:
            raise ValueError("unapproved training-state upload budget")
    elif value.get("schema") == "voxelshogi-state-upload-budget-v2":
        record = value.get("extension")
        if (
            maximum != EXTENDED_MAXIMUM
            or type(record) is not dict
            or set(record)
            != {
                "schema",
                "previous_maximum_new_bytes",
                "prior_reservation_count",
                "prior_reservations_sha256",
                "approval_reference",
            }
            or record["schema"] != "voxelshogi-state-upload-extension-v1"
            or type(record["previous_maximum_new_bytes"]) is not int
            or record["previous_maximum_new_bytes"] != BASIC_MAXIMUM
            or type(record["prior_reservation_count"]) is not int
            or not 1 <= record["prior_reservation_count"] <= len(rows)
            or not _approval_reference(record["approval_reference"])
        ):
            raise ValueError("unapproved training-state upload extension")
        prefix = rows[: record["prior_reservation_count"]]
        if (
            _prefix_hash(prefix) != record["prior_reservations_sha256"]
            or sum(row["maximum_bytes"] for row in prefix) > BASIC_MAXIMUM
        ):
            raise ValueError("historical training-state reservation prefix differs")
    elif value.get("schema") == "voxelshogi-state-upload-budget-v3":
        _validate_research_extension(value)
    else:
        raise ValueError("unknown training-state upload budget schema")
    if sum(row["maximum_bytes"] for row in rows) > maximum:
        raise ValueError("training-state upload budget exceeded")
    return maximum


def extend_upload_budget(value, *, approved=False, approval_reference=None):
    """Caller must hold real user approval; this pure transition does not grant it."""
    if approved is not True or not _approval_reference(approval_reference):
        raise ValueError("explicit capacity approval and reference are required")
    if upload_budget_limit(value) != BASIC_MAXIMUM or not value["reservations"]:
        raise ValueError("extension requires the existing nonempty legacy ledger")
    result = deepcopy(value)
    result.update(
        schema="voxelshogi-state-upload-budget-v2",
        approved_maximum_new_bytes=EXTENDED_MAXIMUM,
        extension={
            "schema": "voxelshogi-state-upload-extension-v1",
            "previous_maximum_new_bytes": BASIC_MAXIMUM,
            "prior_reservation_count": len(value["reservations"]),
            "prior_reservations_sha256": _prefix_hash(value["reservations"]),
            "approval_reference": approval_reference,
        },
    )
    upload_budget_limit(result)
    return result


def research_capacity_plan(value):
    """A bounded estimate for 2 pilot + 12 main runs, including one retry each.

    Two full FP32 model/AdamW checkpoints cost 2 * (4 + 8) bytes/parameter.
    RNG, AdamW step counters, history and metadata receive 64MiB/archive.
    This is a self-limit inside existing free-public publication scope, never
    a purchase, measured archive size, or authorization for extra paid storage.
    """
    from export.research_contract import (
        ARCHITECTURES,
        architecture_config,
        parameter_count,
    )

    if upload_budget_limit(value) != EXTENDED_MAXIMUM:
        raise ValueError("research capacity planning requires the existing v2 ledger")
    counts = {
        name: parameter_count(architecture_config(name)) for name in ARCHITECTURES
    }
    archive_bytes = 24 * max(counts.values()) + 64 * 1024**2
    historical = sum(row["maximum_bytes"] for row in value["reservations"])
    estimate = historical + 14 * 3 * archive_bytes
    if estimate > RESEARCH_MAXIMUM:
        raise ValueError(
            "research state estimate exceeds the bounded free-public self-limit"
        )
    return {
        "schema": "voxelshogi-research-state-capacity-plan-v1",
        "parameter_counts": counts,
        "planned_runs": 14,
        "archives_per_run": 3,
        "tensor_bytes_per_parameter": 24,
        "overhead_bytes_per_archive": 64 * 1024**2,
        "maximum_bytes_per_archive": archive_bytes,
        "historical_reserved_bytes": historical,
        "estimated_total_bytes": estimate,
        "self_limit_bytes": RESEARCH_MAXIMUM,
    }


def _validate_research_extension(value):
    record = value.get("research_extension")
    if (
        value["approved_maximum_new_bytes"] != RESEARCH_MAXIMUM
        or type(record) is not dict
        or set(record)
        != {
            "schema",
            "prior_reservation_count",
            "previous_ledger_sha256",
            "source_commit",
            "scope_reference",
            "plan",
        }
        or record["schema"] != "voxelshogi-research-state-upload-extension-v1"
        or type(record["prior_reservation_count"]) is not int
        or not 1 <= record["prior_reservation_count"] <= len(value["reservations"])
        or not isinstance(record["source_commit"], str)
        or re.fullmatch(r"[0-9a-f]{40}", record["source_commit"]) is None
        or not _approval_reference(record["scope_reference"])
    ):
        raise ValueError("invalid research training-state capacity extension")
    previous = deepcopy(value)
    del previous["research_extension"]
    previous.update(
        schema="voxelshogi-state-upload-budget-v2",
        approved_maximum_new_bytes=EXTENDED_MAXIMUM,
        reservations=previous["reservations"][: record["prior_reservation_count"]],
    )
    if (
        _prefix_hash(previous) != record["previous_ledger_sha256"]
        or research_capacity_plan(previous) != record["plan"]
    ):
        raise ValueError("research capacity historical ledger or estimate differs")


def extend_research_upload_budget(value, *, source_commit, scope_reference):
    """Pure one-time migration under the standing research publication scope."""
    if (
        not isinstance(source_commit, str)
        or re.fullmatch(r"[0-9a-f]{40}", source_commit) is None
        or not _approval_reference(scope_reference)
    ):
        raise ValueError(
            "immutable source and existing publication scope reference are required"
        )
    plan = research_capacity_plan(value)
    if (
        not value["reservations"]
        or value["schema"] != "voxelshogi-state-upload-budget-v2"
    ):
        raise ValueError("research migration requires the existing nonempty v2 ledger")
    result = deepcopy(value)
    result.update(
        schema="voxelshogi-state-upload-budget-v3",
        approved_maximum_new_bytes=RESEARCH_MAXIMUM,
        research_extension={
            "schema": "voxelshogi-research-state-upload-extension-v1",
            "prior_reservation_count": len(value["reservations"]),
            "previous_ledger_sha256": _prefix_hash(value),
            "source_commit": source_commit,
            "scope_reference": scope_reference,
            "plan": plan,
        },
    )
    upload_budget_limit(result)
    return result
