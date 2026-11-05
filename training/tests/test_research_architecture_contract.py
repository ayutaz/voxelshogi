"""Hand-counted architecture metadata; never imports Torch on the Mac."""

from dataclasses import FrozenInstanceError, replace

import pytest


def test_four_m_configs_have_hand_counted_20_to_35m_parameters():
    from export.research_contract import architecture_config, parameter_count

    expected = {
        "full": 25_783_688,
        "axial": 25_783_688,
        "geometry": 26_098_120,
        "cnn": 28_606_344,
    }
    for name, count in expected.items():
        config = architecture_config(name)
        assert config.side == 9 and config.layers == 8
        assert parameter_count(config) == count
        assert 20_000_000 <= count <= 35_000_000
        with pytest.raises(FrozenInstanceError):
            config.width = 1
    with pytest.raises(ValueError):
        architecture_config("unknown")


def test_linear_convolution_and_attention_mac_flops_are_separately_defined():
    from export.research_contract import ResearchConfig, forward_matmul_flops

    # n=8, width8, rank2, value hidden64. Common stem+heads = 9088 FLOPs.
    # Full: 4096 projection + 2048 attention + 4096 FFN = 10240.
    # Axial: 3*4096 projection + 1536 attention + 4096 FFN = 17920.
    # CNN: two dense 3^3 convolutions = 55296, including padded multiplications.
    for name, expected in (
        ("full", 19328),
        ("geometry", 19328),
        ("axial", 27008),
        ("cnn", 64384),
    ):
        config = ResearchConfig(
            architecture=name, side=2, width=8, layers=1, heads=2, ffn=16, policy_rank=2
        )
        assert forward_matmul_flops(config) == expected
        assert forward_matmul_flops(replace(config, layers=2)) > expected


def test_signed_xyz_relative_bias_index_uses_query_minus_key():
    from export.research_contract import relative_bias_index

    assert relative_bias_index((1, 0, 1), (0, 1, 0), side=2) == 20
    assert relative_bias_index((0, 1, 0), (1, 0, 1), side=2) == 6
    assert relative_bias_index((1, 0, 1), (1, 0, 1), side=2) == 13
    assert relative_bias_index((8, 0, 8), (0, 8, 0), side=9) == 4640
    assert relative_bias_index((0, 0, 0), (0, 0, 0), side=9) == 2456
    for invalid in ((-1, 0, 0), (2, 0, 0), (0, True, 0), (0, 0)):
        with pytest.raises(ValueError):
            relative_bias_index(invalid, (0, 0, 0), side=2)


@pytest.mark.parametrize(
    "field,value",
    [
        ("architecture", "unknown"),
        ("side", True),
        ("side", 1),
        ("side", 10),
        ("width", 0),
        ("layers", 0),
        ("heads", 3),
        ("ffn", 7),
        ("policy_rank", False),
    ],
)
def test_invalid_config_cannot_reach_model_construction(field, value):
    from export.research_contract import ResearchConfig

    args = dict(
        architecture="full", side=2, width=8, layers=1, heads=2, ffn=16, policy_rank=2
    )
    args[field] = value
    with pytest.raises(ValueError):
        ResearchConfig(**args)
