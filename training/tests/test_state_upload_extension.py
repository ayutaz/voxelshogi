"""Explicit capacity migration keeps every opaque historical reservation."""

import hashlib
import json
from copy import deepcopy

import pytest


def prior():
    return {
        "schema": "voxelshogi-state-upload-budget-v1",
        "approved_maximum_new_bytes": 1_073_741_824,
        "reservations": [
            {"release_sha256": "a" * 64, "maximum_bytes": 700_000_000},
            {"release_sha256": "b" * 64, "maximum_bytes": 344_495_137},
        ],
    }


def extend(value):
    from training.state_upload_budget import extend_upload_budget

    return extend_upload_budget(
        value, approved=True, approval_reference="synthetic approval fixture"
    )


def test_legacy_budget_stays_one_gib_and_does_not_mutate():
    from training.state_upload_budget import upload_budget_limit

    value = prior()
    assert upload_budget_limit(value) == 1_073_741_824
    assert value == prior()


def test_migration_is_explicit_and_preserves_the_original_reservation_prefix():
    from training.state_upload_budget import upload_budget_limit

    before = prior()
    actual = extend(before)
    assert before == prior()
    assert actual["schema"] == "voxelshogi-state-upload-budget-v2"
    assert actual["approved_maximum_new_bytes"] == 2_147_483_648
    assert actual["reservations"] == before["reservations"]
    assert actual["reservations"] is not before["reservations"]
    assert upload_budget_limit(actual) == 2_147_483_648
    assert sum(r["maximum_bytes"] for r in actual["reservations"]) == 1_044_495_137
    record = actual["extension"]
    assert record["prior_reservation_count"] == 2
    independently_encoded = json.dumps(
        before["reservations"],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    assert (
        record["prior_reservations_sha256"]
        == hashlib.sha256(independently_encoded).hexdigest()
    )
    assert record["approval_reference"] == "synthetic approval fixture"


@pytest.mark.parametrize("approved", [False, None, 1, "yes"])
def test_missing_or_nonboolean_approval_does_not_allow_migration(approved):
    from training.state_upload_budget import extend_upload_budget

    before = prior()
    with pytest.raises(ValueError, match="approval"):
        extend_upload_budget(before, approved=approved, approval_reference="fixture")
    assert before == prior()


@pytest.mark.parametrize("reference", ["", " ", None, 42, "x" * 1025])
def test_a_nonempty_reviewable_approval_reference_is_required(reference):
    from training.state_upload_budget import extend_upload_budget

    with pytest.raises(ValueError, match="approval"):
        extend_upload_budget(prior(), approved=True, approval_reference=reference)


@pytest.mark.parametrize(
    "change",
    [
        "missing-proof",
        "wrong-old-limit",
        "wrong-new-limit",
        "missing-prefix",
        "changed-prefix",
        "reordered-prefix",
        "boolean-count",
        "shortened-count",
        "foreign-proof-field",
        "unknown-schema",
        "v1-raised",
        "already-extended",
    ],
)
def test_partial_tampered_or_repeated_extension_is_rejected(change):
    from training.state_upload_budget import extend_upload_budget, upload_budget_limit

    value = extend(prior())
    if change == "missing-proof":
        del value["extension"]
    elif change == "wrong-old-limit":
        value["extension"]["previous_maximum_new_bytes"] = 2_147_483_648
    elif change == "wrong-new-limit":
        value["approved_maximum_new_bytes"] = 3_221_225_472
    elif change == "missing-prefix":
        value["reservations"].pop()
    elif change == "changed-prefix":
        value["reservations"][0]["maximum_bytes"] -= 1
    elif change == "reordered-prefix":
        value["reservations"].reverse()
    elif change == "boolean-count":
        value["extension"]["prior_reservation_count"] = True
    elif change == "shortened-count":
        value["extension"]["prior_reservation_count"] = 1
    elif change == "foreign-proof-field":
        value["extension"]["reset_allowed"] = True
    elif change == "unknown-schema":
        value["schema"] = "voxelshogi-state-upload-budget-v3"
    elif change == "v1-raised":
        value = prior()
        value["approved_maximum_new_bytes"] = 2_147_483_648
    else:
        with pytest.raises(ValueError):
            extend_upload_budget(value, approved=True, approval_reference="fixture")
        return
    before = deepcopy(value)
    with pytest.raises(ValueError):
        upload_budget_limit(value)
    assert value == before


def test_version_two_reserves_new_bytes_and_still_refuses_overflow_and_duplicates(
    tmp_path,
):
    from training.state_release import reserve_state_upload

    path = tmp_path / "budget.json"
    contents = extend(prior())
    path.write_text(json.dumps(contents))
    plan = {"files": [{"bytes": 67_108_864}]}
    reserve_state_upload(path, plan)
    actual = json.loads(path.read_text())
    assert actual["reservations"][:2] == prior()["reservations"]
    assert len(actual["reservations"]) == 3
    assert sum(r["maximum_bytes"] for r in actual["reservations"]) == 1_111_604_001
    assert actual["extension"] == contents["extension"]
    unchanged = path.read_bytes()
    with pytest.raises(ValueError, match="reserved"):
        reserve_state_upload(path, plan)
    assert path.read_bytes() == unchanged
    with pytest.raises(ValueError, match="exceeded"):
        reserve_state_upload(path, {"files": [{"bytes": 1_035_879_648}]})
    assert path.read_bytes() == unchanged


def test_legacy_capacity_does_not_silently_gain_space(tmp_path):
    from training.state_release import reserve_state_upload

    path = tmp_path / "budget.json"
    path.write_text(json.dumps(prior()))
    unchanged = path.read_bytes()
    with pytest.raises(ValueError, match="exceeded"):
        reserve_state_upload(path, {"files": [{"bytes": 67_108_864}]})
    assert path.read_bytes() == unchanged


@pytest.mark.parametrize("change", ["empty", "duplicate", "boolean", "overspent"])
def test_invalid_or_empty_legacy_history_cannot_be_migrated(change):
    value = prior()
    if change == "empty":
        value["reservations"] = []
    elif change == "duplicate":
        value["reservations"].append(deepcopy(value["reservations"][0]))
    elif change == "boolean":
        value["reservations"][0]["maximum_bytes"] = True
    else:
        value["reservations"][0]["maximum_bytes"] = 1_073_741_824
    before = deepcopy(value)
    with pytest.raises(ValueError):
        extend(value)
    assert value == before


def test_a_tampered_extension_is_rejected_before_the_ledger_is_written(tmp_path):
    from training.state_release import reserve_state_upload

    value = extend(prior())
    value["reservations"][0]["maximum_bytes"] -= 1
    path = tmp_path / "budget.json"
    path.write_text(json.dumps(value))
    before = path.read_bytes()
    with pytest.raises(ValueError):
        reserve_state_upload(path, {"files": [{"bytes": 1}]})
    assert path.read_bytes() == before
