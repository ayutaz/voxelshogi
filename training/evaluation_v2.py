"""Preregistered paired cohorts and descriptive statistics, without model execution.

This module validates metadata, not move legality. A Linux runner must replay all
openings/results through Rust before reporting a verified evaluation. Canonical
position identities for leakage checks must also come from that runner.
"""

import hashlib
import json
import math
import random
import re
from collections import Counter
from itertools import combinations

from training.evaluation import classify_result

SCHEMA = "voxelshogi-evaluation-v2"
RULESET = "voxelshogi-standard-v1"
STRATA = {"opening", "middlegame", "endgame", "tactical"}


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def _integer(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def _hash(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _record(record, *, unfinished=False):
    if (
        not isinstance(record, dict)
        or set(record) != {"ruleset_id", "initial", "moves", "result", "termination"}
        or record["ruleset_id"] != RULESET
        or not isinstance(record["initial"], str)
        or not record["initial"]
        or not isinstance(record["moves"], list)
        or any(not isinstance(move, str) or not move for move in record["moves"])
        or (
            unfinished
            and (record["result"] is not None or record["termination"] is not None)
        )
    ):
        raise ValueError("invalid evaluation record")


def validate_protocol(protocol):
    """Return the immutable condition digest; no game/engine execution occurs."""
    if (
        not isinstance(protocol, dict)
        or set(protocol)
        != {
            "schema",
            "purpose",
            "ruleset_id",
            "search_limits",
            "bootstrap",
            "sensitivity",
            "cases",
            "source_commit",
            "participants",
        }
        or protocol["schema"] != SCHEMA
        or protocol["purpose"] not in ("development", "holdout")
        or protocol["ruleset_id"] != RULESET
        or not isinstance(protocol["source_commit"], str)
        or re.fullmatch(r"[0-9a-f]{40}", protocol["source_commit"]) is None
    ):
        raise ValueError("invalid evaluation protocol")
    participants = protocol["participants"]
    if not isinstance(participants, dict) or set(participants) != {"model", "opponent"}:
        raise ValueError("invalid evaluation participants")
    for participant in participants.values():
        if (
            not isinstance(participant, dict)
            or set(participant) != {"artifact_sha256", "backend", "policy"}
            or not _hash(participant["artifact_sha256"])
            or participant["policy"]
            not in ("legal-argmax-v1", "alphabeta-v1", "random-canonical-v1")
            or (
                participant["backend"] not in ("torch-cpu", "torch-cuda", "ort-cpu")
                if participant["policy"] == "legal-argmax-v1"
                else participant["backend"]
                != ("rust" if participant["policy"] == "alphabeta-v1" else "python-rng")
            )
        ):
            raise ValueError("invalid evaluation participant policy/backend")
    limits, bootstrap, sensitivity = (
        protocol[k] for k in ("search_limits", "bootstrap", "sensitivity")
    )
    if (
        not isinstance(limits, dict)
        or set(limits) != {"max_depth", "max_nodes", "table_capacity"}
        or not _integer(limits["max_depth"], 1, 64)
        or not _integer(limits["max_nodes"], 1, 100_000_000)
        or not _integer(limits["table_capacity"], 0, 1_000_000)
        or not isinstance(bootstrap, dict)
        or set(bootstrap) != {"seed", "resamples"}
        or not _integer(bootstrap["seed"], 0, 2**63 - 1)
        or bootstrap["resamples"] != 10000
        or type(bootstrap["resamples"]) is not int
        or not isinstance(sensitivity, dict)
        or set(sensitivity) != {"minimum_pairs", "minimum_termination_rate"}
        or not _integer(sensitivity["minimum_pairs"], 4, 10000)
        or type(sensitivity["minimum_termination_rate"]) not in (int, float)
        or not 0 < sensitivity["minimum_termination_rate"] <= 1
        or not isinstance(protocol["cases"], list)
        or not 1 <= len(protocol["cases"]) <= 10000
    ):
        raise ValueError("invalid evaluation limits/statistics")
    names, openings = set(), set()
    for case in protocol["cases"]:
        if (
            not isinstance(case, dict)
            or set(case) != {"id", "stratum", "seed", "max_additional_plies", "opening"}
            or not isinstance(case["id"], str)
            or re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", case["id"]) is None
            or case["id"] in names
            or case["stratum"] not in STRATA
            or not _integer(case["seed"], 0, 2**63 - 1)
            or not _integer(case["max_additional_plies"], 1, 20000)
        ):
            raise ValueError("invalid evaluation case")
        _record(case["opening"], unfinished=True)
        identity = fingerprint(case["opening"])
        if identity in openings:
            raise ValueError("duplicate evaluation opening; not an independent pair")
        names.add(case["id"])
        openings.add(identity)
    return fingerprint(protocol)


def check_disjoint_positions(groups):
    """Check full corpus fingerprints, excluding ply but including side/hands.

    Callers must enumerate positions via Rust snapshots. A history digest or only
    the sampled evaluation roots is not a full-corpus leakage audit.
    """
    if not isinstance(groups, dict) or set(groups) != {
        "train",
        "development",
        "holdout",
    }:
        raise ValueError("invalid evaluation split groups")
    for identities in groups.values():
        if (
            not isinstance(identities, (set, frozenset))
            or not identities
            or any(not _hash(x) for x in identities)
        ):
            raise ValueError("invalid evaluation position identities")
    for left, right in combinations(sorted(groups), 2):
        if groups[left] & groups[right]:
            raise ValueError(f"evaluation position leakage: {left}/{right}")
    return {name: len(identities) for name, identities in groups.items()}


def _counts(games):
    n = len(games)
    counts = Counter(row["outcome"] for row in games)
    complete = n - counts["cutoff"]
    points = counts["win"] + 0.5 * counts["draw"]
    plies = [row["additional_plies"] for row in games]
    elapsed = sum(row["elapsed_seconds"] for row in games)
    return {
        "games": n,
        "wins": counts["win"],
        "losses": counts["loss"],
        "draws": counts["draw"],
        "cutoffs": counts["cutoff"],
        "win_rate": counts["win"] / n,
        "termination_rate": complete / n,
        "score_bounds": [points / n, (points + counts["cutoff"]) / n],
        "completed_score_rate": points / complete if complete else None,
        "additional_plies": {
            "min": min(plies),
            "max": max(plies),
            "mean": sum(plies) / n,
        },
        "elapsed_seconds": {"total": elapsed, "mean": elapsed / n},
    }


def summarize_matches(rows, protocol, *, model_sha256, opponent_sha256):
    """Require the exact preregistered cohort; result metadata is not Rust proof."""
    digest = validate_protocol(protocol)
    if (
        model_sha256 != protocol["participants"]["model"]["artifact_sha256"]
        or opponent_sha256 != protocol["participants"]["opponent"]["artifact_sha256"]
    ):
        raise ValueError("invalid evaluation participant hash")
    cases = {case["id"]: case for case in protocol["cases"]}
    expected = {(name, side) for name in cases for side in ("b", "w")}
    games = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "protocol_sha256",
            "case_id",
            "model_side",
            "model_sha256",
            "opponent_sha256",
            "seed",
            "opening_sha256",
            "record",
            "outcome",
            "elapsed_seconds",
        }:
            raise ValueError("invalid evaluation row fields")
        key = (row["case_id"], row["model_side"])
        if key not in expected or key in games:
            raise ValueError("invalid, repeated, or unexpected evaluation game")
        case = cases[row["case_id"]]
        if (
            row["protocol_sha256"] != digest
            or row["model_sha256"] != model_sha256
            or row["opponent_sha256"] != opponent_sha256
            or type(row["seed"]) is not int
            or row["seed"] != case["seed"]
            or row["opening_sha256"] != fingerprint(case["opening"])
            or type(row["elapsed_seconds"]) not in (int, float)
            or not math.isfinite(row["elapsed_seconds"])
            or row["elapsed_seconds"] < 0
        ):
            raise ValueError("evaluation conditions differ")
        record, opening = row["record"], case["opening"]
        _record(record)
        plies = len(record["moves"]) - len(opening["moves"])
        outcome = classify_result(record["result"], row["model_side"])
        if (
            record["initial"] != opening["initial"]
            or record["moves"][: len(opening["moves"])] != opening["moves"]
            or not 0 <= plies <= case["max_additional_plies"]
            or row["outcome"] != outcome
            or (
                outcome == "cutoff"
                and (
                    record["termination"] != "MaxPlies"
                    or plies != case["max_additional_plies"]
                )
            )
            or (outcome != "cutoff" and record["termination"] is not None)
        ):
            raise ValueError("evaluation result/prefix/limit differs")
        games[key] = {**row, "additional_plies": plies, "stratum": case["stratum"]}
    if set(games) != expected:
        raise ValueError("incomplete evaluation cohort")
    ordered = [games[key] for key in sorted(games)]
    pair_wins = [
        sum(games[name, side]["outcome"] == "win" for side in ("b", "w"))
        for name in sorted(cases)
    ]
    rng = random.Random(protocol["bootstrap"]["seed"])
    samples = sorted(
        sum(rng.choice(pair_wins) for _ in pair_wins) / (2 * len(pair_wins))
        for _ in range(protocol["bootstrap"]["resamples"])
    )
    overall = {
        **_counts(ordered),
        "pairs": len(cases),
        "paired_win_rate95": [samples[249], samples[9749]],
    }
    sensitivity = protocol["sensitivity"]
    return {
        "schema": SCHEMA,
        "protocol_sha256": digest,
        "model_sha256": model_sha256,
        "opponent_sha256": opponent_sha256,
        "overall": overall,
        "by_side": {
            side: _counts([r for r in ordered if r["model_side"] == side])
            for side in ("b", "w")
        },
        "by_stratum": {
            name: _counts([r for r in ordered if r["stratum"] == name])
            for name in sorted({r["stratum"] for r in ordered})
        },
        "sensitivity": {
            "sufficient": len(cases) >= sensitivity["minimum_pairs"]
            and overall["termination_rate"] >= sensitivity["minimum_termination_rate"],
            "criteria": dict(sensitivity),
            "meaning": "cohort size/termination screening only; not proof of strength or rating precision",
        },
        "interval_method": "opening-pair bootstrap; 10000 resamples; order statistics 250/9750",
        "interval_limitations": "observed opening pairs only; a degenerate interval is not a population guarantee; repeated or related positions can remain correlated",
        "verification_scope": "metadata only; requires separate Rust replay and full-corpus leakage audit",
    }
