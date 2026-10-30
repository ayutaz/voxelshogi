"""Static metadata and independent membership counts; no engine execution."""

from copy import deepcopy

import pytest


def test_handmade_diagnostics_are_balanced_and_have_independent_terminal_oracles():
    from training.evaluation_cases import handmade_cases

    cases = handmade_cases()
    assert len(cases) == 6
    assert len({item["case"]["id"] for item in cases}) == 6
    mates = [item for item in cases if item["case"]["stratum"] == "tactical"]
    assert len(mates) == 4
    assert [item["oracle"]["result"]["Win"]["winner"] for item in mates] == [
        "Black",
        "White",
        "Black",
        "White",
    ]
    assert all(item["oracle"]["move"] == "232222" for item in (mates[0], mates[2]))
    assert all(item["oracle"]["move"] == "878888" for item in (mates[1], mates[3]))
    repetition = next(
        item for item in cases if item["case"]["id"] == "repetition-near-end"
    )
    assert len(repetition["case"]["opening"]["moves"]) == 11
    assert repetition["oracle"] == {
        "move": "211111",
        "result": {"Draw": {"reason": "Repetition"}},
    }
    assert all(item["case"]["opening"]["result"] is None for item in cases)
    # Callers must not mutate the shared fixture, even across multiple runs.
    original = deepcopy(cases)
    cases[0]["case"]["opening"]["moves"].append("changed")
    assert handmade_cases() == original


def test_membership_audit_checks_all_scored_positions_not_only_the_root():
    from training.evaluation_cases import audit_membership

    groups = {"train": {"a" * 64}, "val": {"b" * 64}, "test": {"c" * 64}}
    result = audit_membership(
        groups, {"root-1": {"d" * 64, "e" * 64}, "root-2": {"f" * 64}}
    )
    assert result["passed"] is True
    assert result["evaluation_positions"] == 3 and result["corpus_positions"] == 3
    assert result["overlaps_by_split"] == {"train": 0, "val": 0, "test": 0}
    contaminated = audit_membership(groups, {"root-1": {"d" * 64, "c" * 64}})
    assert contaminated["passed"] is False
    assert contaminated["overlaps_by_split"] == {"train": 0, "val": 0, "test": 1}
    assert contaminated["cases_with_overlap"] == ["root-1"]
    # Shared book-prefix positions are not passed as scored decision positions.
    assert "scored" in result["scope"]


def test_empty_or_unknown_membership_sets_cannot_prove_no_leakage():
    from training.evaluation_cases import audit_membership

    corpus = {"train": {"a" * 64}, "val": {"b" * 64}, "test": {"c" * 64}}
    for groups, cases in (
        ({}, {"case": {"d" * 64}}),
        (corpus, {}),
        (corpus, {"case": set()}),
        (corpus, {"case": {"invalid"}}),
        ({**corpus, "test": set()}, {"case": {"d" * 64}}),
    ):
        with pytest.raises(ValueError):
            audit_membership(groups, cases)


def test_model_matches_and_corpus_loading_are_linux_only(monkeypatch):
    from training.evaluation_cases import corpus_position_sets, prepare_development

    monkeypatch.setattr("training.evaluation_cases.sys.platform", "darwin")
    for function, args in (
        (prepare_development, ({}, "a" * 40)),
        (corpus_position_sets, ("unused",)),
    ):
        with pytest.raises(ValueError, match="Linux"):
            function(*args)


def test_streaming_inventory_counts_every_published_row_and_all_three_splits():
    from training.evaluation_cases import collect_corpus_identities
    from training.evaluation_v2_runner import position_identity

    rows = [
        {
            "vsfen": "board-a b - 1",
            "split": "train",
            "ruleset_id": "voxelshogi-standard-v1",
        },
        {
            "vsfen": "board-a b - 9",
            "split": "val",
            "ruleset_id": "voxelshogi-standard-v1",
        },
        {
            "vsfen": "board-b w P 1",
            "split": "test",
            "ruleset_id": "voxelshogi-standard-v1",
        },
        {
            "vsfen": "board-a b - 10",
            "split": "train",
            "ruleset_id": "voxelshogi-standard-v1",
        },
    ]
    groups = collect_corpus_identities(iter(rows), expected_rows=4)
    assert groups["train"] == groups["val"] == {position_identity("board-a b - 1")}
    assert groups["test"] == {position_identity("board-b w P 1")}
    for invalid, expected in ((rows[:-1], 4), (rows, 3), (rows[:1], 1)):
        with pytest.raises(ValueError):
            collect_corpus_identities(iter(invalid), expected_rows=expected)
