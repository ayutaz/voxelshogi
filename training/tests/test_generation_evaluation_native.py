"""External Linux/CI only: actual canonical openings, oracle and full replay."""

import subprocess
from pathlib import Path

import pytest


def test_all_generation_openings_are_canonical_unique_and_oracles_hold():
    from voxelshogi import Game

    from training.evaluation_v2_runner import rust_policy_identity
    from training.generation_cases import (
        SEARCH_LIMITS,
        generation_definitions,
        prepare_generation_protocol,
    )
    from training.research_data import input_identity

    source = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2], text=True
    ).strip()
    participant = {
        "policy": "alphabeta-v1",
        "backend": "rust",
        "artifact_sha256": rust_policy_identity("alphabeta-v1", source, SEARCH_LIMITS),
    }
    participants = {"model": dict(participant), "opponent": dict(participant)}
    all_roots = set()
    for stage, count in (("timing", 2), ("comparison", 15)):
        spec = prepare_generation_protocol(participants, source, stage=stage)
        assert len(spec["cases"]) == count
        definitions = generation_definitions(stage)
        for case, definition in zip(spec["cases"], definitions, strict=True):
            game = Game.from_record(case["opening"])
            assert not game.snapshot()["finished"] and game.record() == case["opening"]
            identity = input_identity(game.snapshot())
            assert identity not in all_roots
            all_roots.add(identity)
            if definition["oracle"]:
                game.play("232222")
                assert game.snapshot()["result"] == {
                    "Win": {"winner": "Black", "reason": "Checkmate"}
                }
            if definition["generated_opening"]:
                assert (
                    len(case["opening"]["moves"])
                    == definition["generated_opening"]["plies"]
                )
    assert len(all_roots) == 17


def test_canonical_input_replay_includes_terminal_and_rejects_changed_prefix():
    from voxelshogi import Game

    from training.evaluation_v2_runner import position_identity
    from training.generation_cases import replay_scored_identities
    from training.research_data import input_identity
    from training.tests.test_engine import corner_position

    game = Game(corner_position())
    excluded = input_identity(game.snapshot())
    game.play("999899")
    opening = game.record()
    expected_inputs = {input_identity(game.snapshot())}
    expected_positions = {position_identity(game.snapshot()["vsfen"])}
    game.play("111211")
    expected_inputs.add(input_identity(game.snapshot()))
    expected_positions.add(position_identity(game.snapshot()["vsfen"]))
    actual = replay_scored_identities(game.record(), opening)
    assert actual == {"positions": expected_positions, "inputs": expected_inputs}
    assert excluded not in actual["inputs"]
    with pytest.raises(ValueError):
        replay_scored_identities(game.record(), dict(opening, moves=["999799"]))
