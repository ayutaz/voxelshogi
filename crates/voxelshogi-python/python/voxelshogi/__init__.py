"""Python access to the single Rust rules engine and versioned tensor encoding."""

import json

import numpy as np

from ._native import Engine

ACTIONS = 1067985
RULESET_ID = "voxelshogi-standard-v1"


class Game:
    """A complete history; constructing from VSFEN starts a new history."""

    def __init__(self, initial=None):
        self._engine = Engine(initial)

    @classmethod
    def from_record(cls, record):
        game = cls.__new__(cls)
        game._engine = Engine.from_record(json.dumps(record, allow_nan=False))
        return game

    def record(self):
        return json.loads(self._engine.record())

    def fork(self):
        """Independent copy of the Rust session, including repetition history."""
        game = self.__class__.__new__(self.__class__)
        game._engine = self._engine.fork()
        return game

    def snapshot(self):
        return json.loads(self._engine.snapshot())

    def play(self, text):
        self._engine.play(text)

    def search(self, **limits):
        return json.loads(self._engine.search(**limits))

    def legal_actions(self):
        """Canonical policy ID -> engine-supplied ASCII move. No rule decisions."""
        s = self.snapshot()

        def square(text):
            x, y, z = (int(c) - 1 for c in text)
            index = z * 81 + y * 9 + x
            return index if s["side"] == "b" else 728 - index

        actions = {}
        for text in s["legal_moves"]:
            if text[1] == "*":
                action = 1062882 + "PLNSGBR".index(text[0]) * 729 + square(text[2:])
            else:
                action = 2 * (
                    square(text[:3]) * 729 + square(text[3:6])
                ) + text.endswith("+")
            actions[action] = text
        return actions

    def action_masks(self):
        mask = np.zeros(ACTIONS, dtype=np.bool_)
        mask[list(self.legal_actions())] = True
        return mask

    def features(self):
        """M3 features [729,43], canonical to the side to move; Rust validates."""
        s = self.snapshot()
        board = np.array(s["board"], dtype=np.int64)
        hands = np.array(s["hands"], dtype=np.float32).reshape(2, 7)
        if s["side"] == "w":
            board = board[::-1]
            board = np.where(board == 0, 0, (board - 1 + 14) % 28 + 1)
            hands = hands[::-1]
        out = np.zeros((729, 43), dtype=np.float32)
        out[np.arange(729), board] = 1
        out[:, 29:] = (
            hands / np.array([162, 64, 48, 32, 16, 24, 24], np.float32)
        ).reshape(14)
        return out
