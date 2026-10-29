"""Analytical loss/update oracles. Actual tensor/learning execution is Linux CI."""

import math

import pytest


def toy_model(illegal_logit=0):
    import torch
    from torch import nn

    class Toy(nn.Module):
        def __init__(self):
            super().__init__()
            self.policy = nn.Parameter(torch.tensor([0.0, 0.0, float(illegal_logit)]))
            self.value = nn.Parameter(torch.zeros(1))
            self.modes = []

        def forward(self, features):
            self.modes.append(self.training)
            return self.policy.expand(len(features), -1), self.value.expand(
                len(features), 1
            )

    return Toy()


def batch(split="train", ids=("a",), actions=None, values=None, legal=None):
    import torch

    from training.learning import Batch

    n = len(ids)
    return Batch(
        features=torch.zeros(n, 1),
        actions=torch.tensor(actions if actions is not None else [0] * n),
        values=torch.tensor(values if values is not None else [0.0] * n),
        legal_actions=legal if legal is not None else [[0, 1] for _ in ids],
        ids=ids,
        split=split,
    )


def test_masked_loss_and_gradients_match_hand_computed_two_choice_distribution():
    import torch

    from training.learning import loss_terms

    logits = torch.tensor([[0.0, 0.0, 1000.0]], requires_grad=True)
    value = torch.tensor([[0.0]], requires_grad=True)
    terms = loss_terms(logits, value, torch.tensor([0]), torch.tensor([1.0]), [[0, 1]])
    assert terms["policy"].item() == pytest.approx(math.log(2))
    assert terms["value"].item() == 1
    assert terms["total"].item() == pytest.approx(math.log(2) + 1)
    terms["total"].backward()
    torch.testing.assert_close(logits.grad, torch.tensor([[-0.5, 0.5, 0.0]]))
    assert value.grad.item() == -2


@pytest.mark.parametrize(
    "legal,actions",
    [
        ([[]], [0]),
        ([[0, 0]], [0]),
        ([[0, 1]], [2]),
        ([[0, 3]], [0]),
        ([[0.5, 1.0]], [1]),
    ],
)
def test_invalid_or_empty_legal_targets_are_not_silently_trained(legal, actions):
    import torch

    from training.learning import loss_terms

    with pytest.raises(ValueError):
        loss_terms(
            torch.zeros(1, 3),
            torch.zeros(1, 1),
            torch.tensor(actions),
            torch.zeros(1),
            legal,
        )


def test_empty_nonfinite_or_broadcasting_batches_are_rejected():
    import torch

    from training.learning import loss_terms

    for logits, values, actions, targets, legal in (
        (
            torch.zeros(0, 3),
            torch.zeros(0, 1),
            torch.zeros(0, dtype=torch.long),
            torch.zeros(0),
            [],
        ),
        (
            torch.tensor([[float("nan"), 0.0]]),
            torch.zeros(1, 1),
            torch.tensor([0]),
            torch.zeros(1),
            [[0, 1]],
        ),
        (
            torch.zeros(2, 3),
            torch.zeros(1, 1),
            torch.tensor([0, 0]),
            torch.zeros(2),
            [[0, 1], [0, 1]],
        ),
        (
            torch.zeros(1, 3),
            torch.zeros(1, 1),
            torch.tensor([0]),
            torch.tensor([1.1]),
            [[0, 1]],
        ),
    ):
        with pytest.raises(ValueError):
            loss_terms(logits, values, actions, targets, legal)


def test_one_sgd_step_matches_independent_gradient_update():
    import torch

    from training.learning import train_step

    model = toy_model().eval()
    optimizer = torch.optim.SGD(model.parameters(), lr=0.2)
    metrics = train_step(model, optimizer, batch())
    # dCE/dlogit = p - one_hot: [-1/2, +1/2, 0]. Its norm is below clip=1.
    torch.testing.assert_close(model.policy.detach(), torch.tensor([0.1, -0.1, 0.0]))
    assert model.value.item() == 0 and model.training
    assert metrics["examples"] == 1 and metrics["policy_loss"] == pytest.approx(
        math.log(2)
    )
    for _ in range(5):
        last = train_step(model, optimizer, batch())
    assert last["loss"] < metrics["loss"] - 0.05


def test_validation_or_test_batches_cannot_update_parameters():
    import torch

    from training.learning import train_step

    model = toy_model()
    optimizer = torch.optim.SGD(model.parameters(), lr=0.2)
    before = model.policy.detach().clone()
    for split in ("val", "test"):
        with pytest.raises(ValueError):
            train_step(model, optimizer, batch(split))
    torch.testing.assert_close(before, model.policy, rtol=0, atol=0)


def test_evaluation_weights_partial_batches_and_never_updates_or_enables_dropout():
    import torch

    from training.learning import evaluate_model

    model = toy_model(illegal_logit=1000).train()
    before = {k: v.detach().clone() for k, v in model.state_dict().items()}
    result = evaluate_model(
        model,
        [
            batch("val", ("a", "b"), actions=[0, 1], values=[1.0, 1.0]),
            batch("val", ("c",), legal=[[1, 0]]),
        ],
        split="val",
    )
    assert result["examples"] == 3
    assert result["policy_loss"] == pytest.approx(math.log(2))
    assert result["value_mse"] == pytest.approx(2 / 3)
    assert result["value_mae"] == pytest.approx(2 / 3)
    assert result["policy_top1"] == pytest.approx(2 / 3)
    assert result["policy_top5"] == 1
    assert result["raw_legal_rate"] == 0 and result["masked_legal_rate"] == 1
    assert model.modes == [False, False] and model.training
    for key, value in model.state_dict().items():
        torch.testing.assert_close(value, before[key], rtol=0, atol=0)
    assert all(p.grad is None for p in model.parameters())


def test_evaluation_rejects_empty_wrong_split_and_repeated_examples():
    from training.learning import evaluate_model

    model = toy_model()
    for batches in ([], [batch("train")], [batch("val"), batch("val")]):
        with pytest.raises(ValueError):
            evaluate_model(model, batches, split="val")


def test_nonfinite_backward_is_rejected_before_optimizer_step():
    import torch

    from training.learning import train_step

    class BadGradient(torch.autograd.Function):
        @staticmethod
        def forward(ctx, value):
            return value.clone()

        @staticmethod
        def backward(ctx, grad_output):
            return torch.full_like(grad_output, float("inf"))

    model = toy_model()
    original = model.forward

    def bad_forward(features):
        policy, value = original(features)
        return policy, BadGradient.apply(value)

    model.forward = bad_forward
    optimizer = torch.optim.SGD(model.parameters(), lr=0.2)
    before = model.policy.detach().clone()
    with pytest.raises(ValueError, match="gradient"):
        train_step(model, optimizer, batch(values=[1.0]))
    torch.testing.assert_close(before, model.policy, rtol=0, atol=0)


def test_gradient_clipping_caps_a_large_finite_update():
    import torch

    from training.learning import train_step

    model = toy_model()
    optimizer = torch.optim.SGD(model.parameters(), lr=0.2)
    result = train_step(model, optimizer, batch(values=[1.0]))
    # Unclipped norm sqrt(.25 + .25 + 4) = sqrt(4.5).
    assert result["gradient_norm"] == pytest.approx(math.sqrt(4.5))
    update = torch.cat([model.policy.detach(), model.value.detach()])
    assert update.norm().item() == pytest.approx(0.2, abs=1e-6)
