"""Small Rust cohort and restart control on Linux CI; not a production benchmark."""

import json

import pytest


def profile():
    from training.supervision import evaluation_protocol

    value = evaluation_protocol()
    value.update(
        schema="voxelshogi-evaluation-smoke-v1",
        max_plies=4,
        opening_plies=2,
        opening_seeds={"random": [7], "search": [8]},
    )
    return value


def model_info():
    return {
        "model_id": "fixture",
        "artifact_sha256": "a" * 64,
        "trained": False,
        "precision": "fp32",
        "backend": "fixture",
    }


def test_small_cohort_is_complete_paired_replayable_and_can_reuse_verified_games(
    tmp_path,
):
    from voxelshogi import Game

    from training.evaluation import evaluate_matches
    from training.tests.test_engine import corner_position

    def factory():
        return Game(corner_position())

    calls = []

    def choose(game):
        calls.append(1)
        return min(game.legal_actions())

    folder = tmp_path / "matches"
    result = evaluate_matches(
        choose,
        folder,
        model=model_info(),
        source_commit="b" * 40,
        protocol=profile(),
        game_factory=factory,
    )
    assert result["complete"] and not result["production_profile"]
    assert len(result["files"]) == 4 and len(calls) == 4
    assert all(result["cohorts"][name]["cutoffs"] == 2 for name in ("random", "search"))
    before = len(calls)
    again = evaluate_matches(
        choose,
        folder,
        model=model_info(),
        source_commit="b" * 40,
        protocol=profile(),
        game_factory=factory,
        resume=True,
    )
    assert again == result and len(calls) == before
    path = folder / "random-7-b.json"
    row = json.loads(path.read_text())
    row["outcome"] = "win"
    path.write_text(json.dumps(row))
    with pytest.raises(ValueError):
        evaluate_matches(
            choose,
            folder,
            model=model_info(),
            source_commit="b" * 40,
            protocol=profile(),
            game_factory=factory,
            resume=True,
        )


def test_stop_does_not_fabricate_results_and_model_switch_cannot_resume_same_cohort(
    tmp_path,
):
    from training.evaluation import evaluate_matches

    folder = tmp_path / "interrupted"
    result = evaluate_matches(
        lambda game: -1,
        folder,
        model=model_info(),
        source_commit="b" * 40,
        protocol=profile(),
        stop_requested=lambda: True,
    )
    assert result["complete"] is False and result["completed_games"] == 0
    assert not (folder / "evaluation.json").exists()
    with pytest.raises(ValueError, match="binding"):
        evaluate_matches(
            lambda game: -1,
            folder,
            model={**model_info(), "artifact_sha256": "c" * 64},
            source_commit="b" * 40,
            protocol=profile(),
            resume=True,
        )
