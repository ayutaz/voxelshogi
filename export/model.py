"""Untrained representative Full Attention model for browser feasibility."""

import math

import torch
from torch import nn

from export.contract import FEATURES, SQUARES

SEED = 314159
CONFIG = {"width": 256, "layers": 6, "heads": 8, "ffn": 1024, "policy_rank": 64}


class Attention(nn.Module):
    def __init__(self, width=256, heads=8):
        super().__init__()
        self.heads = heads
        self.dim = width // heads
        self.qkv = nn.Linear(width, 3 * width)
        self.out = nn.Linear(width, width)

    def forward(self, x):
        batch, tokens, width = x.shape
        query, key, value = (
            self.qkv(x)
            .reshape(batch, tokens, 3, self.heads, self.dim)
            .permute(2, 0, 3, 1, 4)
            .unbind(0)
        )
        scores = (query @ key.transpose(-2, -1)) / math.sqrt(self.dim)
        result = scores.softmax(dim=-1) @ value
        return self.out(result.transpose(1, 2).reshape(batch, tokens, width))


class Block(nn.Module):
    def __init__(self):
        super().__init__()
        self.norm1, self.norm2 = nn.LayerNorm(256), nn.LayerNorm(256)
        self.attention = Attention()
        self.ffn = nn.Sequential(
            nn.Linear(256, 1024), nn.GELU(approximate="tanh"), nn.Linear(1024, 256)
        )

    def forward(self, x):
        x = x + self.attention(self.norm1(x))
        return x + self.ffn(self.norm2(x))


class PolicyHead(nn.Module):
    def __init__(self, width=256, rank=64):
        super().__init__()
        self.rank = rank
        self.query, self.key = nn.Linear(width, 2 * rank), nn.Linear(width, 2 * rank)
        self.drop = nn.Linear(width, 7)

    def forward(self, x):
        batch, tokens, _ = x.shape
        query = self.query(x).reshape(batch, tokens, 2, self.rank).permute(0, 2, 1, 3)
        key = self.key(x).reshape(batch, tokens, 2, self.rank).permute(0, 2, 1, 3)
        pair = (query @ key.transpose(-2, -1)) / math.sqrt(self.rank)
        # Adjacent labels distinguish promotion for each from/to pair.
        pair = pair.permute(0, 2, 3, 1).reshape(batch, 2 * tokens * tokens)
        drop = self.drop(x).transpose(1, 2).reshape(batch, 7 * tokens)
        return torch.cat((pair, drop), dim=1)


class RepresentativeModel(nn.Module):
    def __init__(self):
        super().__init__()
        self.input = nn.Linear(FEATURES, 256)
        self.position = nn.Parameter(torch.empty(1, SQUARES, 256))
        nn.init.normal_(self.position, std=0.02)
        self.blocks = nn.Sequential(*(Block() for _ in range(6)))
        self.norm = nn.LayerNorm(256)
        self.policy = PolicyHead()
        self.value = nn.Sequential(
            nn.Linear(256, 64), nn.GELU(approximate="tanh"), nn.Linear(64, 1), nn.Tanh()
        )

    def forward(self, features):
        hidden = self.norm(self.blocks(self.input(features) + self.position))
        return self.policy(hidden), self.value(hidden.mean(dim=1))


def make_model(seed=SEED):
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(seed)
        model = RepresentativeModel()
    return model.eval()
