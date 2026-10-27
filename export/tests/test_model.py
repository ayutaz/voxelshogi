import math

import numpy as np
import torch

from export.contract import ACTIONS
from export.model import Attention, PolicyHead, make_model


def test_attention_matches_independent_scalar_reference():
    attention = Attention(width=4, heads=2)
    with torch.no_grad():
        attention.qkv.weight.copy_(torch.eye(4).repeat(3, 1))
        attention.qkv.bias.zero_()
        attention.out.weight.copy_(torch.eye(4))
        attention.out.bias.zero_()
    values = np.array([[1, 0, 2, -1], [0, 2, -1, 1], [1, 1, 0, 2]], np.float32)
    expected = np.zeros_like(values)
    for row in range(3):
        for head in range(2):
            scores = [
                sum(
                    float(values[row, c]) * float(values[k, c])
                    for c in range(head * 2, head * 2 + 2)
                )
                / math.sqrt(2)
                for k in range(3)
            ]
            weights = [math.exp(s - max(scores)) for s in scores]
            for c in range(head * 2, head * 2 + 2):
                expected[row, c] = sum(
                    weights[k] * float(values[k, c]) for k in range(3)
                ) / sum(weights)
    actual = attention(torch.from_numpy(values[None])).detach().numpy()
    np.testing.assert_allclose(actual[0], expected, rtol=1e-6, atol=1e-6)


def test_policy_head_uses_the_contracts_interleaved_promotion_and_drop_layout():
    head = PolicyHead(width=4, rank=1)
    with torch.no_grad():
        for p in head.parameters():
            p.zero_()
        head.query.weight[0, 0], head.query.weight[1, 1] = 1, 1
        head.key.weight[0, 2], head.key.weight[1, 3] = 1, 1
        head.drop.weight[6, 3] = 1
    hidden = torch.zeros(1, 729, 4)
    hidden[0, 0], hidden[0, 1] = torch.tensor([2, 4, 0, 0]), torch.tensor([0, 0, 3, 5])
    actual = head(hidden).detach().numpy()
    assert actual.shape == (1, ACTIONS)
    assert actual[0, 2] == 6  # from0 -> to1, no promotion
    assert actual[0, 3] == 20  # same pair, promotion
    assert actual[0, 1_067_257] == 5  # rook drop -> to1
    assert np.count_nonzero(actual) == 3


def test_representative_model_size_seed_and_real_input_dependence():
    torch.set_num_threads(1)
    model = make_model(314159)
    assert sum(p.numel() for p in model.parameters()) == 5_021_064
    assert 5_000_000 <= sum(p.numel() for p in model.parameters()) <= 10_000_000
    again = make_model(314159)
    for key, value in model.state_dict().items():
        torch.testing.assert_close(value, again.state_dict()[key], rtol=0, atol=0)
    changed = make_model(271828)
    assert not torch.equal(model.input.weight, changed.input.weight)
    inputs = torch.zeros(1, 729, 43)
    inputs[:, :, 0] = 1
    calls = []
    hooks = [
        block.register_forward_hook(lambda *_: calls.append(True))
        for block in model.blocks
    ]
    with torch.inference_mode():
        policy, value = model(inputs)
        for hook in hooks:
            hook.remove()
        different_policy, different_value = model(inputs + 0.25)
    assert len(calls) == 6  # all six layers must execute, not just own unused weights
    assert policy.shape == (1, 1_067_985)
    assert value.shape == (1, 1)
    assert torch.isfinite(policy).all() and torch.isfinite(value).all()
    assert torch.count_nonzero(policy) > 1_000_000
    assert -1 <= value.item() <= 1
    assert (policy - different_policy).abs().max() > 0.001
    assert (value - different_value).abs().max() > 0.001
