"""Bounded free-public storage planning, no model bytes or Hub traffic."""

import hashlib
import json
from copy import deepcopy

import pytest

from training.tests.test_state_upload_extension import extend, prior


def legacy():
    return extend(prior())


def migrate(value):
    from training.state_upload_budget import extend_research_upload_budget

    return extend_research_upload_budget(
        value,
        source_commit="a" * 40,
        scope_reference="standing research/state publication scope and free public HF capacity",
    )


def test_capacity_is_derived_from_actual_m_parameters_and_all_planned_save_points():
    from training.state_upload_budget import research_capacity_plan

    plan = research_capacity_plan(legacy())
    # Independent arithmetic: two FP32 model+AdamW copies = 24 bytes/parameter.
    assert plan == {
        "schema": "voxelshogi-research-state-capacity-plan-v1",
        "parameter_counts": {
            "full": 25_783_688,
            "axial": 25_783_688,
            "geometry": 26_098_120,
            "cnn": 28_606_344,
        },
        "planned_runs": 14,
        "archives_per_run": 3,
        "tensor_bytes_per_parameter": 24,
        "overhead_bytes_per_archive": 67_108_864,
        "maximum_bytes_per_archive": 753_661_120,
        "historical_reserved_bytes": 1_044_495_137,
        "estimated_total_bytes": 32_698_262_177,
        "self_limit_bytes": 34_359_738_368,
    }


def test_v3_keeps_original_v2_and_v1_evidence_and_every_reservation():
    from training.state_upload_budget import upload_budget_limit

    before = legacy()
    value = migrate(before)
    assert before == legacy()
    assert upload_budget_limit(before) == 2_147_483_648
    assert upload_budget_limit(value) == 34_359_738_368
    assert value["schema"] == "voxelshogi-state-upload-budget-v3"
    assert value["reservations"] == before["reservations"]
    assert value["reservations"] is not before["reservations"]
    assert value["extension"] == before["extension"]
    record = value["research_extension"]
    encoded = json.dumps(
        before, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    assert record["previous_ledger_sha256"] == hashlib.sha256(encoded).hexdigest()
    assert record["prior_reservation_count"] == 2
    assert record["source_commit"] == "a" * 40
    assert value["extension"] is not before["extension"]


@pytest.mark.parametrize(
    "change",
    [
        "prefix",
        "old-proof",
        "old-count",
        "estimate",
        "bytes-per-param",
        "archive-count",
        "self-limit",
        "source",
        "reference",
        "missing-proof",
        "extra-proof",
    ],
)
def test_v3_rejects_tampered_history_plan_or_scope(change):
    from training.state_upload_budget import upload_budget_limit

    value = migrate(legacy())
    if change == "prefix":
        value["reservations"][0]["maximum_bytes"] -= 1
    elif change == "old-proof":
        value["extension"]["approval_reference"] = "different history"
    elif change == "old-count":
        value["research_extension"]["prior_reservation_count"] = True
    elif change == "estimate":
        value["research_extension"]["plan"]["estimated_total_bytes"] -= 1
    elif change == "bytes-per-param":
        value["research_extension"]["plan"]["tensor_bytes_per_parameter"] = 16
    elif change == "archive-count":
        value["research_extension"]["plan"]["archives_per_run"] = 2
    elif change == "self-limit":
        value["approved_maximum_new_bytes"] += 1
    elif change == "source":
        value["research_extension"]["source_commit"] = "main"
    elif change == "reference":
        value["research_extension"]["scope_reference"] = ""
    elif change == "missing-proof":
        del value["research_extension"]
    else:
        value["research_extension"]["paid_storage"] = True
    before = deepcopy(value)
    with pytest.raises(ValueError):
        upload_budget_limit(value)
    assert value == before


def test_only_existing_v2_can_migrate_once_and_scope_must_be_reviewable():
    from training.state_upload_budget import extend_research_upload_budget

    for value in (prior(), migrate(legacy()), {}):
        with pytest.raises(ValueError):
            migrate(value)
    for source, reference in (
        ("main", "scope"),
        ("a" * 40, " "),
        ("a" * 40, "x" * 1025),
    ):
        with pytest.raises(ValueError):
            extend_research_upload_budget(
                legacy(), source_commit=source, scope_reference=reference
            )


def test_v3_can_reserve_new_real_bytes_without_resetting_the_historical_prefix(
    tmp_path,
):
    from training.state_release import reserve_state_upload
    from training.state_upload_budget import upload_budget_limit

    path = tmp_path / "budget.json"
    value = migrate(legacy())
    path.write_text(json.dumps(value))
    reserve_state_upload(path, {"files": [{"bytes": 753_661_120}]})
    after = json.loads(path.read_text())
    assert upload_budget_limit(after) == 34_359_738_368
    assert after["reservations"][:2] == value["reservations"]
    assert len(after["reservations"]) == 3
    assert after["research_extension"] == value["research_extension"]
    snapshot = path.read_bytes()
    with pytest.raises(ValueError, match="exceeded"):
        reserve_state_upload(path, {"files": [{"bytes": 32_561_582_112}]})
    assert path.read_bytes() == snapshot
    with pytest.raises(ValueError, match="reserved"):
        reserve_state_upload(path, {"files": [{"bytes": 753_661_120}]})
    assert path.read_bytes() == snapshot
