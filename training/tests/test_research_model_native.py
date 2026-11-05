"""Independent scalar spatial references, gradients and real ONNX, Linux only."""

import itertools
import math
from dataclasses import replace

import pytest


def tiny(name):
    from export.research_contract import ResearchConfig

    return ResearchConfig(
        architecture=name, side=2, width=4, layers=1, heads=2, ffn=8, policy_rank=2
    )


def identity_attention(attention):
    import torch

    with torch.no_grad():
        attention.qkv.weight.copy_(torch.eye(4).repeat(3, 1))
        attention.qkv.bias.zero_()
        attention.out.weight.copy_(torch.eye(4))
        attention.out.bias.zero_()


def scalar_attention(values, bias=None):
    """Identity Q/K/V/out, two heads; scalar Python double arithmetic."""
    answer = [[0.0] * 4 for _ in values]
    for row, head in itertools.product(range(len(values)), range(2)):
        channels = range(2 * head, 2 * head + 2)
        scores = [
            sum(values[row][c] * key[c] for c in channels) / math.sqrt(2)
            for key in values
        ]
        if bias is not None:
            scores = [s + bias(head, row, key) for key, s in enumerate(scores)]
        weights = [math.exp(s - max(scores)) for s in scores]
        for c in channels:
            answer[row][c] = sum(
                w * key[c] for w, key in zip(weights, values, strict=True)
            ) / sum(weights)
    return answer


def test_geometry_attention_matches_signed_xyz_scalar_reference():
    import torch

    from export.research_contract import relative_bias_index
    from export.research_model import GeometryAttention

    attention = GeometryAttention(tiny("geometry"))
    identity_attention(attention)
    with torch.no_grad():
        attention.bias[0].copy_(torch.arange(27).square() * 0.001)
        attention.bias[1].copy_(torch.arange(27) * -0.002)
    coordinates = [(i % 2, i // 2 % 2, i // 4) for i in range(8)]
    table = attention.bias.detach().tolist()
    for query, key in itertools.product(range(8), repeat=2):
        assert attention.relative_index[query, key].item() == relative_bias_index(
            coordinates[query], coordinates[key], side=2
        )
    values = [[(i * 4 + c - 11) / 17 for c in range(4)] for i in range(8)]
    expected = scalar_attention(
        values,
        lambda h, q, k: table[h][
            relative_bias_index(coordinates[q], coordinates[k], side=2)
        ],
    )
    actual = attention(torch.tensor([values])).detach()
    torch.testing.assert_close(actual, torch.tensor([expected]), rtol=1e-5, atol=1e-6)


def test_axial_attention_matches_three_explicit_scalar_line_passes():
    import torch

    from export.research_model import AxialAttention

    attention = AxialAttention(tiny("axial"))
    identity_attention(attention.attention)
    values = [[(i * 4 + c - 7) / 19 for c in range(4)] for i in range(8)]
    expected = values
    # x then y then z, x-fast token layout; no production reshape/permute used.
    for axis in range(3):
        next_values = [None] * 8
        other_axes = [a for a in range(3) if a != axis]
        for fixed in itertools.product(range(2), repeat=2):
            indices = []
            for variable in range(2):
                coordinate = [0, 0, 0]
                coordinate[axis] = variable
                for a, value in zip(other_axes, fixed, strict=True):
                    coordinate[a] = value
                x, y, z = coordinate
                indices.append(x + 2 * y + 4 * z)
            outputs = scalar_attention([expected[i] for i in indices])
            for index, output in zip(indices, outputs, strict=True):
                next_values[index] = output
        expected = next_values
    actual = attention(torch.tensor([values])).detach()
    torch.testing.assert_close(actual, torch.tensor([expected]), rtol=1e-5, atol=1e-6)


def test_cnn_token_grid_preserves_x_fast_xyz_and_zero_padding():
    import torch

    from export.research_model import TokenConv

    layer = TokenConv(tiny("cnn"))
    with torch.no_grad():
        layer.conv.weight.zero_()
        layer.conv.bias.zero_()
        layer.conv.weight[0, 0, 1, 1, 2] = 1  # input at x+1
    values = torch.zeros(1, 8, 4)
    values[0, :, 0] = torch.arange(1, 9)
    expected = torch.zeros_like(values)
    expected[0, [0, 2, 4, 6], 0] = torch.tensor([2.0, 4.0, 6.0, 8.0])
    torch.testing.assert_close(layer(values), expected, rtol=0, atol=0)


@pytest.mark.parametrize("name", ["full", "axial", "geometry", "cnn"])
def test_all_architectures_use_every_block_have_gradients_and_preserve_rng(name):
    import torch

    from export.research_model import make_research_model

    torch.set_num_threads(1)
    config = replace(tiny(name), layers=2)
    before = torch.get_rng_state().clone()
    network = make_research_model(config, seed=66001)
    assert torch.equal(before, torch.get_rng_state())
    again = make_research_model(config, seed=66001)
    changed = make_research_model(config, seed=66002)
    for key, tensor in network.state_dict().items():
        torch.testing.assert_close(tensor, again.state_dict()[key], rtol=0, atol=0)
    assert not torch.equal(network.input.weight, changed.input.weight)
    values = torch.linspace(-0.4, 0.5, 8 * 43).reshape(1, 8, 43)
    calls = []
    hooks = [
        block.register_forward_hook(lambda *_: calls.append(True))
        for block in network.blocks
    ]
    policy, value = network(values)
    assert calls == [True, True]
    for hook in hooks:
        hook.remove()
    assert policy.shape == (1, 184) and value.shape == (1, 1)
    assert torch.isfinite(policy).all() and torch.isfinite(value).all()
    other_policy, other_value = network(values + 0.1)
    assert not torch.equal(policy, other_policy) and not torch.equal(value, other_value)
    (policy.square().mean() + value.square().mean()).backward()
    for label, parameter in network.named_parameters():
        assert parameter.grad is not None and torch.isfinite(parameter.grad).all(), (
            label
        )
    assert any(p.grad.abs().sum() > 0 for p in network.blocks.parameters())


@pytest.mark.parametrize(
    "name,count",
    [
        ("full", 25_783_688),
        ("axial", 25_783_688),
        ("geometry", 26_098_120),
        ("cnn", 28_606_344),
    ],
)
def test_real_m_parameter_counts_match_handwritten_contract(name, count):
    import torch

    from export.research_contract import architecture_config, parameter_count
    from export.research_model import make_research_model

    torch.set_num_threads(1)
    config = architecture_config(name)
    network = make_research_model(config, seed=66001)
    assert (
        sum(p.numel() for p in network.parameters()) == count == parameter_count(config)
    )
    assert network.position.shape == (1, 729, config.width)


def test_invalid_input_cannot_broadcast_one_token_into_the_whole_cube():
    import torch

    from export.research_model import make_research_model

    network = make_research_model(tiny("full"), seed=66001)
    for shape in ((1, 1, 43), (8, 43), (1, 8, 42)):
        with pytest.raises(ValueError, match="research features"):
            network(torch.zeros(shape))
    for seed in (True, -1, 2**63):
        with pytest.raises(ValueError):
            make_research_model(tiny("full"), seed=seed)


@pytest.mark.parametrize("name", ["full", "axial", "geometry", "cnn"])
def test_real_onnx_export_matches_cpu_torch_on_distinct_inputs(name, tmp_path):
    import numpy as np
    import onnx
    import onnxruntime as ort
    import torch

    from export.research_model import make_research_model

    torch.set_num_threads(1)
    network = make_research_model(tiny(name), seed=66001)
    values = torch.linspace(-0.2, 0.4, 8 * 43).reshape(1, 8, 43)
    path = tmp_path / "model.onnx"
    torch.onnx.export(
        network,
        (values,),
        path,
        input_names=["features"],
        output_names=["policy", "value"],
        dynamo=True,
        opset_version=18,
        external_data=False,
    )
    onnx.checker.check_model(onnx.load(path), full_check=True)
    options = ort.SessionOptions()
    options.intra_op_num_threads = options.inter_op_num_threads = 1
    session = ort.InferenceSession(path, options, providers=["CPUExecutionProvider"])
    for inputs in (values, values * -1.5):
        with torch.inference_mode():
            expected = network(inputs)
        actual = session.run(None, {"features": inputs.numpy()})
        assert len(actual) == 2
        for reference, output in zip(expected, actual, strict=True):
            np.testing.assert_allclose(output, reference.numpy(), rtol=1e-4, atol=1e-5)
