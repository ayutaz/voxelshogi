"""Deterministic bounded PUCT, with rules and complete histories supplied by Rust.

The kernel accepts an adapter exposing fork/snapshot/legal_actions/play and an
evaluator returning all legal priors plus a side-to-move value in [-1, 1]. Each
call owns a fresh tree; no state/model/history cache is shared between calls.
"""

import math
from dataclasses import dataclass, field

from training.research_targets import ACTIONS, terminal_value


@dataclass(frozen=True)
class SearchConfig:
    simulations: int = 32
    max_depth: int = 64
    cpuct: float = 1.0

    def __post_init__(self):
        if (
            type(self.simulations) is not int
            or not 1 <= self.simulations <= 100000
            or type(self.max_depth) is not int
            or not 1 <= self.max_depth <= 256
            or type(self.cpuct) not in (int, float)
            or not math.isfinite(self.cpuct)
            or not 0 < self.cpuct <= 100
        ):
            raise ValueError("invalid bounded PUCT configuration")


@dataclass
class _Node:
    prior: float = 1.0
    side: str | None = None
    visits: int = 0
    value_sum: float = 0.0
    estimate: float | None = None
    terminal: bool = False
    moves: dict = field(default_factory=dict)
    children: dict = field(default_factory=dict)


def _snapshot(game):
    snapshot = game.snapshot()
    if (
        snapshot.get("side") not in ("b", "w")
        or type(snapshot.get("finished")) is not bool
        or (not snapshot["finished"] and snapshot.get("result") is not None)
    ):
        raise ValueError("invalid engine viewpoint or terminal status")
    return snapshot


def _expand(node, game, evaluate):
    snapshot = _snapshot(game)
    node.side = snapshot["side"]
    if snapshot["finished"]:
        node.estimate = terminal_value(snapshot["result"], node.side)["value"]
        node.terminal = True
        return 0
    legal = game.legal_actions()
    if (
        not isinstance(legal, dict)
        or not legal
        or any(type(a) is not int or not 0 <= a < ACTIONS for a in legal)
        or any(not isinstance(move, str) or not move for move in legal.values())
    ):
        raise ValueError("unfinished node must have engine-supplied legal actions")
    priors, value = evaluate(game)
    if (
        not isinstance(priors, dict)
        or set(priors) != set(legal)
        or any(type(a) is not int for a in priors)
        or any(
            type(p) not in (int, float) or not math.isfinite(p) or not 0 <= p <= 1
            for p in priors.values()
        )
        or not math.isclose(math.fsum(priors.values()), 1, rel_tol=0, abs_tol=1e-6)
        or type(value) not in (int, float)
        or not math.isfinite(value)
        or not -1 <= value <= 1
    ):
        raise ValueError(
            "model priors/value differ from the legal probability contract"
        )
    node.moves = {action: legal[action] for action in sorted(legal)}
    node.children = {a: _Node(prior=float(priors[a])) for a in node.moves}
    node.estimate = float(value)
    return 1


def _select(node, cpuct):
    def score(action):
        child = node.children[action]
        q = (
            (1 if node.side == child.side else -1) * child.value_sum / child.visits
            if child.visits
            else 0.0
        )
        u = cpuct * child.prior * math.sqrt(max(1, node.visits)) / (1 + child.visits)
        return q + u, -action

    return max(node.children, key=score)


def search(root, evaluate, config, *, stop_requested=lambda: False):
    """Only completed simulations count. Cancellation may return no move.

    Depth-limited leaves use their explicit model estimate, never a draw label.
    No wall-clock limit is hidden in deterministic configuration: the supervisor
    may stop the call; that interrupted result is reported explicitly.
    """
    if not isinstance(config, SearchConfig):
        raise ValueError("a validated SearchConfig is required")
    tree = _Node()
    evaluations, completed, depth_reached = 0, 0, 0

    def result(reason):
        visits = {action: child.visits for action, child in tree.children.items()}
        best = max(visits, key=lambda a: (visits[a], -a)) if completed else None
        value = tree.value_sum / completed if completed else None
        if tree.terminal:
            value = tree.estimate
        return {
            "best_action": best,
            "visits": visits,
            "root_value": value,
            "completed_simulations": completed,
            "model_evaluations": evaluations,
            "max_depth_reached": depth_reached,
            "stop_reason": reason,
        }

    if stop_requested():
        return result("interrupted")
    evaluations += _expand(tree, root, evaluate)
    if tree.terminal:
        return result("terminal")
    for _ in range(config.simulations):
        if stop_requested():
            return result("interrupted")
        game, node, path, depth = root.fork(), tree, [tree], 0
        while not node.terminal and depth < config.max_depth:
            action = _select(node, config.cpuct)
            game.play(node.moves[action])
            node = node.children[action]
            path.append(node)
            depth += 1
            if node.estimate is None:
                if stop_requested():
                    return result("interrupted")
                evaluations += _expand(node, game, evaluate)
                break
        if stop_requested():
            return result("interrupted")
        depth_reached = max(depth_reached, depth)
        for ancestor in path:
            sign = 1 if ancestor.side == node.side else -1
            ancestor.value_sum += sign * node.estimate
            ancestor.visits += 1
        completed += 1
    return result("simulations")
