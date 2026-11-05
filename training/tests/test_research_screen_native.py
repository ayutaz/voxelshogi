"""Real Rust opening/oracle checks on Linux CI; no model or timing claims."""

import subprocess
from copy import deepcopy
from pathlib import Path

import pytest


def participants():
    from training.evaluation_v2_runner import rust_policy_identity
    from training.generation_cases import SEARCH_LIMITS

    source = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2], text=True
    ).strip()
    return source, {
        "model": {
            "artifact_sha256": "a" * 64,
            "backend": "torch-cpu",
            "policy": "legal-argmax-v1",
        },
        "opponent": {
            "artifact_sha256": rust_policy_identity(
                "alphabeta-v1", source, SEARCH_LIMITS
            ),
            "backend": "rust",
            "policy": "alphabeta-v1",
        },
    }


def test_24_real_roots_are_canonical_unique_oracles_hold_and_holdout_is_separate():
    from voxelshogi import Game

    from training.evaluation_v2 import fingerprint, validate_protocol
    from training.research_data import input_identity
    from training.research_screen import prepare_screen, screen_definitions

    source, players = participants()
    result = prepare_screen(players, source)
    binding = deepcopy(result)
    assert binding.pop("conditions_sha256") == fingerprint(binding)
    assert len(result["roots"]) == 24
    assert len(result["protected_holdout_inputs"]) == 12
    argmax = result["protocols"]["legal-argmax-v1"]
    puct = result["protocols"]["puct32-v1"]
    assert argmax["cases"] == puct["cases"]
    assert (
        argmax["participants"]["model"]["artifact_sha256"]
        == puct["participants"]["model"]["artifact_sha256"]
    )
    assert puct["participants"]["model"]["policy"] == "puct32-v1"
    assert validate_protocol(argmax) != validate_protocol(puct)
    inputs = set()
    for purpose, protocol in (
        ("development", argmax),
        ("holdout", result["holdout_protocol"]),
    ):
        assert protocol["purpose"] == purpose and len(protocol["cases"]) == 12
        for case, definition in zip(
            protocol["cases"], screen_definitions(purpose), strict=True
        ):
            game = Game.from_record(case["opening"])
            assert game.record() == case["opening"] and not game.snapshot()["finished"]
            identity = input_identity(game.snapshot())
            assert identity not in inputs
            inputs.add(identity)
            assert identity == result["roots"][case["id"]]["input"]
            assert (identity in result["protected_holdout_inputs"]) == (
                purpose == "holdout"
            )
            if definition["oracle"] is not None:
                game.play(definition["oracle"]["move"])
                assert game.snapshot()["finished"]
                assert game.snapshot()["result"] == definition["oracle"]["result"]
            if definition["generated_opening"] is not None:
                assert (
                    len(case["opening"]["moves"])
                    == definition["generated_opening"]["plies"]
                )
    assert len(inputs) == 24


def test_preparation_rejects_duplicate_side_canonical_roots(monkeypatch):
    import training.research_screen as module

    first = module.screen_definitions("development")[0]
    duplicate = deepcopy(first)
    duplicate["case"]["id"] = "duplicate"
    # Distinct record/ply metadata but identical canonical neural input. A mere
    # duplicate-record check in evaluation_v2 must not catch this mutation.
    duplicate["case"]["opening"]["initial"] = (
        first["case"]["opening"]["initial"].removesuffix(" 1") + " 3"
    )
    monkeypatch.setattr(
        module, "screen_definitions", lambda purpose: [first, duplicate]
    )
    source, players = participants()
    with pytest.raises(ValueError, match="duplicate"):
        module.prepare_screen(players, source)


def test_preparation_rejects_incorrect_handwritten_oracle(monkeypatch):
    import training.research_screen as module

    first = module.screen_definitions("development")[0]
    first["oracle"]["result"]["Win"]["winner"] = "White"
    monkeypatch.setattr(module, "screen_definitions", lambda purpose: [first])
    source, players = participants()
    with pytest.raises(ValueError, match="oracle"):
        module.prepare_screen(players, source)
