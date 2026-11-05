"""Four P6 structures with the existing feature and action-head contract.

No changes to the frozen M6 model or its checkpoint loader. Construct/execute
these models only on external Linux or CI, not the editing Mac.
"""

import math

import torch
from torch import nn

from export.contract import FEATURES
from export.model import Attention, PolicyHead
from export.research_contract import ResearchConfig


class GeometryAttention(Attention):
    def __init__(self, config):
        super().__init__(config.width, config.heads)
        side = config.side
        radix = 2 * side - 1
        tokens = torch.arange(side**3)
        coordinates = torch.stack(
            (tokens % side, tokens // side % side, tokens // (side * side)), dim=-1
        )
        delta = coordinates[:, None, :] - coordinates[None, :, :] + side - 1
        relative_index = (
            delta[..., 0] + radix * delta[..., 1] + radix * radix * delta[..., 2]
        )
        self.register_buffer("relative_index", relative_index, persistent=False)
        self.bias = nn.Parameter(torch.zeros(config.heads, radix**3))

    def forward(self, x):
        batch, tokens, width = x.shape
        query, key, value = (
            self.qkv(x)
            .reshape(batch, tokens, 3, self.heads, self.dim)
            .permute(2, 0, 3, 1, 4)
            .unbind(0)
        )
        scores = (query @ key.transpose(-2, -1)) / math.sqrt(self.dim)
        scores = scores + self.bias[:, self.relative_index].unsqueeze(0)
        result = scores.softmax(dim=-1) @ value
        return self.out(result.transpose(1, 2).reshape(batch, tokens, width))


class AxialAttention(nn.Module):
    """Three sequential x/y/z line passes sharing QKV/out, then outer residual."""

    def __init__(self, config):
        super().__init__()
        self.side = config.side
        self.attention = Attention(config.width, config.heads)

    def forward(self, x):
        batch, _, width = x.shape
        grid = x.reshape(batch, self.side, self.side, self.side, width)
        # Grid dimensions are batch,z,y,x,channels; tokens use x-fast order.
        for axis in (3, 2, 1):
            permutation = [0] + [a for a in (1, 2, 3) if a != axis] + [axis, 4]
            inverse = [permutation.index(a) for a in range(5)]
            lines = grid.permute(permutation).reshape(
                batch * self.side * self.side, self.side, width
            )
            lines = self.attention(lines)
            grid = lines.reshape(batch, self.side, self.side, self.side, width).permute(
                inverse
            )
        return grid.reshape(batch, self.side**3, width)


class AttentionBlock(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.norm1, self.norm2 = nn.LayerNorm(config.width), nn.LayerNorm(config.width)
        if config.architecture == "geometry":
            self.attention = GeometryAttention(config)
        elif config.architecture == "axial":
            self.attention = AxialAttention(config)
        else:
            self.attention = Attention(config.width, config.heads)
        self.ffn = nn.Sequential(
            nn.Linear(config.width, config.ffn),
            nn.GELU(approximate="tanh"),
            nn.Linear(config.ffn, config.width),
        )

    def forward(self, x):
        x = x + self.attention(self.norm1(x))
        return x + self.ffn(self.norm2(x))


class TokenConv(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.side = config.side
        self.conv = nn.Conv3d(config.width, config.width, 3, padding=1)

    def forward(self, x):
        batch, _, width = x.shape
        grid = x.transpose(1, 2).reshape(batch, width, self.side, self.side, self.side)
        return self.conv(grid).flatten(2).transpose(1, 2)


class ConvBlock(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.norm1, self.norm2 = nn.LayerNorm(config.width), nn.LayerNorm(config.width)
        self.conv1, self.conv2 = TokenConv(config), TokenConv(config)
        self.activation = nn.GELU(approximate="tanh")

    def forward(self, x):
        hidden = self.activation(self.conv1(self.norm1(x)))
        return x + self.conv2(self.norm2(hidden))


class ResearchModel(nn.Module):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.input = nn.Linear(FEATURES, config.width)
        self.position = nn.Parameter(torch.empty(1, config.side**3, config.width))
        nn.init.normal_(self.position, std=0.02)
        block = ConvBlock if config.architecture == "cnn" else AttentionBlock
        self.blocks = nn.Sequential(*(block(config) for _ in range(config.layers)))
        self.norm = nn.LayerNorm(config.width)
        self.policy = PolicyHead(width=config.width, rank=config.policy_rank)
        self.value = nn.Sequential(
            nn.Linear(config.width, 64),
            nn.GELU(approximate="tanh"),
            nn.Linear(64, 1),
            nn.Tanh(),
        )

    def forward(self, features):
        if (
            features.ndim != 3
            or features.shape[1] != self.config.side**3
            or features.shape[2] != FEATURES
        ):
            raise ValueError("research features must match batch, cube tokens, 43")
        hidden = self.norm(self.blocks(self.input(features) + self.position))
        return self.policy(hidden), self.value(hidden.mean(dim=1))


def make_research_model(config, *, seed):
    if (
        not isinstance(config, ResearchConfig)
        or type(seed) is not int
        or not 0 <= seed < 2**63
    ):
        raise ValueError("validated research config and integer seed required")
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(seed)
        result = ResearchModel(config)
    return result.eval()
