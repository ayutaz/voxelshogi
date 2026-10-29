"""Small metadata fixtures, not game simulation, tensor work, or training on Mac."""

import copy
import json

import pytest


def row(game="g000002", split="train", side="b", score=1000):
    # Opaque board text: Rust legality is established by M4 replay + pinned hashes.
    moves = ["111998", "111999"] if side == "b" else ["999111+", "999112"]
    actions = [1294, 1456] if side == "b" else [1294, 1457]
    best = "111999" if side == "b" else "999111+"
    return {
        "game_id": game,
        "ply": 0,
        "source": "search",
        "split": split,
        "ruleset_id": "voxelshogi-standard-v1",
        "initial": f"board-{game} {side} - 1",
        "history": [],
        "vsfen": f"board-{game} {side} - 1",
        "hash": "0000000000000000",
        "side": side,
        "legal_moves": sorted(moves),
        "legal_actions": actions,
        "played_move": moves[0],
        "teacher": json.dumps(
            {
                "best_move": best,
                "score": score,
                "completed_depth": 2,
                "nodes": 700,
                "stop_reason": "depth",
            }
        ),
        "teacher_valid": True,
        "finished": False,
        "result": None,
        "termination": None,
        "duplicate_of": None,
        "evaluation": -5000,  # Static material is intentionally not the teacher.
    }


@pytest.mark.parametrize(
    "text,side,expected",
    [
        ("111999", "b", 1456),
        ("111999+", "b", 1457),
        ("999111", "w", 1456),
        ("999111+", "w", 1457),
        ("P*111", "b", 1062882),
        ("R*111", "w", 1067984),
    ],
)
def test_move_ids_are_hand_computed(text, side, expected):
    from training.supervision import move_action

    assert move_action(text, side) == expected


@pytest.mark.parametrize("text", ["000999", "11199", "K*555", "P*111+", "garbage"])
def test_bad_notation_is_rejected(text):
    from training.supervision import move_action

    with pytest.raises(ValueError):
        move_action(text, "b")


def test_search_score_is_already_from_side_to_move_and_uses_fixed_scale():
    from training.supervision import score_value, select_target

    assert score_value(0) == 0
    assert score_value(100) == pytest.approx(0.09966799462495582)
    assert score_value(1000) == pytest.approx(0.7615941559557649)
    assert score_value(1_000_000) == 1 and score_value(-1_000_000) == -1
    target = select_target(row(side="w", score=-1000))
    assert target.action == 1457 and target.value == pytest.approx(-0.7615941559557649)
    for invalid in (True, 1.5, None, float("nan"), 1_000_001):
        with pytest.raises(ValueError):
            score_value(invalid)


def test_opening_played_move_is_not_the_policy_teacher():
    from training.supervision import select_target

    target = select_target(row())
    assert target.action == 1456 and target.legal_actions == (1294, 1456)
    assert target.example_id == "g000002:0" and target.split == "train"


def test_duplicate_and_final_rows_are_not_supervision():
    from training.supervision import select_target

    duplicate = row()
    duplicate["duplicate_of"] = "g000000:0"
    assert select_target(duplicate) is None
    final = row()
    final.update(
        ply=64,
        history=["111999"] * 64,
        termination="max_plies",
        teacher=None,
        teacher_valid=False,
        played_move=None,
    )
    assert select_target(final) is None  # Never create a draw/zero-value target.
    final.update(
        finished=True,
        result='{"Win":{"winner":"White","reason":"Checkmate"}}',
        termination="natural",
        legal_moves=[],
        legal_actions=[],
    )
    assert select_target(final) is None


def test_unlabelled_sources_and_unfinished_depth_are_excluded():
    from training.supervision import select_target

    other = row()
    other.update(source="random", teacher=None, teacher_valid=False)
    assert select_target(other) is None
    incomplete = row()
    teacher = json.loads(incomplete["teacher"])
    teacher.update(completed_depth=0, score=None, nodes=1, stop_reason="nodes")
    incomplete.update(teacher=json.dumps(teacher), teacher_valid=False)
    assert select_target(incomplete) is None


@pytest.mark.parametrize(
    "change",
    [
        {"teacher_valid": False},
        {"teacher": None},
        {"source": "rules"},
        {"legal_actions": [1294, 1457]},
        {"legal_actions": [1456, 1456]},
        {"legal_moves": ["111998", "111998"]},
        {"side": "w"},
        {"ruleset_id": "nine-kings"},
        {"split": "test"},
        {"history": ["111999"]},
        {"result": "{}"},
    ],
)
def test_inconsistent_metadata_is_not_silently_filtered(change):
    from training.supervision import select_target

    bad = {**row(), **change}
    with pytest.raises(ValueError):
        select_target(bad)


@pytest.mark.parametrize(
    "change",
    [
        {"best_move": "111997"},
        {"score": None},
        {"score": True},
        {"completed_depth": 3},
        {"nodes": 10001},
        {"stop_reason": "time"},
    ],
)
def test_teacher_must_match_the_pinned_search_contract(change):
    from training.supervision import select_target

    bad = row()
    bad["teacher"] = json.dumps({**json.loads(bad["teacher"]), **change})
    with pytest.raises(ValueError):
        select_target(bad)


def test_audit_counts_actual_teacher_splits_and_rejects_leakage_and_emptiness():
    from training.supervision import audit_rows

    rows = [row(), row("g000044", "val"), row("g000050", "test")]
    report = audit_rows(rows)
    assert report["rows"] == report["eligible_teachers"] == 3
    assert report["teacher_splits"] == {"train": 1, "val": 1, "test": 1}
    assert report["teacher_depths"] == {"2": 3}
    bad = copy.deepcopy(rows)
    bad[2]["vsfen"] = bad[0]["vsfen"].rsplit(" ", 1)[0] + " 2"
    with pytest.raises(ValueError):
        audit_rows(bad)  # A repeated position has no duplicate_of marker.
    bad[2]["duplicate_of"] = "g000002:0"
    with pytest.raises(ValueError):
        audit_rows(bad)  # No usable test teachers remain.
    with pytest.raises(ValueError):
        audit_rows([])
    with pytest.raises(ValueError):
        audit_rows(rows, expected={"eligible_teachers": 4})


def test_inventory_hash_and_paths_are_checked_before_reading_parquet(tmp_path):
    import hashlib

    from training.supervision import verify_files

    p = tmp_path / "game-000000.parquet"
    p.write_bytes(b"abc")
    entry = {"file": p.name, "bytes": 3, "sha256": hashlib.sha256(b"abc").hexdigest()}
    verify_files(tmp_path, [entry])
    p.write_bytes(b"abd")
    with pytest.raises(ValueError):
        verify_files(tmp_path, [entry])
    with pytest.raises(ValueError):
        verify_files(tmp_path, [{**entry, "file": "../outside"}])


def test_frozen_label_profile_has_a_stable_identifier_and_no_test_selection():
    from training.supervision import label_contract

    contract = label_contract()
    assert contract["schema"] == "voxelshogi-supervision-v1"
    assert contract["value_scale"] == 1000 and contract["loss_value_weight"] == 1
    assert contract["revision"] == "6e7fb29d2469b56a895042fbb089d86e7b4d074f"
    assert contract["config"] == "production-64"
    assert contract["selection_split"] == "val" and contract["training_seed"] == 314159


def test_manifest_cannot_introduce_a_shard_missing_from_verified_inventory():
    from training.supervision import validate_manifest

    config = {"games": 1, "max_plies": 64}
    manifest = {
        "schema": "voxelshogi-dataset-v1",
        "ruleset_id": "voxelshogi-standard-v1",
        "complete": True,
        "config": config,
        "shards": [{"file": "game-000000.parquet", "rows": 65, "sha256": "a" * 64}],
    }
    inventory = [
        {"file": name, "sha256": "a" * 64, "bytes": 3}
        for name in (
            "game-000000.parquet",
            "manifest.json",
            "generation.json",
            "validation.json",
        )
    ]
    validate_manifest(manifest, config, inventory, expected_rows=65)
    for change in (
        {"complete": False},
        {"schema": "old-schema"},
        {"config": {"games": 2, "max_plies": 64}},
        {"shards": [{"file": "../outside", "rows": 65, "sha256": "a" * 64}]},
        {"shards": [{"file": "game-000000.parquet", "rows": 65, "sha256": "b" * 64}]},
    ):
        with pytest.raises(ValueError):
            validate_manifest(
                {**manifest, **change}, config, inventory, expected_rows=65
            )
    with pytest.raises(ValueError):
        validate_manifest(manifest, config, inventory[1:], expected_rows=65)
    with pytest.raises(ValueError):
        validate_manifest(manifest, config, inventory, expected_rows=64)


def test_nonfinite_json_teacher_and_wrong_side_are_rejected():
    from training.supervision import move_action, select_target

    bad = row()
    bad["teacher"] = bad["teacher"].replace('"score": 1000', '"score": NaN')
    with pytest.raises(ValueError):
        select_target(bad)
    with pytest.raises(ValueError):
        move_action("111999", "white")


def test_evaluation_protocol_is_frozen_before_measuring_strength():
    from training.supervision import evaluation_protocol

    protocol = evaluation_protocol()
    assert protocol["max_plies"] == 256 and protocol["opening_plies"] == 8
    assert protocol["opening_seeds"]["random"] == list(range(7000, 7020))
    assert protocol["opening_seeds"]["search"] == list(range(8000, 8010))
    assert protocol["swap_model_colors"] is True
    assert protocol["search_limits"] == {
        "max_depth": 2,
        "max_nodes": 10000,
        "table_capacity": 4096,
    }
    assert protocol["primary_win_rate"] == "wins / games_started"
    assert protocol["cutoff_is_draw"] is False
