"""Pure, explicitly approved capacity migration; never writes or uploads state."""

import hashlib
import json
import re
from copy import deepcopy

BASIC_MAXIMUM = 1024**3
EXTENDED_MAXIMUM = 2 * 1024**3


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
