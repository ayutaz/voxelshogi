"""IEEE754 hand sums distinguish a fixed rank order from a reduction tree."""

import struct

import pytest


def f32(value):
    return struct.unpack("f", struct.pack("f", value))[0]


class Vector:
    def __init__(self, values, dtype="float32"):
        self.values = [f32(v) for v in values]
        self.shape = (len(values),)
        self.dtype = dtype

    def clone(self):
        return Vector(self.values, self.dtype)

    def add_(self, other):
        self.values = [
            f32(x + y) for x, y in zip(self.values, other.values, strict=True)
        ]
        return self

    def div_(self, value):
        self.values = [f32(x / value) for x in self.values]
        return self


@pytest.mark.parametrize(
    "values,expected",
    [
        ([[3, 7]], [3, 7]),
        ([[-3, 5], [7, 9]], [2, 7]),
        ([[100_000_000, 4], [1, 8], [-100_000_000, 12], [1, 16]], [0.25, 10]),
        ([[100_000_000], [-100_000_000], [1], [1]], [0.5]),
    ],
)
def test_fixed_rank_average_matches_hand_fp32_rounding_without_mutating_inputs(
    values, expected
):
    from training.distributed_training import rank_ordered_mean

    buffers = [Vector(v) for v in values]
    result = rank_ordered_mean(buffers)
    assert result.values == expected
    assert result is not buffers[0]
    assert [v.values for v in buffers] == values


@pytest.mark.parametrize(
    "buffers",
    [
        [],
        [Vector([1])] * 3,
        [Vector([1]), Vector([1, 2])],
        [Vector([1]), Vector([1], dtype="float64")],
    ],
)
def test_invalid_rank_count_or_bucket_layout_is_rejected(buffers):
    from training.distributed_training import rank_ordered_mean

    with pytest.raises(ValueError):
        rank_ordered_mean(buffers)
