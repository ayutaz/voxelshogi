"""The reduction strategy is explicit, while old state stays readable."""

import pytest

from training.distributed_training import (
    DistributedConfig,
    validate_distributed_binding,
)


def fixture(schema, **extra):
    return {
        "source_commit": "a" * 40,
        "cache_sha256": "b" * 64,
        "config": DistributedConfig(device="cpu").value(),
        "contract": {
            "schema": schema,
            "source_commit": "a" * 40,
            "initial_model_sha256": "c" * 64,
            "architecture": "transformer-s-full-v1",
            "world_size": 4,
            "schedule_sha256": "d" * 64,
            **extra,
        },
    }


def test_v1_archives_keep_their_old_reduction_contract():
    validate_distributed_binding(fixture("voxelshogi-distributed-training-v1"))


def test_v2_requires_the_literal_fixed_rank_fp32_strategy():
    validate_distributed_binding(
        fixture(
            "voxelshogi-distributed-training-v2",
            gradient_reduction="rank-ordered-float32-v1",
        )
    )


@pytest.mark.parametrize(
    "schema,extra",
    [
        ("voxelshogi-distributed-training-v2", {}),
        (
            "voxelshogi-distributed-training-v2",
            {"gradient_reduction": "default-all-reduce"},
        ),
        (
            "voxelshogi-distributed-training-v1",
            {"gradient_reduction": "rank-ordered-float32-v1"},
        ),
        (
            "voxelshogi-distributed-training-v3",
            {"gradient_reduction": "rank-ordered-float32-v1"},
        ),
    ],
)
def test_missing_unknown_or_relabelled_reduction_is_rejected(schema, extra):
    with pytest.raises(ValueError):
        validate_distributed_binding(fixture(schema, **extra))
