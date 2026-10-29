"""Linux-only real Rust matches, small handmade positions, never Mac search."""

import pytest


def test_match_keeps_history_checks_legal_actions_and_replays_cutoff_record():
    from voxelshogi import Game

    from training.evaluation import play_match, verify_match
    from training.tests.test_engine import corner_position

    opening = Game(corner_position()).record()
    result = play_match(
        opening,
        lambda game: min(game.legal_actions()),
        model_side="b",
        opponent="random",
        seed=7,
        max_plies=4,
    )
    assert result["outcome"] == "cutoff" and result["plies"] == 4
    assert result["record"]["termination"] == "MaxPlies"
    assert result["record"]["result"] == {"Draw": {"reason": "MaxPlies"}}
    assert verify_match(result, opening, max_plies=4) == "cutoff"
    again = play_match(
        opening,
        lambda game: min(game.legal_actions()),
        model_side="b",
        opponent="random",
        seed=7,
        max_plies=4,
    )
    assert result["record"] == again["record"]
    changed = {**result, "outcome": "win"}
    with pytest.raises(ValueError):
        verify_match(changed, opening, max_plies=4)
    with pytest.raises(ValueError):
        play_match(
            opening,
            lambda game: -1,
            model_side="b",
            opponent="random",
            seed=7,
            max_plies=4,
        )


def test_natural_mate_on_last_allowed_ply_takes_precedence_over_cutoff():
    import json

    from training.evaluation import play_match
    from training.supervision import ROOT

    opening = json.loads((ROOT / "export/fixtures/positions.json").read_text())[2][
        "record"
    ]

    def choose_mate(game):
        best = game.search(max_depth=1, max_nodes=1000)["best_move"]
        return next(
            action for action, text in game.legal_actions().items() if text == best
        )

    result = play_match(
        opening, choose_mate, model_side="b", opponent="random", seed=7, max_plies=1
    )
    assert result["outcome"] == "win" and result["plies"] == 1
    assert result["record"]["termination"] is None


def test_pair_opening_is_reused_identically_and_stop_is_not_adjudicated():
    from voxelshogi import Game

    from training.evaluation import opening_record, play_match
    from training.tests.test_engine import corner_position

    def factory():
        return Game(corner_position())

    opening = opening_record(7, plies=2, game_factory=factory)
    assert len(opening["moves"]) == 2
    assert opening_record(7, plies=2, game_factory=factory) == opening
    rows = [
        play_match(
            opening,
            lambda game: min(game.legal_actions()),
            model_side=side,
            opponent="random",
            seed=7,
            max_plies=4,
        )
        for side in ("b", "w")
    ]
    assert all(row["record"]["moves"][:2] == opening["moves"] for row in rows)
    with pytest.raises(InterruptedError):
        play_match(
            opening,
            lambda game: min(game.legal_actions()),
            model_side="b",
            opponent="random",
            seed=7,
            max_plies=4,
            stop_requested=lambda: True,
        )
