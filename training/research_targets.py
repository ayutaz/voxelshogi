"""Sparse policy labels and explicit value origins for research datasets.

These functions translate verified metadata. Rust supplies legal actions, sides,
and terminal results; no game rules or model execution are implemented here.
"""

import math
import re

from training.evaluation import classify_result

ACTIONS = 1_067_985


def _integer(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def visit_policy(legal_actions, visits):
    if (
        not isinstance(legal_actions, (list, tuple))
        or not legal_actions
        or any(not _integer(action, 0, ACTIONS - 1) for action in legal_actions)
        or len(set(legal_actions)) != len(legal_actions)
        or not isinstance(visits, dict)
        or not visits
        or any(
            not _integer(action, 0, ACTIONS - 1)
            or action not in legal_actions
            or not _integer(count, 0, 2**63 - 1)
            for action, count in visits.items()
        )
    ):
        raise ValueError("invalid or illegal sparse policy visits")
    total = sum(visits.values())
    if total <= 0 or total > 2**63 - 1:
        raise ValueError("policy requires positive bounded completed visits")
    actions = sorted(action for action, count in visits.items() if count > 0)
    return {
        "kind": "visits-v1",
        "actions": actions,
        "probabilities": [visits[action] / total for action in actions],
        "visits": [visits[action] for action in actions],
        "total_visits": total,
    }


def terminal_value(result, sample_side):
    outcome = classify_result(result, sample_side)
    if outcome == "cutoff":
        raise ValueError(
            "cutoff is not a terminal draw label; explicit bootstrap required"
        )
    return {
        "kind": "terminal-v1",
        "value": {"win": 1.0, "loss": -1.0, "draw": 0.0}[outcome],
    }


def bootstrap_value(
    value, *, bootstrap_side, sample_side, remaining_plies, model_sha256, discount
):
    if (
        type(value) not in (int, float)
        or not math.isfinite(value)
        or not -1 <= value <= 1
        or bootstrap_side not in ("b", "w")
        or sample_side not in ("b", "w")
        or not _integer(remaining_plies, 0, 20000)
        or not isinstance(model_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", model_sha256) is None
        or type(discount) not in (int, float)
        or not math.isfinite(discount)
        or not 0 < discount <= 1
    ):
        raise ValueError("invalid bootstrap value, viewpoint, model, or horizon")
    sign = 1 if bootstrap_side == sample_side else -1
    return {
        "kind": "bootstrap-v1",
        "value": float(sign * value * discount**remaining_plies),
        "bootstrap_side": bootstrap_side,
        "model_sha256": model_sha256,
        "remaining_plies": remaining_plies,
        "discount": float(discount),
    }


def teacher_value(score, *, completed_depth, minimum_depth, value_scale):
    if (
        not _integer(score, -1_000_000, 1_000_000)
        or not _integer(minimum_depth, 1, 64)
        or not _integer(completed_depth, minimum_depth, 64)
        or type(value_scale) not in (int, float)
        or not math.isfinite(value_scale)
        or value_scale <= 0
    ):
        raise ValueError(
            "search target requires a valid score and completed minimum depth"
        )
    return {
        "kind": "search-score-v1",
        "value": math.tanh(score / value_scale),
        "score": score,
        "completed_depth": completed_depth,
        "value_scale": value_scale,
    }
