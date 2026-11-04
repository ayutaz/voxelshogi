"""Pure paired generation comparisons and complete supplied identity inventories.

No rule, model or corpus execution occurs here. The external Linux producer must
Rust-replay every record and enumerate physical and model-input identities.
"""

import random
import re
from copy import deepcopy

from training.evaluation_v2 import summarize_matches, validate_protocol


def _conditions(protocol):
    value = deepcopy(protocol)
    del value["participants"]["model"]["artifact_sha256"]
    return value


def summarize_generations(cohorts, *, baseline):
    """Compare fixed weights using shared opening pairs and a common opponent."""
    if (
        type(cohorts) is not dict
        or not 2 <= len(cohorts) <= 16
        or baseline not in cohorts
        or any(
            not isinstance(n, str) or not re.fullmatch(r"[a-z0-9-]{1,80}", n)
            for n in cohorts
        )
        or any(
            type(c) is not dict or set(c) != {"protocol", "rows"}
            for c in cohorts.values()
        )
    ):
        raise ValueError("invalid generation comparison cohort")
    summaries, games, hashes = {}, {}, set()
    reference = cohorts[baseline]["protocol"]
    validate_protocol(reference)
    for name in sorted(cohorts):
        protocol, rows = (cohorts[name][k] for k in ("protocol", "rows"))
        validate_protocol(protocol)
        identity = protocol["participants"]["model"]["artifact_sha256"]
        if _conditions(protocol) != _conditions(reference) or identity in hashes:
            raise ValueError("generation conditions/opponent differ or model repeated")
        hashes.add(identity)
        summaries[name] = summarize_matches(
            rows,
            protocol,
            model_sha256=identity,
            opponent_sha256=protocol["participants"]["opponent"]["artifact_sha256"],
        )
        games[name] = {(r["case_id"], r["model_side"]): r["outcome"] for r in rows}
    pairs = sorted(c["id"] for c in reference["cases"])
    differences = {}
    base = summaries[baseline]["overall"]
    for name in sorted(cohorts):
        if name == baseline:
            continue
        deltas = [
            sum(
                int(games[name][case, side] == "win")
                - int(games[baseline][case, side] == "win")
                for side in ("b", "w")
            )
            for case in pairs
        ]
        rng = random.Random(reference["bootstrap"]["seed"])
        samples = sorted(
            sum(rng.choice(deltas) for _ in deltas) / (2 * len(deltas))
            for _ in range(reference["bootstrap"]["resamples"])
        )
        current = summaries[name]["overall"]
        differences[name] = {
            "win_rate_difference": sum(deltas) / (2 * len(deltas)),
            "paired_win_difference95": [samples[249], samples[9749]],
            "score_difference_bounds": [
                current["score_bounds"][0] - base["score_bounds"][1],
                current["score_bounds"][1] - base["score_bounds"][0],
            ],
        }
    return {
        "schema": "voxelshogi-generation-comparison-v1",
        "baseline": baseline,
        "games": sum(s["overall"]["games"] for s in summaries.values()),
        "opening_pairs_per_model": len(pairs),
        "comparisons": summaries,
        "differences_from_baseline": differences,
        "limitations": "development opening-pair bootstrap, not a population guarantee; related families remain correlated; cutoffs have unknown scores; no automatic strength claim",
        "verification_scope": "metadata only; requires Linux Rust replay and complete physical/model-input leakage audit",
    }


def _inventory(value):
    if (
        type(value) is not dict
        or not value
        or any(not isinstance(n, str) or not n for n in value)
        or any(
            not isinstance(ids, (set, frozenset))
            or not ids
            or any(
                not isinstance(i, str) or not re.fullmatch(r"[0-9a-f]{64}", i)
                for i in ids
            )
            for ids in value.values()
        )
    ):
        raise ValueError("nonempty complete generation identity inventories required")


def audit_evaluation_inputs(physical_corpora, input_corpora, cases):
    """Check all supplied continuation/terminal IDs, retaining every source."""
    _inventory(physical_corpora)
    _inventory(input_corpora)
    if (
        type(cases) is not dict
        or not cases
        or any(
            type(c) is not dict or set(c) != {"positions", "inputs"}
            for c in cases.values()
        )
    ):
        raise ValueError("complete scored case identities required")
    physical = {name: c["positions"] for name, c in cases.items()}
    inputs = {name: c["inputs"] for name, c in cases.items()}
    _inventory(physical)
    _inventory(inputs)
    all_positions, all_inputs = (
        set.union(*map(set, physical.values())),
        set.union(*map(set, inputs.values())),
    )
    sources = {"physical": physical_corpora, "model_input": input_corpora}
    evaluated = {"physical": all_positions, "model_input": all_inputs}
    overlaps = {
        kind: {name: len(ids & evaluated[kind]) for name, ids in sorted(groups.items())}
        for kind, groups in sources.items()
    }
    bad_cases = set()
    for groups, per_case in ((physical_corpora, physical), (input_corpora, inputs)):
        corpus = set.union(*map(set, groups.values()))
        bad_cases.update(name for name, ids in per_case.items() if corpus & ids)
    return {
        "passed": not any(n for groups in overlaps.values() for n in groups.values()),
        "evaluation_counts": {
            "positions": len(all_positions),
            "inputs": len(all_inputs),
        },
        "corpus_counts": {
            kind: {name: len(ids) for name, ids in sorted(groups.items())}
            for kind, groups in sources.items()
        },
        "overlaps_by_source": overlaps,
        "cases_with_overlap": sorted(bad_cases),
        "scope": "all supplied scored continuation and terminal positions and side-canonical inputs; shared book prefix excluded; producer enumeration must be independently verified",
    }
