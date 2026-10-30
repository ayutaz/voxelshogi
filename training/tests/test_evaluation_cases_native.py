"""Linux CI verifies handwritten terminal oracles against the real Rust engine."""

import pytest


def test_handwritten_mating_moves_and_repetition_result_replay_in_rust():
    from voxelshogi import Game

    from training.evaluation_cases import handmade_cases

    cases = handmade_cases()
    assert len(cases) == 6
    for item in cases:
        game = Game.from_record(item["case"]["opening"])
        assert not game.snapshot()["finished"]
        if item["oracle"] is not None:
            assert item["oracle"]["move"] in game.snapshot()["legal_moves"]
            game.play(item["oracle"]["move"])
            assert game.snapshot()["finished"]
            assert game.snapshot()["result"] == item["oracle"]["result"]
            assert (
                Game.from_record(game.record()).snapshot()["result"]
                == item["oracle"]["result"]
            )


def test_scored_replay_excludes_book_prefix_but_includes_later_decision_states():
    from voxelshogi import Game

    from training.evaluation_cases import replay_scored_positions
    from training.evaluation_v2_runner import position_identity
    from training.tests.test_engine import corner_position

    game = Game(corner_position())
    original = position_identity(game.snapshot()["vsfen"])
    game.play("999899")
    root = game.record()
    root_id = position_identity(game.snapshot()["vsfen"])
    game.play("111211")
    next_id = position_identity(game.snapshot()["vsfen"])
    identities = replay_scored_positions(game.record(), root)
    assert identities == {root_id, next_id}
    assert original not in identities
    changed = dict(root, moves=["999799"])
    with pytest.raises(ValueError):
        replay_scored_positions(game.record(), changed)


def test_fixed_development_openings_are_reproducible_and_cover_all_strata():
    import subprocess
    from pathlib import Path

    from training.evaluation_cases import prepare_development
    from training.evaluation_v2_runner import rust_policy_identity

    root = Path(__file__).resolve().parents[2]
    source = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    limits = {"max_depth": 3, "max_nodes": 20000, "table_capacity": 4096}
    native = {
        "policy": "alphabeta-v1",
        "backend": "rust",
        "artifact_sha256": rust_policy_identity("alphabeta-v1", source, limits),
    }
    participants = {"model": dict(native), "opponent": dict(native)}
    first = prepare_development(participants, source)
    assert first == prepare_development(participants, source)
    assert first["purpose"] == "development"
    assert len(first["cases"]) == 8
    assert {case["stratum"] for case in first["cases"]} == {
        "opening",
        "middlegame",
        "endgame",
        "tactical",
    }
    generated = {
        case["id"]: case
        for case in first["cases"]
        if case["stratum"] in ("opening", "middlegame")
    }
    assert len(generated["standard-opening"]["opening"]["moves"]) == 16
    assert len(generated["standard-middle"]["opening"]["moves"]) == 96
    assert all(case["max_additional_plies"] == 512 for case in generated.values())
