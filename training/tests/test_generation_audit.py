"""Small trusted-metadata ports check enumeration, not shogi interpretation."""

import pytest


def test_inventory_keeps_duplicate_split_membership_and_canonical_equivalences():
    from training.generation_audit import collect_corpus_identities

    calls = []

    def snapshot(vsfen):
        calls.append(vsfen)
        return {
            "ruleset_id": "voxelshogi-standard-v1",
            "board": [0] * 729,
            "hands": [0] * 14,
            "side": "b",
        }

    rows = [
        {"vsfen": v, "split": s, "ruleset_id": "voxelshogi-standard-v1"}
        for v, s in (
            ("board-a b - 1", "train"),
            ("board-a b - 9", "val"),
            ("board-b b - 1", "test"),
            ("board-a b - 10", "train"),
        )
    ]
    physical, inputs, report = collect_corpus_identities(
        rows, expected_rows=4, snapshot_factory=snapshot
    )
    assert physical["train"] == physical["val"]
    assert physical["train"].isdisjoint(physical["test"])
    assert inputs["train"] == inputs["val"] == inputs["test"]
    assert (
        len(calls) == 2
    )  # physical duplicate/ply cache does not drop split memberships
    assert report == {
        "rows": 4,
        "unique_physical": 2,
        "unique_inputs": 1,
        "rows_by_split": {"train": 2, "val": 1, "test": 1},
    }
    with pytest.raises(ValueError):
        collect_corpus_identities(rows[:-1], expected_rows=4, snapshot_factory=snapshot)


def test_inventory_refuses_truncated_empty_or_unexpected_corpus_before_no_leakage_claim():
    from training.generation_audit import collect_corpus_identities

    def unused(_):
        raise AssertionError("invalid row must be rejected before parsing a game")

    for rows, expected in (
        ([], 0),
        ([], 1),
        (
            [
                {
                    "vsfen": "a b - 1",
                    "split": "holdout",
                    "ruleset_id": "voxelshogi-standard-v1",
                }
            ],
            1,
        ),
    ):
        with pytest.raises(ValueError):
            collect_corpus_identities(
                rows, expected_rows=expected, snapshot_factory=unused
            )


def test_full_generation_audit_is_linux_only_before_file_or_engine_access(monkeypatch):
    from training.generation_audit import audit_generation_runs

    monkeypatch.setattr("training.generation_audit.sys.platform", "darwin")
    with pytest.raises(ValueError, match="Linux"):
        audit_generation_runs(
            {}, "absent", "absent", expected_protocol={}, protection="absent"
        )


def test_replayed_references_preserve_base_sources_and_bind_every_identity():
    from training.evaluation_v2 import fingerprint
    from training.generation_audit import include_reference_sources

    p, i = {"m4": {"1" * 64}}, {"m4": {"2" * 64}}
    references = {
        "physical": {"development/prior": {"3" * 64}},
        "model_input": {"development/prior": {"4" * 64}},
        "receipt": {
            "schema": "voxelshogi-development-references-v1",
            "verified": True,
            "sources": {
                "development/prior": {
                    "positions": 1,
                    "inputs": 1,
                    "positions_sha256": fingerprint(["3" * 64]),
                    "inputs_sha256": fingerprint(["4" * 64]),
                }
            },
        },
    }
    physical, inputs = include_reference_sources(p, i, references)
    assert physical == {"m4": {"1" * 64}, "development/prior": {"3" * 64}}
    assert inputs == {"m4": {"2" * 64}, "development/prior": {"4" * 64}}
    assert p == {"m4": {"1" * 64}} and i == {"m4": {"2" * 64}}
    references["model_input"]["development/prior"].add("5" * 64)
    with pytest.raises(ValueError):
        include_reference_sources(p, i, references)
