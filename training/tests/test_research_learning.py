"""Analytical sparse-distribution losses; tensor execution is external Linux."""

import math

import pytest


def test_zero_visit_legal_action_stays_in_denominator_and_gradients_match_oracle():
    import torch

    from training.research_learning import loss_terms

    # Legal probabilities [1/2,1/4,1/4]; teacher [3/4,1/4,0].
    # CE=-(3/4)ln(1/2)-(1/4)ln(1/4)=1.25ln2.
    # dCE/dlogits=p-target=[-1/4,0,1/4,0]; illegal logit1000 is excluded.
    logits = torch.tensor([[math.log(2), 0.0, 0.0, 1000.0]], requires_grad=True)
    values = torch.tensor([[0.0]], requires_grad=True)
    policies = [
        {
            "kind": "visits-v1",
            "actions": [0, 1],
            "probabilities": [0.75, 0.25],
            "visits": [3, 1],
            "total_visits": 4,
        }
    ]
    terms = loss_terms(
        logits,
        values,
        policies,
        [{"kind": "terminal-v1", "value": 1.0}],
        [[2, 1, 0]],
        value_kind="terminal-v1",
        value_weight=0.5,
    )
    assert terms["policy"].item() == pytest.approx(1.25 * math.log(2))
    assert terms["value"].item() == 1
    assert terms["total"].item() == pytest.approx(1.25 * math.log(2) + 0.5)
    terms["total"].backward()
    torch.testing.assert_close(logits.grad, torch.tensor([[-0.25, 0.0, 0.25, 0.0]]))
    assert values.grad.item() == -1


def test_batch_mean_value_kind_and_one_choice_policy_are_explicit():
    import torch

    from training.research_learning import loss_terms
    from training.research_targets import visit_policy

    terms = loss_terms(
        torch.zeros(2, 3),
        torch.zeros(2, 1),
        [visit_policy([0, 1], {0: 1}), visit_policy([2], {2: 1})],
        [
            {"kind": "search-score-v1", "value": 0.5},
            {"kind": "search-score-v1", "value": -1.0},
        ],
        [[0, 1], [2]],
        value_kind="search-score-v1",
    )
    assert terms["policy"].item() == pytest.approx(math.log(2) / 2)
    assert terms["value"].item() == pytest.approx(0.625)


@pytest.mark.parametrize(
    "changes",
    [
        {"policy_actions": [0, 2]},
        {"probabilities": [0.5, 0.5]},
        {"visits": [3, 0]},
        {"total_visits": 3},
        {"probabilities": [float("nan"), 0.25]},
        {"legal": [0, 0, 1]},
        {"legal": [0, 1, 4]},
        {"legal": []},
        {"label_kind": "bootstrap-v1"},
        {"expected_kind": "mixed"},
        {"target": float("nan")},
        {"target": 1.1},
        {"target": True},
        {"weight": -1},
        {"weight": True},
    ],
)
def test_invalid_visits_legal_sets_and_mixed_or_nonfinite_values_are_rejected(changes):
    import torch

    from training.research_learning import loss_terms

    policy = {
        "kind": "visits-v1",
        "actions": changes.get("policy_actions", [0, 1]),
        "probabilities": changes.get("probabilities", [0.75, 0.25]),
        "visits": changes.get("visits", [3, 1]),
        "total_visits": changes.get("total_visits", 4),
    }
    label = {
        "kind": changes.get("label_kind", "terminal-v1"),
        "value": changes.get("target", 1.0),
    }
    with pytest.raises(ValueError):
        loss_terms(
            torch.zeros(1, 4),
            torch.zeros(1, 1),
            [policy],
            [label],
            [changes.get("legal", [0, 1, 3])],
            value_kind=changes.get("expected_kind", "terminal-v1"),
            value_weight=changes.get("weight", 1.0),
        )


def test_empty_and_broadcasting_shapes_are_rejected():
    import torch

    from training.research_learning import loss_terms
    from training.research_targets import visit_policy

    policy, label = visit_policy([0, 1], {0: 1}), {"kind": "terminal-v1", "value": 1.0}
    for logits, values, policies, labels, legal in (
        (torch.zeros(0, 3), torch.zeros(0, 1), [], [], []),
        (torch.zeros(2, 3), torch.zeros(1, 1), [policy] * 2, [label] * 2, [[0, 1]] * 2),
        (torch.zeros(1, 3), torch.zeros(1, 1), [], [label], [[0, 1]]),
        (torch.zeros(1, 3), torch.zeros(1, 1), [policy], [], [[0, 1]]),
        (
            torch.tensor([[float("nan"), 0.0]]),
            torch.zeros(1, 1),
            [policy],
            [label],
            [[0, 1]],
        ),
    ):
        with pytest.raises(ValueError):
            loss_terms(
                logits, values, policies, labels, legal, value_kind="terminal-v1"
            )


@pytest.mark.parametrize(
    "changes",
    [{"total_visits": True}, {"total_visits": 1.0}, {"probabilities": [True]}],
)
def test_policy_count_and_probability_types_are_not_accepted_by_numeric_equality(
    changes,
):
    import torch

    from training.research_learning import loss_terms
    from training.research_targets import visit_policy

    policy = visit_policy([0], {0: 1})
    policy.update(changes)
    with pytest.raises(ValueError):
        loss_terms(
            torch.zeros(1, 1),
            torch.zeros(1, 1),
            [policy],
            [{"kind": "terminal-v1", "value": 0.0}],
            [[0]],
            value_kind="terminal-v1",
        )
