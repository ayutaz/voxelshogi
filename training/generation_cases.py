"""Fixed P5-3 development cohorts; real opening/replay work is Linux only."""

import json
import sys
from copy import deepcopy
from pathlib import Path

from training.evaluation_v2 import validate_protocol
from training.evaluation_v2_runner import position_identity

ROOT = Path(__file__).resolve().parents[1]
SEARCH_LIMITS = {"max_depth": 3, "max_nodes": 20000, "table_capacity": 4096}


def _linux():
    if sys.platform != "linux":
        raise ValueError("generation opening/replay execution requires external Linux")


def _offset_king(record, offset):
    """Edit static diagnostic metadata; legal/oracle validation belongs to Rust."""
    value = deepcopy(record)
    fields = value["initial"].split()
    layers = fields[0].split("|")
    ranks = layers[8].split("/")
    if ranks[8] != "K8":
        raise ValueError("unexpected diagnostic fixture")
    ranks[8] = f"{offset}K{8 - offset}"
    layers[8] = "/".join(ranks)
    fields[0] = "|".join(layers)
    value["initial"] = " ".join(fields)
    return value


def generation_definitions(stage):
    """Static plan, not legal validation or evidence of independent tactics."""
    if stage not in ("timing", "comparison"):
        raise ValueError("unknown development generation stage")
    fixtures = json.loads((ROOT / "export/fixtures/positions.json").read_text())
    result = []

    def add(
        name, stratum, seed, limit, family, *, record=None, plies=None, oracle=None
    ):
        result.append(
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

    if stage == "timing":
        add(
            "timing-material",
            "endgame",
            63090,
            128,
            "material-offset",
            record=_offset_king(fixtures[3]["record"], 6),
        )
        add("timing-long", "middlegame", 63091, 512, "seeded-standard-63091", plies=128)
        return result
    for i, offset in enumerate((2, 3, 4)):
        add(
            f"mate-offset-{offset}",
            "tactical",
            63000 + i,
            1,
            "exposed-rook-gold-mate",
            record=_offset_king(fixtures[2]["record"], offset),
            oracle={
                "move": "232222",
                "result": {"Win": {"winner": "Black", "reason": "Checkmate"}},
            },
        )
    for i, offset in enumerate((2, 3, 4, 5)):
        add(
            f"material-offset-{offset}",
            "endgame",
            63010 + i,
            128,
            "material-offset",
            record=_offset_king(fixtures[3]["record"], offset),
        )
    for i, plies in enumerate((16, 24, 32, 48)):
        add(
            f"opening-{i}",
            "opening",
            63100 + i,
            512,
            f"seeded-standard-{63100 + i}",
            plies=plies,
        )
    for i, plies in enumerate((96, 128, 160, 192)):
        add(
            f"long-{i}",
            "middlegame",
            63200 + i,
            512,
            f"seeded-standard-{63200 + i}",
            plies=plies,
        )
    return result


def prepare_generation_protocol(participants, source_commit, *, stage):
    _linux()
    from voxelshogi import Game

    from training.evaluation import opening_record
    from training.research_data import input_identity

    definitions = generation_definitions(stage)
    cases, roots = [], set()
    for definition in definitions:
        case = deepcopy(definition["case"])
        generated = definition["generated_opening"]
        if generated is not None:
            case["opening"] = opening_record(**generated)
        game = Game.from_record(case["opening"])
        if game.snapshot()["finished"] or game.record() != case["opening"]:
            raise ValueError("generation opening must be unfinished and Rust canonical")
        identity = input_identity(game.snapshot())
        if identity in roots:
            raise ValueError("duplicate canonical generation root input")
        roots.add(identity)
        oracle = definition["oracle"]
        if oracle is not None:
            game.play(oracle["move"])
            if (
                not game.snapshot()["finished"]
                or game.snapshot()["result"] != oracle["result"]
            ):
                raise ValueError("handwritten generation oracle differs from Rust")
        cases.append(case)
    protocol = {
        "schema": "voxelshogi-evaluation-v2",
        "purpose": "development",
        "source_commit": source_commit,
        "ruleset_id": "voxelshogi-standard-v1",
        "participants": deepcopy(participants),
        "search_limits": dict(SEARCH_LIMITS),
        "bootstrap": {"seed": 314159, "resamples": 10000},
        "sensitivity": {
            "minimum_pairs": 15 if stage == "comparison" else 4,
            "minimum_termination_rate": 0.25,
        },
        "cases": cases,
    }
    validate_protocol(protocol)
    return protocol


def replay_scored_identities(record, opening):
    """Enumerate root, every continuation and terminal; exclude book prefix."""
    _linux()
    from voxelshogi import Game

    from training.research_data import input_identity

    Game.from_record(record)
    if (
        record["ruleset_id"] != opening["ruleset_id"]
        or record["initial"] != opening["initial"]
        or record["moves"][: len(opening["moves"])] != opening["moves"]
    ):
        raise ValueError("scored history differs from frozen opening")
    game = Game.from_record(opening)
    identities = {"positions": set(), "inputs": set()}

    def add():
        snapshot = game.snapshot()
        identities["positions"].add(position_identity(snapshot["vsfen"]))
        identities["inputs"].add(input_identity(snapshot))

    add()
    for move in record["moves"][len(opening["moves"]) :]:
        game.play(move)
        add()
    return identities
