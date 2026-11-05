"""P6 development screen and separate final openings; execution is Linux only.

Definitions and method statistics are pure metadata. They are not evidence of
legality, full-corpus exclusion, model execution, or an independent population.
"""

import json
import random
import re
import sys
from collections import defaultdict
from copy import deepcopy

from training.evaluation_v2 import fingerprint, summarize_matches, validate_protocol
from training.generation_cases import ROOT, SEARCH_LIMITS, _offset_king

METHODS = ("legal-argmax-v1", "puct32-v1")


def screen_definitions(purpose):
    """Freeze inputs before outcomes. Related static variants retain one family."""
    if purpose not in ("development", "holdout"):
        raise ValueError("unknown research screen purpose")
    definitions = []

    def add(
        name, stratum, seed, limit, family, *, record=None, plies=None, oracle=None
    ):
        definitions.append(
            {
                "case": {
                    "id": name,
                    "stratum": stratum,
                    "seed": seed,
                    "max_additional_plies": limit,
                    "opening": record,
                },
                "family": family,
                "generated_opening": {"seed": seed, "plies": plies}
                if plies is not None
                else None,
                "oracle": oracle,
            }
        )

    if purpose == "holdout":
        for i, plies in enumerate((48, 64, 96, 128) * 3):
            add(
                f"final-seed-{65000 + i}",
                "middlegame",
                65000 + i,
                128,
                f"seeded-standard-{65000 + i}",
                plies=plies,
            )
        return definitions

    from training.evaluation_cases import handmade_cases

    fixtures = json.loads((ROOT / "export/fixtures/positions.json").read_text())
    for i, offset in enumerate((6, 7)):
        record = _offset_king(fixtures[2]["record"], offset)
        # Extra attacking hand pawns distinguish these inputs from old fixtures.
        # No legality claim is made until Rust checks the handwritten mate below.
        record["initial"] = record["initial"].replace(" b - 1", " b P 1")
        add(
            f"dev-mate-black-{offset}",
            "tactical",
            64000 + i,
            1,
            "exposed-rook-gold-mate",
            record=record,
            oracle={
                "move": "232222",
                "result": {"Win": {"winner": "Black", "reason": "Checkmate"}},
            },
        )
    white = handmade_cases()[1]["case"]["opening"]
    for i, offset in enumerate((2, 3)):
        record = deepcopy(white)
        record["initial"] = record["initial"].replace(
            "8k/", f"{offset}k{8 - offset}/", 1
        )
        # Two white hand pawns also avoid side-canonical identity with black cases.
        record["initial"] = record["initial"].replace(" w - 1", " w 2p 1")
        add(
            f"dev-mate-white-{offset}",
            "tactical",
            64002 + i,
            1,
            "exposed-rook-gold-mate",
            record=record,
            oracle={
                "move": "878888",
                "result": {"Win": {"winner": "White", "reason": "Checkmate"}},
            },
        )
    for i, (offset, side) in enumerate(((6, "b"), (7, "b"), (6, "w"), (7, "w"))):
        record = _offset_king(fixtures[3]["record"], offset)
        record["initial"] = record["initial"].replace(" b 2Ps 1", f" {side} 3Ps 1")
        add(
            f"dev-material-{offset}-{side}",
            "endgame",
            64010 + i,
            64,
            "material-offset",
            record=record,
        )
    for i, plies in enumerate((48, 64, 96, 128)):
        add(
            f"dev-seed-{64020 + i}",
            "middlegame",
            64020 + i,
            128,
            f"seeded-standard-{64020 + i}",
            plies=plies,
        )
    return definitions


def prepare_screen(participants, source_commit):
    """Rust-validate all 24 roots/oracles without consulting a neural model.

    A separate external full-corpus/query audit is still mandatory. Holdout roots
    are returned for protection before training; they are not evaluated here.
    """
    if sys.platform != "linux":
        raise ValueError("research screen preparation requires external Linux")
    from voxelshogi import Game

    from training.evaluation import opening_record
    from training.evaluation_v2_runner import position_identity
    from training.research_data import input_identity

    if (
        not isinstance(participants, dict)
        or set(participants) != {"model", "opponent"}
        or participants["model"].get("policy") != METHODS[0]
        or participants["opponent"].get("policy") != "alphabeta-v1"
    ):
        raise ValueError("screen requires fixed argmax model and alpha-beta opponent")
    protocols, families, roots, seen = {}, {}, {}, set()
    for purpose in ("development", "holdout"):
        cases = []
        for definition in screen_definitions(purpose):
            case = deepcopy(definition["case"])
            if definition["generated_opening"] is not None:
                case["opening"] = opening_record(**definition["generated_opening"])
            game = Game.from_record(case["opening"])
            snapshot = game.snapshot()
            if snapshot["finished"] or game.record() != case["opening"]:
                raise ValueError("screen opening must be unfinished and Rust canonical")
            identity = input_identity(snapshot)
            if identity in seen:
                raise ValueError("duplicate screen/holdout canonical root input")
            seen.add(identity)
            roots[case["id"]] = {
                "purpose": purpose,
                "position": position_identity(snapshot["vsfen"]),
                "input": identity,
            }
            oracle = definition["oracle"]
            if oracle is not None:
                game.play(oracle["move"])
                if (
                    not game.snapshot()["finished"]
                    or game.snapshot()["result"] != oracle["result"]
                ):
                    raise ValueError("handwritten screen oracle differs from Rust")
            cases.append(case)
            if purpose == "development":
                families[case["id"]] = definition["family"]
        protocols[purpose] = {
            "schema": "voxelshogi-evaluation-v2",
            "purpose": purpose,
            "source_commit": source_commit,
            "ruleset_id": "voxelshogi-standard-v1",
            "participants": deepcopy(participants),
            "search_limits": dict(SEARCH_LIMITS),
            "bootstrap": {"seed": 314159, "resamples": 10000},
            "sensitivity": {"minimum_pairs": 12, "minimum_termination_rate": 0.25},
            "cases": cases,
        }
        validate_protocol(protocols[purpose])
    arms = {name: deepcopy(protocols["development"]) for name in METHODS}
    for name, protocol in arms.items():
        protocol["participants"]["model"]["policy"] = name
        validate_protocol(protocol)
    result = {
        "schema": "voxelshogi-research-screen-v1",
        "protocols": arms,
        "holdout_protocol": protocols["holdout"],
        "families": families,
        "roots": roots,
        "protected_holdout_inputs": sorted(
            r["input"] for r in roots.values() if r["purpose"] == "holdout"
        ),
        "definitions_sha256": fingerprint(
            {p: screen_definitions(p) for p in protocols}
        ),
    }
    return {**result, "conditions_sha256": fingerprint(result)}


def _policy_free(protocol):
    value = deepcopy(protocol)
    del value["participants"]["model"]["policy"]
    return value


def summarize_screen(cohorts, *, families):
    """Compare only the two fixed policies, retaining same weights and censoring.

    Primary descriptive interval: average each family's paired win differences,
    then resample whole families with equal family weight. Opening-pair summaries
    are also retained, with their own existing limitations. Neither is a rating.
    """
    if type(cohorts) is not dict or set(cohorts) != set(METHODS):
        raise ValueError("both exact screen methods required")
    summaries, games = {}, {}
    reference = None
    for name in METHODS:
        cohort = cohorts[name]
        if type(cohort) is not dict or set(cohort) != {"protocol", "rows"}:
            raise ValueError("invalid screen cohort")
        protocol = cohort["protocol"]
        validate_protocol(protocol)
        if (
            protocol["purpose"] != "development"
            or len(protocol["cases"]) != 12
            or protocol["participants"]["model"]["policy"] != name
            or protocol["participants"]["opponent"]["policy"] != "alphabeta-v1"
            or (
                reference is not None
                and _policy_free(protocol) != _policy_free(reference)
            )
        ):
            raise ValueError("screen conditions differ beyond model policy")
        reference = protocol
        summaries[name] = summarize_matches(
            cohort["rows"],
            protocol,
            model_sha256=protocol["participants"]["model"]["artifact_sha256"],
            opponent_sha256=protocol["participants"]["opponent"]["artifact_sha256"],
        )
        games[name] = {
            (r["case_id"], r["model_side"]): r["outcome"] for r in cohort["rows"]
        }
    cases = sorted(c["id"] for c in reference["cases"])
    if (
        type(families) is not dict
        or set(families) != set(cases)
        or any(
            not isinstance(f, str) or not re.fullmatch(r"[a-z0-9-]{1,80}", f)
            for f in families.values()
        )
    ):
        raise ValueError("exact nonempty case family assignments required")
    grouped = defaultdict(list)
    for case in cases:
        grouped[families[case]].append(case)
    if len(grouped) < 2:
        raise ValueError("at least two families required")
    deltas, lower, upper = [], [], []
    for family in sorted(grouped):
        members = [(c, s) for c in grouped[family] for s in ("b", "w")]
        delta = lo = hi = 0
        for key in members:
            baseline, candidate = (games[name][key] for name in METHODS)
            delta += int(candidate == "win") - int(baseline == "win")
            points = {"win": 1, "draw": 0.5, "loss": 0, "cutoff": 0}
            lo += points[candidate] - points[baseline] - int(baseline == "cutoff")
            hi += points[candidate] + int(candidate == "cutoff") - points[baseline]
        deltas.append(delta / len(members))
        lower.append(lo / len(members))
        upper.append(hi / len(members))
    rng = random.Random(reference["bootstrap"]["seed"])
    samples = sorted(
        sum(rng.choice(deltas) for _ in deltas) / len(deltas)
        for _ in range(reference["bootstrap"]["resamples"])
    )
    baseline, candidate = (summaries[name]["overall"] for name in METHODS)
    return {
        "schema": "voxelshogi-research-screen-comparison-v1",
        "games": sum(s["overall"]["games"] for s in summaries.values()),
        "opening_pairs_per_method": len(cases),
        "families": len(grouped),
        "family_cases": {f: grouped[f] for f in sorted(grouped)},
        "comparisons": summaries,
        "puct_minus_argmax": {
            "case_weighted_win_difference": candidate["win_rate"]
            - baseline["win_rate"],
            "case_weighted_score_difference_bounds": [
                candidate["score_bounds"][0] - baseline["score_bounds"][1],
                candidate["score_bounds"][1] - baseline["score_bounds"][0],
            ],
            "family_balanced_win_difference": sum(deltas) / len(deltas),
            "family_balanced_win_difference95": [samples[249], samples[9749]],
            "family_balanced_score_difference_bounds": [
                sum(lower) / len(lower),
                sum(upper) / len(upper),
            ],
        },
        "interval_method": "equal-family paired win differences; whole-family bootstrap; 10000 resamples; order statistics 250/9750",
        "limitations": "development screen, not a population guarantee; exposed static families and seeded starts are not representative strength tests; cutoffs have unknown scores; PUCT uses more inference than argmax; no automatic adoption or strength claim",
        "verification_scope": "metadata only; requires Linux Rust replay, actual neural-query inventories, full-corpus/holdout leakage audit, timings and inference counts",
    }
