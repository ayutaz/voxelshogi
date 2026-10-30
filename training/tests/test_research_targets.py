"""Hand-counted sparse targets and value semantics; no model or rules execute."""

import math

import pytest


def test_visit_counts_become_sparse_probabilities_in_canonical_action_order():
    from training.research_targets import visit_policy

    target = visit_policy([99, 3, 7], {99: 0, 7: 1, 3: 3})
    assert target == {
        "kind": "visits-v1",
        "actions": [3, 7],
        "probabilities": [0.75, 0.25],
        "visits": [3, 1],
        "total_visits": 4,
    }
    assert visit_policy([7, 3, 99], {3: 3, 7: 1}) == target
    assert visit_policy([7], {7: 2})["probabilities"] == [1.0]


@pytest.mark.parametrize(
    "legal,visits",
    [
        ([], {}),
        ([3], {}),
        ([3], {3: 0}),
        ([3], {7: 1}),
        ([3, 3], {3: 1}),
        ([3], {3: True}),
        ([3], {3: -1}),
        ([3], {3: float("nan")}),
        ([True], {1: 1}),
        ([1067985], {1067985: 1}),
        ([3], {"3": 1}),
        ([3, 7], {3: 2**63 - 1, 7: 1}),
        ([3], {3: 2**63}),
        ([-1], {-1: 1}),
    ],
)
def test_empty_illegal_duplicate_or_noninteger_visits_are_rejected(legal, visits):
    from training.research_targets import visit_policy

    with pytest.raises(ValueError):
        visit_policy(legal, visits)


def test_natural_terminal_values_use_the_sample_side_and_cutoffs_are_not_draws():
    from training.research_targets import terminal_value

    win = {"Win": {"winner": "Black", "reason": "Checkmate"}}
    assert terminal_value(win, "b") == {"kind": "terminal-v1", "value": 1.0}
    assert terminal_value(win, "w") == {"kind": "terminal-v1", "value": -1.0}
    assert terminal_value({"Draw": {"reason": "Repetition"}}, "b")["value"] == 0.0
    for invalid in (
        None,
        {"Draw": {"reason": "MaxPlies"}},
        {"Draw": {"reason": "Abandoned"}},
    ):
        with pytest.raises(ValueError):
            terminal_value(invalid, "b")


def test_cutoff_bootstrap_is_explicit_signed_discounted_and_model_bound():
    from training.research_targets import bootstrap_value

    label = bootstrap_value(
        0.8,
        bootstrap_side="w",
        sample_side="b",
        remaining_plies=2,
        model_sha256="a" * 64,
        discount=0.5,
    )
    assert label == {
        "kind": "bootstrap-v1",
        "value": -0.2,
        "bootstrap_side": "w",
        "model_sha256": "a" * 64,
        "remaining_plies": 2,
        "discount": 0.5,
    }
    same = bootstrap_value(
        0.8,
        bootstrap_side="b",
        sample_side="b",
        remaining_plies=0,
        model_sha256="a" * 64,
        discount=1.0,
    )
    assert same["value"] == 0.8
    assert same["kind"] != "terminal-v1"
    zero = bootstrap_value(
        0.0,
        bootstrap_side="b",
        sample_side="w",
        remaining_plies=3,
        model_sha256="a" * 64,
        discount=1.0,
    )
    assert zero["value"] == 0.0 and zero["kind"] == "bootstrap-v1"


@pytest.mark.parametrize(
    "changes",
    [
        {"value": None},
        {"value": float("nan")},
        {"value": 1.01},
        {"value": True},
        {"model_sha256": ""},
        {"remaining_plies": True},
        {"remaining_plies": -1},
        {"remaining_plies": 20001},
        {"model_sha256": "A" * 64},
        {"bootstrap_side": "x"},
        {"sample_side": "x"},
        {"discount": 0},
        {"discount": 1.01},
        {"discount": True},
    ],
)
def test_unknown_or_invalid_bootstrap_never_silently_becomes_zero(changes):
    from training.research_targets import bootstrap_value

    arguments = dict(
        value=0.8,
        bootstrap_side="b",
        sample_side="w",
        remaining_plies=1,
        model_sha256="a" * 64,
        discount=1.0,
    )
    arguments.update(changes)
    with pytest.raises(ValueError):
        bootstrap_value(**arguments)


def test_search_score_target_remains_distinct_from_outcome_and_requires_finished_depth():
    from training.research_targets import teacher_value

    label = teacher_value(1000, completed_depth=3, minimum_depth=3, value_scale=1000)
    assert label["kind"] == "search-score-v1"
    assert label["value"] == pytest.approx(0.7615941559557649)
    assert label["score"] == 1000 and label["completed_depth"] == 3
    assert label["value_scale"] == 1000
    assert (
        teacher_value(-1000000, completed_depth=3, minimum_depth=3, value_scale=1000)[
            "value"
        ]
        == -1.0
    )
    for changes in (
        {"completed_depth": 2},
        {"completed_depth": 0},
        {"score": True},
        {"score": math.inf},
        {"minimum_depth": True},
        {"value_scale": 0},
        {"value_scale": math.nan},
        {"minimum_depth": 0},
        {"completed_depth": 65},
        {"score": 1000001},
    ):
        arguments = dict(
            score=1000, completed_depth=3, minimum_depth=3, value_scale=1000
        )
        arguments.update(changes)
        with pytest.raises(ValueError):
            teacher_value(**arguments)
