"""Alternating side-to-move research environment; no opponent policy is hidden."""

import gymnasium as gym
import numpy as np

from . import ACTIONS, Game


class VoxelShogiEnv(gym.Env):
    """Each step acts for the current side; reward is for that step's actor."""

    metadata = {"render_modes": []}

    def __init__(self, initial=None, max_plies=400):
        if type(max_plies) is not int or max_plies < 1:
            raise ValueError("max_plies must be positive")
        self.initial, self.max_plies = initial, max_plies
        self.action_space = gym.spaces.Discrete(ACTIONS)
        self.observation_space = gym.spaces.Box(0, 1, (729, 43), np.float32)
        self.game = None
        self._done = True
        self._steps = 0

    def _observation(self):
        s = self.game.snapshot()
        return self.game.features(), {**s, "action_mask": self.game.action_masks()}

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self.game = Game(self.initial)
        self._steps = 0
        self._done = self.game.snapshot()["finished"]
        return self._observation()

    def step(self, action):
        if self._done:
            raise RuntimeError("reset required after termination/truncation")
        legal = self.game.legal_actions()
        if not self.action_space.contains(action) or action not in legal:
            raise ValueError("illegal action")
        actor = self.game.snapshot()["side"]
        self.game.play(legal[action])
        self._steps += 1
        s = self.game.snapshot()
        terminated = s["finished"]
        truncated = not terminated and self._steps >= self.max_plies
        self._done = terminated or truncated
        reward = 0.0
        if s["result"] and "Win" in s["result"]:
            winner = "b" if s["result"]["Win"]["winner"] == "Black" else "w"
            reward = 1.0 if winner == actor else -1.0
        observation, info = self._observation()
        return observation, reward, terminated, truncated, info
