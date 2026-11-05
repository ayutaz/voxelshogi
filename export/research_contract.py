"""Immutable P6 model dimensions and explicit dense-MAC accounting, no Torch."""

from dataclasses import dataclass

from export.contract import FEATURES

ARCHITECTURES = ("full", "axial", "geometry", "cnn")


@dataclass(frozen=True)
class ResearchConfig:
    architecture: str
    side: int = 9
    width: int = 512
    layers: int = 8
    heads: int = 8
    ffn: int = 2048
    policy_rank: int = 64

    def __post_init__(self):
        dimensions = (
            self.side,
            self.width,
            self.layers,
            self.heads,
            self.ffn,
            self.policy_rank,
        )
        if (
            self.architecture not in ARCHITECTURES
            or any(type(n) is not int or n <= 0 for n in dimensions)
            or not 2 <= self.side <= 9
            or self.width % self.heads
            or self.ffn < self.width
        ):
            raise ValueError("invalid research architecture dimensions")


def architecture_config(name):
    return ResearchConfig(architecture=name, width=256 if name == "cnn" else 512)


def parameter_count(config):
    """Trainable tensors only; axial reuses QKV/out across its three axes."""
    n, w, f, r = config.side**3, config.width, config.ffn, config.policy_rank
    stem = (FEATURES + 1) * w + n * w + 2 * w
    heads = 2 * (w + 1) * (2 * r) + (w + 1) * 7 + (w + 1) * 64 + 65
    if config.architecture == "cnn":
        block = 2 * (27 * w * w + w) + 4 * w
    else:
        block = 4 * w * w + 4 * w + 2 * w * f + f + w + 4 * w
        if config.architecture == "geometry":
            block += config.heads * (2 * config.side - 1) ** 3
    return stem + heads + config.layers * block


def forward_matmul_flops(config):
    """Per-example FP multiply/add count, one multiply-add = two FLOPs.

    Includes stem, Policy/Value heads, dense projections, attention QK/AV,
    FFNs and dense padded convolutions. Excludes backward, normalization,
    activations/softmax, bias additions, indexing and IO. This is an explicit
    accounting component, not measured total FLOPs or a runtime prediction.
    """
    n, w, f, r = config.side**3, config.width, config.ffn, config.policy_rank
    common = (
        2 * n * FEATURES * w
        + 8 * n * w * r
        + 4 * n * n * r
        + 14 * n * w
        + 128 * w
        + 128
    )
    if config.architecture == "cnn":
        block = 108 * n * w * w
    else:
        projections = 8 * n * w * w
        attention = 4 * n * n * w
        if config.architecture == "axial":
            projections *= 3
            attention = 12 * n * config.side * w
        block = projections + attention + 4 * n * w * f
    return common + config.layers * block


def relative_bias_index(query, key, *, side):
    """Scalar reference: x fastest, then y then z, signed query minus key."""
    if (
        type(side) is not int
        or not 2 <= side <= 9
        or any(not isinstance(c, (tuple, list)) or len(c) != 3 for c in (query, key))
        or any(type(v) is not int or not 0 <= v < side for c in (query, key) for v in c)
    ):
        raise ValueError("invalid relative-bias coordinate")
    radix = 2 * side - 1
    dx, dy, dz = (q - k + side - 1 for q, k in zip(query, key, strict=True))
    return dx + radix * dy + radix * radix * dz
