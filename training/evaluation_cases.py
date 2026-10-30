"""Development diagnostics, frozen openings, and full-continuation leakage audit.

Only static fixture metadata and set membership are evaluated on Mac. All rule,
opening generation, Parquet, and match replay execution requires external Linux.
"""

import argparse
import json
import re
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

from training.checkpoint import atomic_json
from training.evaluation_v2 import fingerprint, validate_protocol
from training.evaluation_v2_runner import position_identity, verify_run

ROOT = Path(__file__).resolve().parents[1]


def _linux():
    if sys.platform != "linux":
        raise ValueError("evaluation case generation/audit requires external Linux")


def handmade_cases():
    """Exposed development diagnostics, not unseen strength-test positions."""
    fixtures = json.loads((ROOT / "export/fixtures/positions.json").read_text())
    black = deepcopy(fixtures[2]["record"])
    empty = "9/9/9/9/9/9/9/9/9"
    layers = [empty] * 9
    layers[0] = "8k/9/9/9/9/9/9/9/9"
    layers[6] = "9/9/9/9/9/9/2g6/9/9"
    layers[7] = "9/9/9/9/9/9/1+r7/9/9"
    layers[8] = "9/9/9/9/9/9/9/9/K8"
    white = {
        "ruleset_id": black["ruleset_id"],
        "initial": "|".join(layers) + " w - 1",
        "moves": [],
        "result": None,
        "termination": None,
    }
    black_offset = deepcopy(black)
    black_offset["initial"] = black_offset["initial"].replace("K8 b - 1", "1K7 b - 1")
    white_offset = deepcopy(white)
    white_offset["initial"] = white_offset["initial"].replace("8k/", "7k1/", 1)
    definitions = []
    for index, (name, record, move, winner) in enumerate(
        (
            ("mate-black", black, "232222", "Black"),
            ("mate-white", white, "878888", "White"),
            ("mate-black-offset", black_offset, "232222", "Black"),
            ("mate-white-offset", white_offset, "878888", "White"),
        )
    ):
        definitions.append(
            {
                "case": {
                    "id": name,
                    "stratum": "tactical",
                    "seed": 9100 + index,
                    "max_additional_plies": 1,
                    "opening": record,
                },
                "oracle": {
                    "move": move,
                    "result": {"Win": {"winner": winner, "reason": "Checkmate"}},
                },
            }
        )
    layers = [empty] * 9
    layers[0] = "8k/9/9/9/9/9/9/9/9"
    layers[8] = "9/9/9/9/9/9/9/9/K8"
    cycle = ["999899", "111211", "899999", "211111"]
    repetition = {
        "ruleset_id": black["ruleset_id"],
        "initial": "|".join(layers) + " b - 1",
        "moves": cycle * 2 + cycle[:3],
        "result": None,
        "termination": None,
    }
    definitions.append(
        {
            "case": {
                "id": "repetition-near-end",
                "stratum": "endgame",
                "seed": 9104,
                "max_additional_plies": 16,
                "opening": repetition,
            },
            "oracle": {"move": "211111", "result": {"Draw": {"reason": "Repetition"}}},
        }
    )
    definitions.append(
        {
            "case": {
                "id": "material-ending",
                "stratum": "endgame",
                "seed": 9105,
                "max_additional_plies": 128,
                "opening": deepcopy(fixtures[3]["record"]),
            },
            "oracle": None,
        }
    )
    return definitions


def audit_membership(corpus, cases):
    """Pure set audit. Inputs must be complete, trusted position inventories."""
    if (
        not isinstance(corpus, dict)
        or set(corpus) != {"train", "val", "test"}
        or not isinstance(cases, dict)
        or not cases
    ):
        raise ValueError("missing corpus/evaluation inventories")
    for group in (*corpus.values(), *cases.values()):
        if (
            not isinstance(group, (set, frozenset))
            or not group
            or any(
                not isinstance(item, str) or re.fullmatch(r"[0-9a-f]{64}", item) is None
                for item in group
            )
        ):
            raise ValueError("invalid or empty evaluation position inventory")
    evaluated = set().union(*cases.values())
    published = set().union(*corpus.values())
    overlaps = {name: len(evaluated & group) for name, group in corpus.items()}
    return {
        "passed": not any(overlaps.values()),
        "evaluation_positions": len(evaluated),
        "corpus_positions": len(published),
        "overlaps_by_split": overlaps,
        "cases_with_overlap": sorted(
            name for name, group in cases.items() if group & published
        ),
        "scope": "all supplied scored continuation and terminal positions; shared book prefix excluded",
    }


def prepare_development(participants, source_commit):
    _linux()
    from training.evaluation import opening_record

    protocol = {
        "schema": "voxelshogi-evaluation-v2",
        "purpose": "development",
        "source_commit": source_commit,
        "ruleset_id": "voxelshogi-standard-v1",
        "participants": deepcopy(participants),
        "search_limits": {"max_depth": 3, "max_nodes": 20000, "table_capacity": 4096},
        "bootstrap": {"seed": 314159, "resamples": 10000},
        "sensitivity": {"minimum_pairs": 8, "minimum_termination_rate": 0.25},
        "cases": [item["case"] for item in handmade_cases()],
    }
    validate_protocol(protocol)
    for name, seed, length, stratum in (
        ("standard-opening", 9200, 16, "opening"),
        ("standard-middle", 9201, 96, "middlegame"),
    ):
        record = opening_record(seed, plies=length)
        protocol["cases"].append(
            {
                "id": name,
                "stratum": stratum,
                "seed": seed,
                "max_additional_plies": 512,
                "opening": record,
            }
        )
    validate_protocol(protocol)
    return protocol


def replay_scored_positions(record, opening):
    _linux()
    from voxelshogi import Game

    Game.from_record(record)  # Validate the whole history and declared result first.
    if (
        record["ruleset_id"] != opening["ruleset_id"]
        or record["initial"] != opening["initial"]
        or record["moves"][: len(opening["moves"])] != opening["moves"]
    ):
        raise ValueError("evaluation continuation differs from opening")
    game = Game.from_record(opening)
    identities = {position_identity(game.snapshot()["vsfen"])}
    for move in record["moves"][len(opening["moves"]) :]:
        game.play(move)
        identities.add(position_identity(game.snapshot()["vsfen"]))
    return identities


def collect_corpus_identities(rows, *, expected_rows):
    """Stream trusted metadata; keep duplicate positions and all split memberships."""
    groups = {name: set() for name in ("train", "val", "test")}
    count = 0
    for row in rows:
        if (
            not isinstance(row, dict)
            or set(row) != {"vsfen", "split", "ruleset_id"}
            or row["split"] not in groups
        ):
            raise ValueError("invalid corpus membership row")
        groups[row["split"]].add(
            position_identity(row["vsfen"], ruleset=row["ruleset_id"])
        )
        count += 1
    if (
        type(expected_rows) is not int
        or count != expected_rows
        or any(not group for group in groups.values())
    ):
        raise ValueError("corpus membership enumeration is incomplete")
    return groups


def corpus_position_sets(folder):
    _linux()
    import pyarrow.parquet as pq

    from training.supervision import audit_corpus

    audit = audit_corpus(
        folder
    )  # Fixed HF revision, complete inventory, hashes and schema.
    manifest = json.loads((Path(folder) / "manifest.json").read_text())

    def rows():
        for shard in manifest["shards"]:
            yield from pq.read_table(
                Path(folder) / shard["file"], columns=["vsfen", "split", "ruleset_id"]
            ).to_pylist()

    groups = collect_corpus_identities(rows(), expected_rows=audit["counts"]["rows"])
    return groups, audit


def audit_matches(folder, corpus_folder):
    _linux()
    summary = verify_run(folder)
    protocol = json.loads((Path(folder) / "protocol.json").read_text())
    corpus, audit = corpus_position_sets(corpus_folder)
    positions = {}
    for case in protocol["cases"]:
        for side in ("b", "w"):
            name = f"{case['id']}-{side}"
            row = json.loads((Path(folder) / (name + ".json")).read_text())
            positions[name] = replay_scored_positions(row["record"], case["opening"])
    return {
        **audit_membership(corpus, positions),
        "protocol_sha256": summary["protocol_sha256"],
        "corpus_contract": audit["contract"],
        "corpus_rows": audit["counts"]["rows"],
        "corpus_inventory_sha256": fingerprint(audit["files"]),
        "scope_note": "All published M6 corpus rows, including duplicates and all splits, are excluded; this is not an audit of later new datasets.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("participants", type=Path)
    prepare.add_argument("output", type=Path)
    audit = sub.add_parser("audit")
    audit.add_argument("matches", type=Path)
    audit.add_argument("corpus", type=Path)
    audit.add_argument("output", type=Path)
    args = parser.parse_args()
    _linux()
    if args.output.exists():
        raise ValueError("evaluation protocol/audit output already exists")
    if args.command == "prepare":
        source = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        if subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True
        ):
            raise ValueError("development protocol requires clean source")
        result = prepare_development(json.loads(args.participants.read_text()), source)
    else:
        result = audit_matches(args.matches, args.corpus)
    atomic_json(args.output, result)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "sha256": fingerprint(result),
                "passed": result.get("passed"),
            },
            allow_nan=False,
        )
    )
    if args.command == "audit" and result["passed"] is not True:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
