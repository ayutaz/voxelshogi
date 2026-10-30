"""Seeded episode orchestration over Rust game ports and bounded PUCT.

This module supplies no rules or model loader. Production ports must validate
histories in Rust and bind the evaluator to the declared immutable model hash.
Interrupted episodes are discarded and may be reexecuted from their seed/root;
only completed episodes are eligible for replay storage.
"""

import hashlib
import json
import math
import random
import re
from dataclasses import asdict, dataclass, field

from training.research_targets import (
    ACTIONS,
    bootstrap_value,
    terminal_value,
    visit_policy,
)
from training.selfplay_search import SearchConfig, search
from training.supervision import RULESET


def _number(value, low, high):
    return type(value) in (int, float) and low <= value <= high and math.isfinite(value)


def _temperature(value):
    return _number(value, 0, 5) and (value == 0 or value >= 0.01)


@dataclass(frozen=True)
class ActorConfig:
    seed: int = 314159
    max_plies: int = 256
    temperature: float = 1.0
    temperature_plies: int = 16
    noise_fraction: float = 0.25
    noise_alpha: float = 0.3
    bootstrap_discount: float = 1.0
    search: SearchConfig = field(default_factory=SearchConfig)

    def __post_init__(self):
        if (
            type(self.seed) is not int
            or not 0 <= self.seed <= 2**63 - 1
            or type(self.max_plies) is not int
            or not 1 <= self.max_plies <= 20000
            or type(self.temperature_plies) is not int
            or not 0 <= self.temperature_plies <= self.max_plies
            or not _temperature(self.temperature)
            or not _number(self.noise_fraction, 0, 1)
            or not _number(self.noise_alpha, 0.001, 10)
            or not _number(self.bootstrap_discount, 0.000001, 1)
            or not isinstance(self.search, SearchConfig)
        ):
            raise ValueError("invalid actor limits, seed, or sampling configuration")


def sample_action(visits, temperature, rng):
    if not isinstance(visits, dict) or not _temperature(temperature):
        raise ValueError("invalid visits or temperature")
    target = visit_policy(list(visits), visits)
    actions, counts = target["actions"], target["visits"]
    if temperature == 0:
        return max(actions, key=lambda a: (visits[a], -a))
    logs = [math.log(n) / temperature for n in counts]
    maximum = max(logs)
    weights = [math.exp(x - maximum) for x in logs]
    draw = rng.random()
    if not _number(draw, 0, 1) or draw == 1:
        raise ValueError("sampling RNG must return a finite value in [0,1)")
    threshold, cumulative = draw * math.fsum(weights), 0.0
    for action, weight in zip(actions, weights, strict=True):
        cumulative += weight
        if threshold < cumulative:
            return action
    return actions[-1]  # Only accumulated floating-point rounding can reach here.


def mix_dirichlet(priors, fraction, alpha, rng):
    if (
        not isinstance(priors, dict)
        or not priors
        or any(type(a) is not int or not 0 <= a < ACTIONS for a in priors)
        or any(not _number(p, 0, 1) for p in priors.values())
        or not math.isclose(math.fsum(priors.values()), 1, rel_tol=0, abs_tol=1e-6)
        or not _number(fraction, 0, 1)
        or not _number(alpha, 0.001, 10)
    ):
        raise ValueError("invalid legal priors or root-noise configuration")
    actions = sorted(priors)
    if fraction == 0:
        return {a: priors[a] for a in actions}
    noise = [rng.gammavariate(alpha, 1) for _ in actions]
    if any(not _number(x, 0, float("inf")) for x in noise) or math.fsum(noise) <= 0:
        raise ValueError("root noise must have positive finite mass")
    total = math.fsum(noise)
    return {
        a: (1 - fraction) * priors[a] + fraction * n / total
        for a, n in zip(actions, noise, strict=True)
    }


def _digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def _rng(config, model_sha256, record, stream):
    seed = _digest(
        {
            "seed": config.seed,
            "model_sha256": model_sha256,
            "record": record,
            "stream": stream,
        }
    )
    return random.Random(int(seed, 16))


def _snapshot(game):
    snapshot = game.snapshot()
    if (
        snapshot.get("ruleset_id") != RULESET
        or snapshot.get("side") not in ("b", "w")
        or type(snapshot.get("finished")) is not bool
        or not isinstance(snapshot.get("vsfen"), str)
        or not snapshot["vsfen"]
        or (not snapshot["finished"] and snapshot.get("result") is not None)
    ):
        raise ValueError("invalid Rust game snapshot")
    return snapshot


def play_episode(
    root, evaluate, config, *, model_sha256, source_commit, stop_requested=lambda: False
):
    if (
        not isinstance(config, ActorConfig)
        or not isinstance(model_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", model_sha256) is None
        or not isinstance(source_commit, str)
        or re.fullmatch(r"[0-9a-f]{40}", source_commit) is None
    ):
        raise ValueError("a validated actor configuration and model hash are required")
    initial = _snapshot(root)
    if initial["finished"]:
        raise ValueError("episode opening must be unfinished")
    opening, game, samples = root.record(), root.fork(), []
    bootstrap = None
    bootstrap_evaluations = 0
    prefix = len(opening["moves"])
    if opening["ruleset_id"] != RULESET:
        raise ValueError("episode opening ruleset differs")
    while True:
        snapshot = _snapshot(game)
        if snapshot["finished"]:
            terminal_value(snapshot["result"], snapshot["side"])
            record, kind = game.record(), "natural"
            for sample in samples:
                sample["value"] = terminal_value(snapshot["result"], sample["side"])
            break
        if stop_requested():
            raise InterruptedError("incomplete episode is not replay-eligible")
        ply = len(game.record()["moves"])
        if ply - prefix >= config.max_plies:
            priors, value = evaluate(game)
            bootstrap_evaluations += 1
            if set(priors) != set(game.legal_actions()):
                raise ValueError("bootstrap priors differ from engine legal actions")
            mix_dirichlet(
                priors,
                0,
                config.noise_alpha,
                _rng(config, model_sha256, game.record(), "bootstrap"),
            )
            if stop_requested():
                raise InterruptedError("bootstrap interrupted; no completed episode")
            for sample in samples:
                sample["value"] = bootstrap_value(
                    value,
                    bootstrap_side=snapshot["side"],
                    sample_side=sample["side"],
                    remaining_plies=ply - sample["ply"],
                    model_sha256=model_sha256,
                    discount=config.bootstrap_discount,
                )
            bootstrap = {"value": float(value), "side": snapshot["side"], "ply": ply}
            record, kind = game.record(), "cutoff"
            record.update(
                termination="MaxPlies", result={"Draw": {"reason": "MaxPlies"}}
            )
            break
        history = game.record()
        first = True

        def evaluate_search(position):
            nonlocal first
            priors, value = evaluate(position)
            if first:
                first = False
                priors = mix_dirichlet(
                    priors,
                    config.noise_fraction,
                    config.noise_alpha,
                    _rng(config, model_sha256, history, "root-noise"),
                )
            return priors, value

        result = search(
            game, evaluate_search, config.search, stop_requested=stop_requested
        )
        if result["stop_reason"] != "simulations" or stop_requested():
            raise InterruptedError("incomplete search is not a completed episode")
        legal = game.legal_actions()
        policy = visit_policy(sorted(legal), result["visits"])
        temperature = (
            config.temperature if ply - prefix < config.temperature_plies else 0
        )
        action = sample_action(
            result["visits"], temperature, _rng(config, model_sha256, history, "action")
        )
        if action not in legal:
            raise ValueError("actor selected an illegal action")
        sample = {
            "ply": ply,
            "side": snapshot["side"],
            "position": snapshot["vsfen"],
            "legal_actions": sorted(legal),
            "policy": policy,
            "action": action,
            "move": legal[action],
            "search": {k: v for k, v in result.items() if k != "visits"},
        }
        game.play(legal[action])
        samples.append(sample)
    if not samples:
        raise ValueError("completed episode has no played training samples")
    conditions = {
        "source_commit": source_commit,
        "config": asdict(config),
        "opening": opening,
        "model_sha256": model_sha256,
    }
    return {
        "schema": "voxelshogi-selfplay-episode-v2",
        "episode_id": _digest(conditions),
        **conditions,
        "complete": True,
        "bootstrap": bootstrap,
        "bootstrap_evaluations": bootstrap_evaluations,
        "model_evaluations": sum(s["search"]["model_evaluations"] for s in samples)
        + bootstrap_evaluations,
        "termination_kind": kind,
        "record": record,
        "samples": samples,
    }
