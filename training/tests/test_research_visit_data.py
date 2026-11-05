"""Hand-authored selection handoff; no engine, NumPy arrays or model on Mac."""

from copy import deepcopy

import pytest

from training.evaluation_v2 import fingerprint


def audit_fixture():
    rows = [
        {
            "id": name,
            "family": f"{i:064x}",
            "input": f"{i + 100:064x}",
            "value_kind": "bootstrap-v1",
            "ply": 32,
        }
        for i, name in enumerate(("t0", "t1", "v0", "v1", "x0", "x1"))
    ]
    selected = {"train": [0, 1], "val": [2, 3], "test": [4, 5]}
    return {
        "schema": "voxelshogi-research-selfplay-corpus-audit-v1",
        "source_manifest_sha256": "a" * 64,
        "source_protocol_sha256": "b" * 64,
        "source_protection_sha256": "c" * 64,
        "screen_config_sha256": "d" * 64,
        "metadata": rows,
        "family_partition": {
            r["family"]: split
            for split, indices in selected.items()
            for i in indices
            for r in [rows[i]]
        },
        "admission": {
            "usable_for_pilot": True,
            "selected_ids": {
                s: [rows[i]["id"] for i in indices] for s, indices in selected.items()
            },
            "indices_by_split": selected,
            "rows_by_split": {"train": 2, "val": 2, "test": 2},
            "selection_sha256": fingerprint(
                [
                    {**rows[i], "split": s}
                    for s, indices in selected.items()
                    for i in indices
                ]
            ),
        },
    }


def test_encoding_selects_train_val_in_frozen_order_and_never_requests_test():
    from training.research_visit_data import select_training

    audit = audit_fixture()
    selected = select_training(audit, expected_sha256=fingerprint(audit))
    assert list(selected) == ["train", "val"]
    assert [r["id"] for r in selected["train"]] == ["t0", "t1"]
    assert [r["id"] for r in selected["val"]] == ["v0", "v1"]
    assert {r["input"] for rows in selected.values() for r in rows} == {
        f"{i:064x}" for i in (100, 101, 102, 103)
    }
    with pytest.raises(ValueError, match="byte"):
        select_training(
            audit, expected_sha256=fingerprint(audit), maximum_feature_bytes=501551
        )
    assert (
        select_training(
            audit, expected_sha256=fingerprint(audit), maximum_feature_bytes=501552
        )
        == selected
    )


@pytest.mark.parametrize(
    "change",
    ["unusable", "overlap", "family", "selection", "indices", "count", "duplicate"],
)
def test_rehashed_invalid_handoff_still_fails_selection_invariants(change):
    from training.research_visit_data import select_training

    audit = audit_fixture()
    if change == "unusable":
        audit["admission"]["usable_for_pilot"] = False
    elif change == "overlap":
        audit["metadata"][4]["input"] = audit["metadata"][0]["input"]
        audit["admission"]["selection_sha256"] = fingerprint(
            [
                {**audit["metadata"][i], "split": split}
                for split, indices in audit["admission"]["indices_by_split"].items()
                for i in indices
            ]
        )
    elif change == "family":
        audit["family_partition"][audit["metadata"][0]["family"]] = "val"
    elif change == "selection":
        audit["admission"]["selected_ids"]["train"].reverse()
    elif change == "indices":
        audit["admission"]["indices_by_split"]["train"] = [0, 6]
    elif change == "count":
        audit["admission"]["rows_by_split"]["train"] = 3
    else:
        audit["metadata"][1]["id"] = "t0"
    with pytest.raises(ValueError):
        select_training(audit, expected_sha256=fingerprint(audit))


def test_stale_hash_and_noninteger_memory_limit_are_rejected():
    from training.research_visit_data import select_training

    audit = audit_fixture()
    changed = deepcopy(audit)
    changed["metadata"][0]["ply"] = 33
    with pytest.raises(ValueError, match="hash"):
        select_training(changed, expected_sha256=fingerprint(audit))
    with pytest.raises(ValueError, match="hash"):
        select_training(audit, expected_sha256="e" * 64)
    with pytest.raises(ValueError):
        select_training(
            audit, expected_sha256=fingerprint(audit), maximum_feature_bytes=True
        )


def test_actual_encoding_refuses_mac_before_accessing_source(monkeypatch, tmp_path):
    from training import research_visit_data as module

    monkeypatch.setattr(module.sys, "platform", "darwin")

    def forbidden(*args, **kwargs):
        pytest.fail("Mac refusal must happen before the source audit port")

    monkeypatch.setattr(module, "audit_selfplay_corpus", forbidden)
    with pytest.raises(ValueError, match="Linux"):
        module.encode_corpus(
            tmp_path,
            {},
            tmp_path,
            tmp_path,
            screen_sha256="d" * 64,
            expected_audit_sha256="a" * 64,
        )
