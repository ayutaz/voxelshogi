"""Hand-counted outcomes and paired statistics, no rules or models on Mac."""

import pytest


def pair(seed, outcomes, opponent="random"):
    return [
        {
            "seed": seed,
            "model_side": side,
            "opponent": opponent,
            "opening_moves": ["opaque-opening"],
            "outcome": outcome,
        }
        for side, outcome in zip(("b", "w"), outcomes, strict=True)
    ]


def test_counts_include_cutoffs_in_denominator_but_never_as_draws():
    from training.evaluation import summarize_pairs

    result = summarize_pairs(
        pair(7, ("win", "loss")) + pair(8, ("draw", "cutoff")),
        seeds=[7, 8],
        opponent="random",
    )
    assert result["games_started"] == 4 and result["pairs"] == 2
    assert [result[key] for key in ("wins", "losses", "draws", "cutoffs")] == [
        1,
        1,
        1,
        1,
    ]
    assert result["win_rate"] == 0.25


def test_bootstrap_resamples_opening_pairs_instead_of_individual_games():
    from training.evaluation import summarize_pairs

    rows = pair(7, ("win", "loss")) + pair(8, ("loss", "win"))
    result = summarize_pairs(rows, seeds=[7, 8], opponent="random")
    assert result["paired_bootstrap95"] == [0.5, 0.5]
    assert summarize_pairs(rows[::-1], seeds=[8, 7], opponent="random") == result
    for outcome, expected in (("win", [1, 1]), ("loss", [0, 0])):
        assert (
            summarize_pairs(pair(7, (outcome, outcome)), seeds=[7], opponent="random")[
                "paired_bootstrap95"
            ]
            == expected
        )


def test_incomplete_duplicate_unexpected_or_mismatched_pairs_are_not_success():
    from training.evaluation import summarize_pairs

    rows = pair(7, ("win", "loss"))
    bad = [
        {**rows[1], "opening_moves": ["different"]},
        {**rows[1], "outcome": "failed"},
        {**rows[1], "opponent": "search"},
        {**rows[1], "model_side": "b"},
    ]
    for games in ([], rows[:1], rows + rows, *([rows[0], changed] for changed in bad)):
        with pytest.raises(ValueError):
            summarize_pairs(games, seeds=[7], opponent="random")
    with pytest.raises(ValueError):
        summarize_pairs(rows, seeds=[7, 8], opponent="random")


def test_result_uses_model_color_and_distinguishes_move_limit_from_repetition():
    from training.evaluation import classify_result

    win = {"Win": {"winner": "White", "reason": "Checkmate"}}
    assert classify_result(win, "w") == "win" and classify_result(win, "b") == "loss"
    assert classify_result({"Draw": {"reason": "Repetition"}}, "b") == "draw"
    assert classify_result({"Draw": {"reason": "MaxPlies"}}, "w") == "cutoff"
    for result, side in (
        (None, "b"),
        ({"Win": {"winner": "Green", "reason": "Checkmate"}}, "b"),
        ({"Draw": {"reason": "unknown"}}, "b"),
        (win, "x"),
    ):
        with pytest.raises(ValueError):
            classify_result(result, side)


def test_production_profile_cannot_be_relabelled_after_custom_rules_or_fixture_openings():
    from training.evaluation import _evaluation_binding
    from training.supervision import evaluation_protocol

    model = {
        "model_id": "selected",
        "artifact_sha256": "a" * 64,
        "trained": True,
        "precision": "fp32",
        "backend": "torch-cpu",
    }
    fixed = evaluation_protocol()
    assert _evaluation_binding(model, "b" * 40, fixed)["protocol"] == fixed
    with pytest.raises(ValueError):
        _evaluation_binding(model, "b" * 40, fixed, custom_opening=True)
    with pytest.raises(ValueError):
        _evaluation_binding({**model, "backend": "fixture"}, "b" * 40, fixed)
    altered = {**fixed, "max_plies": 4}
    with pytest.raises(ValueError):
        _evaluation_binding(model, "b" * 40, altered)
