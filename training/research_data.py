"""Paired research teachers on one trajectory; metadata and injected game ports.

Actual Rust execution, Parquet, and corpus audits belong to the Linux runner.
The frozen M4/M6 contracts are deliberately not extended by this module.
"""

import hashlib
import json
import math
import re
from collections import Counter, defaultdict

from training.evaluation_v2_runner import position_identity
from training.research_targets import teacher_value
from training.supervision import CONFIG, REPO, REVISION, RULESET

SCHEMA = "voxelshogi-paired-teachers-v1"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _integer(value, low, high):
    return type(value) is int and low <= value <= high


def pilot_protocol(source_commit):
    return {
        "schema": SCHEMA,
        "ruleset_id": RULESET,
        "source_commit": source_commit,
        "frozen_corpus": {"repo_id": REPO, "revision": REVISION, "config": CONFIG},
        "games": [
            {
                "id": f"g{i:06d}",
                "seed": 9300 + i,
                "split": "train" if i < 5 else "val" if i < 7 else "test",
            }
            for i in range(8)
        ],
        "opening_plies": 16,
        "max_plies": 512,
        "sample_plies": [16, 48, 96, 160, 256, 384, 480],
        "trajectory": {"max_depth": 3, "max_nodes": 20000, "table_capacity": 4096},
        "teachers": {
            "shallow": {
                "max_depth": 2,
                "minimum_depth": 1,
                "max_nodes": 10000,
                "table_capacity": 4096,
            },
            "deep": {
                "max_depth": 3,
                "minimum_depth": 3,
                "max_nodes": 100000,
                "table_capacity": 4096,
            },
        },
        "value_scale": 1000,
        "acceptance": {"minimum_per_cell": 2, "minimum_deep_completion_fraction": 0.8},
    }


def _limits(value, *, teacher=False):
    keys = {"max_depth", "max_nodes", "table_capacity"}
    if teacher:
        keys.add("minimum_depth")
    if (
        type(value) is not dict
        or set(value) != keys
        or not _integer(value.get("max_depth"), 1, 3)
        or not _integer(value.get("max_nodes"), 1, 100000)
        or not _integer(value.get("table_capacity"), 0, 4096)
        or teacher
        and not _integer(value.get("minimum_depth"), 1, value["max_depth"])
    ):
        raise ValueError("invalid research search budget")
    return {k: v for k, v in value.items() if k != "minimum_depth"}


def validate_protocol(p):
    if (
        type(p) is not dict
        or set(p) != set(pilot_protocol("a" * 40))
        or p.get("schema") != SCHEMA
        or p.get("ruleset_id") != RULESET
        or not isinstance(p.get("source_commit"), str)
        or not re.fullmatch(r"[0-9a-f]{40}", p["source_commit"])
        or p.get("frozen_corpus")
        != {"repo_id": REPO, "revision": REVISION, "config": CONFIG}
        or not _integer(p.get("max_plies"), 1, 512)
        or not _integer(p.get("opening_plies"), 0, p["max_plies"])
        or p.get("value_scale") != 1000
        or type(p["value_scale"]) is not int
    ):
        raise ValueError("invalid research protocol identity or horizon")
    plies, games = p["sample_plies"], p["games"]
    if (
        type(plies) is not list
        or not plies
        or any(
            not _integer(n, p["opening_plies"], p["max_plies"]) or 64 < n < 96
            for n in plies
        )
        or plies != sorted(set(plies))
        or type(games) is not list
        or not 1 <= len(games) <= 8
    ):
        raise ValueError("invalid sample plies or game count")
    seeds = set()
    for i, spec in enumerate(games):
        if (
            type(spec) is not dict
            or set(spec) != {"id", "seed", "split"}
            or spec["id"] != f"g{i:06d}"
            or not _integer(spec["seed"], 0, 2**63 - 1)
            or spec["seed"] in seeds
            or spec["split"] not in ("train", "val", "test")
        ):
            raise ValueError("invalid game/family split")
        seeds.add(spec["seed"])
    _limits(p["trajectory"])
    if type(p["teachers"]) is not dict or set(p["teachers"]) != {"shallow", "deep"}:
        raise ValueError("both paired teachers are required")
    for limits in p["teachers"].values():
        _limits(limits, teacher=True)
    a = p["acceptance"]
    if (
        type(a) is not dict
        or set(a) != {"minimum_per_cell", "minimum_deep_completion_fraction"}
        or not _integer(a["minimum_per_cell"], 1, 56)
        or type(a["minimum_deep_completion_fraction"]) not in (int, float)
        or not 0 < a["minimum_deep_completion_fraction"] <= 1
    ):
        raise ValueError("invalid preregistered coverage screen")
    return fingerprint(p)


def input_identity(snapshot):
    """Compact exact identity for M3 [729,43] inputs, excluding history/ply.

    No rule decisions are made here. Counts are encoded before the fixed feature
    normalization; same side-canonical codes/counts imply identical FP32 inputs.
    """
    board, hands, side = (snapshot.get(k) for k in ("board", "hands", "side"))
    if (
        snapshot.get("ruleset_id") != RULESET
        or side not in ("b", "w")
        or type(board) is not list
        or len(board) != 729
        or any(not _integer(x, 0, 28) for x in board)
        or type(hands) is not list
        or len(hands) != 14
        or any(not _integer(x, 0, 65535) for x in hands)
    ):
        raise ValueError("invalid canonical feature identity metadata")
    if side == "w":
        board = [0 if x == 0 else (x - 1 + 14) % 28 + 1 for x in reversed(board)]
        hands = hands[7:] + hands[:7]
    return fingerprint(
        {
            "ruleset_id": RULESET,
            "features": "voxelshogi-standard-features-v1",
            "board": board,
            "hands": hands,
        }
    )


def _opening_move(seed, ply, legal):
    moves = sorted(legal.values())
    h = hashlib.sha256(f"p5-trajectory:{seed}:{ply}".encode()).digest()
    return moves[int.from_bytes(h, "big") % len(moves)]


def _checked_search(r, legal, limits):
    if (
        type(r) is not dict
        or set(r)
        != {
            "best_move",
            "score",
            "completed_depth",
            "nodes",
            "last_iteration_nodes",
            "tt_hits",
            "stop_reason",
        }
        or r.get("best_move") not in legal.values()
        or not _integer(r.get("completed_depth"), 0, limits["max_depth"])
        or not _integer(r.get("nodes"), 0, limits["max_nodes"])
        or not _integer(r.get("last_iteration_nodes"), 0, r["nodes"])
        or not _integer(r.get("tt_hits"), 0, r["nodes"])
        or r.get("stop_reason") not in ("depth", "nodes")
        or (r["completed_depth"] == 0 and r.get("score") is not None)
        or (
            r["completed_depth"] > 0 and not _integer(r.get("score"), -1000000, 1000000)
        )
    ):
        raise ValueError("invalid bounded search result")
    return r


def _search(game, limits):
    r = game.search(**_limits(limits, teacher="minimum_depth" in limits))
    return _checked_search(r, game.legal_actions(), limits)


def generate_game(p, spec, game_factory, *, stop_requested=lambda: False):
    protocol_hash = validate_protocol(p)
    if spec not in p["games"]:
        raise ValueError("game is not in the fixed protocol")
    game, rows = game_factory(), []
    for ply in range(p["max_plies"] + 1):
        if stop_requested():
            raise InterruptedError("partial research game is not eligible")
        s = game.snapshot()
        if s["finished"] or ply == p["max_plies"]:
            record, kind = game.record(), "natural" if s["finished"] else "cutoff"
            if kind == "cutoff":
                record.update(
                    termination="MaxPlies", result={"Draw": {"reason": "MaxPlies"}}
                )
            break
        legal = game.legal_actions()
        if not legal:
            raise ValueError("unfinished game has no legal action")
        if ply in p["sample_plies"]:
            teachers = {}
            for name, limits in p["teachers"].items():
                r = _search(game, limits)
                target = None
                if r["completed_depth"] >= limits["minimum_depth"]:
                    target = {
                        "policy": {
                            "kind": "best-move-v1",
                            "action": next(
                                a for a, m in legal.items() if m == r["best_move"]
                            ),
                        },
                        "value": teacher_value(
                            r["score"],
                            completed_depth=r["completed_depth"],
                            minimum_depth=limits["minimum_depth"],
                            value_scale=p["value_scale"],
                        ),
                    }
                teachers[name] = {"search": r, "target": target}
                if stop_requested():
                    raise InterruptedError("partial teacher annotation is not eligible")
            rows.append(
                {
                    "game_id": spec["id"],
                    "seed": spec["seed"],
                    "split": spec["split"],
                    "ply": ply,
                    "vsfen": s["vsfen"],
                    "side": s["side"],
                    "history": game.record()["moves"],
                    "physical_id": position_identity(s["vsfen"]),
                    "input_id": input_identity(s),
                    "legal_actions": sorted(legal),
                    "legal_moves": [legal[a] for a in sorted(legal)],
                    "teachers": teachers,
                }
            )
        move = (
            _opening_move(spec["seed"], ply, legal)
            if ply < p["opening_plies"]
            else _search(game, p["trajectory"])["best_move"]
        )
        if stop_requested():
            raise InterruptedError("partial trajectory is not eligible")
        game.play(move)
    return {
        "schema": SCHEMA,
        "protocol_sha256": protocol_hash,
        "game": dict(spec),
        "record": record,
        "termination_kind": kind,
        "samples": rows,
    }


def validate_game(p, spec, entry, game_factory, *, recompute):
    """Replay every move and independently check sample coverage and labels."""
    protocol_hash = validate_protocol(p)
    if (
        set(entry)
        != {
            "schema",
            "protocol_sha256",
            "game",
            "record",
            "termination_kind",
            "samples",
        }
        or entry["schema"] != SCHEMA
        or entry["protocol_sha256"] != protocol_hash
        or canonical(entry["game"]) != canonical(spec)
        or spec not in p["games"]
    ):
        raise ValueError("research game identity differs")
    game = game_factory()
    record, rows = entry["record"], entry["samples"]
    if record["initial"] != game.record()["initial"] or record["ruleset_id"] != RULESET:
        raise ValueError("trajectory must start at standard initial position")
    moves, index = record["moves"], 0
    if not isinstance(moves, list) or len(moves) > p["max_plies"]:
        raise ValueError("invalid trajectory length")
    for ply in range(len(moves) + 1):
        s = game.snapshot()
        legal = game.legal_actions()
        final = s["finished"] or ply == p["max_plies"]
        if final != (ply == len(moves)):
            raise ValueError("missing/extra terminal trajectory move")
        if not final and ply in p["sample_plies"]:
            if index >= len(rows):
                raise ValueError("missing paired sample")
            row = rows[index]
            expected = {
                "game_id": spec["id"],
                "seed": spec["seed"],
                "split": spec["split"],
                "ply": ply,
                "vsfen": s["vsfen"],
                "side": s["side"],
                "history": moves[:ply],
                "physical_id": position_identity(s["vsfen"]),
                "input_id": input_identity(s),
                "legal_actions": sorted(legal),
                "legal_moves": [legal[a] for a in sorted(legal)],
            }
            if set(row) != set(expected) | {"teachers"} or any(
                canonical(row[k]) != canonical(v) for k, v in expected.items()
            ):
                raise ValueError("research row differs from replay")
            if set(row["teachers"]) != {"shallow", "deep"}:
                raise ValueError("unpaired teachers")
            for name, limits in p["teachers"].items():
                annotation = row["teachers"][name]
                if set(annotation) != {"search", "target"}:
                    raise ValueError("invalid teacher metadata")
                r = _checked_search(annotation["search"], legal, limits)
                if recompute and r != _search(game, limits):
                    raise ValueError("teacher recomputation differs")
                target = None
                if r["completed_depth"] >= limits["minimum_depth"]:
                    action = next(
                        (a for a, m in legal.items() if m == r["best_move"]), None
                    )
                    if action is None:
                        raise ValueError("illegal teacher move")
                    target = {
                        "policy": {"kind": "best-move-v1", "action": action},
                        "value": {
                            "kind": "search-score-v1",
                            "value": math.tanh(r["score"] / p["value_scale"]),
                            "score": r["score"],
                            "completed_depth": r["completed_depth"],
                            "value_scale": p["value_scale"],
                        },
                    }
                if canonical(annotation["target"]) != canonical(target):
                    raise ValueError(
                        "teacher target differs from independent calculation"
                    )
            index += 1
        if not final:
            move = moves[ply]
            if move not in legal.values():
                raise ValueError("illegal trajectory move")
            if ply < p["opening_plies"]:
                if move != _opening_move(spec["seed"], ply, legal):
                    raise ValueError("seeded opening differs")
            elif recompute and move != _search(game, p["trajectory"])["best_move"]:
                raise ValueError("trajectory policy differs")
            game.play(move)
    expected_record = game.record()
    kind = "natural" if s["finished"] else "cutoff"
    if kind == "cutoff":
        expected_record.update(
            termination="MaxPlies", result={"Draw": {"reason": "MaxPlies"}}
        )
    if rows[index:] or entry["termination_kind"] != kind or record != expected_record:
        raise ValueError("game result or sample coverage differs")


def audit_samples(p, rows, *, protected):
    """Eligibility excludes frozen inputs and every cross-split collision.

    Metadata must first be checked by validate_game. This screen establishes
    coverage for a subsequent val-training comparison, not teacher superiority.
    """
    validate_protocol(p)
    groups = defaultdict(set)
    for r in rows:
        groups[r["input_id"]].add(r["split"])
    seen, exclusions = set(), Counter()
    cells = {
        s: {phase: {t: 0 for t in p["teachers"]} for phase in ("early", "late")}
        for s in ("train", "val", "test")
    }
    candidates, completed = Counter(), Counter()
    eligibility, agreements = [], Counter()
    for r in rows:
        identity = r["input_id"]
        reason = (
            "protected_input"
            if identity in protected
            else "cross_split_input"
            if len(groups[identity]) > 1
            else "duplicate_input"
            if identity in seen
            else None
        )
        seen.add(identity)
        eligibility.append(
            {"game_id": r["game_id"], "ply": r["ply"], "excluded": reason}
        )
        if reason:
            exclusions[reason] += 1
            continue
        phase = "early" if r["ply"] <= 64 else "late"
        for name, annotation in r["teachers"].items():
            if annotation["target"] is not None:
                cells[r["split"]][phase][name] += 1
        if r["split"] in ("train", "val"):
            candidates[phase] += 1
            completed[phase] += r["teachers"]["deep"]["target"] is not None
        if r["split"] == "val" and all(
            a["target"] is not None for a in r["teachers"].values()
        ):
            agreements[phase + "_paired"] += 1
            agreements[phase + "_same_action"] += (
                r["teachers"]["shallow"]["target"]["policy"]["action"]
                == r["teachers"]["deep"]["target"]["policy"]["action"]
            )
    fractions = {
        phase: completed[phase] / candidates[phase] if candidates[phase] else 0
        for phase in ("early", "late")
    }
    a = p["acceptance"]
    passed = all(
        cells[s][phase][name] >= a["minimum_per_cell"]
        for s in ("train", "val")
        for phase in ("early", "late")
        for name in p["teachers"]
    ) and all(f >= a["minimum_deep_completion_fraction"] for f in fractions.values())
    return {
        "candidate_rows": len(rows),
        "eligible_rows": len(rows) - sum(exclusions.values()),
        "exclusions": dict(exclusions),
        "cells": cells,
        "eligibility": eligibility,
        "selection_splits": ["train", "val"],
        "deep_completion_fraction": fractions,
        "val_teacher_agreement": dict(agreements),
        "screen_passed": passed,
        "screen_scope": "coverage only; no teacher-strength or learning improvement claim",
    }
