"""Linux Rust smoke records exercise export replay, not the full 60-game study."""

import json

import pytest


def test_export_replays_games_and_recounts_cohort_before_accepting_summary(
    tmp_path, monkeypatch
):
    from voxelshogi import Game

    from export import trained
    from training import evaluation
    from training.tests.test_engine import corner_position
    from training.tests.test_evaluation_cohort import model_info, profile

    def factory():
        return Game(corner_position())

    folder = tmp_path / "evaluated"
    folder.mkdir()
    small = profile()
    report = evaluation.evaluate_matches(
        lambda game: min(game.legal_actions()),
        folder / "matches",
        model=model_info(),
        source_commit="b" * 40,
        protocol=small,
        game_factory=factory,
    )
    (folder / "evaluation.json").write_text(json.dumps({"matches": report}))
    original = evaluation.opening_record

    def opening(seed, *, plies):
        return original(seed, plies=plies, game_factory=factory)

    # Production has no override; this test only shortens the already-tested Rust plumbing.
    monkeypatch.setattr(evaluation, "opening_record", opening)
    monkeypatch.setattr(trained, "evaluation_protocol", lambda: small)
    trained.verify_evaluation_games(folder)
    report["cohorts"]["random"]["wins"] = 1
    (folder / "evaluation.json").write_text(json.dumps({"matches": report}))
    with pytest.raises(ValueError, match="summary"):
        trained.verify_evaluation_games(folder)
