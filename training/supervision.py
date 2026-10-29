"""Pinned M6 teacher contract and streaming metadata audit; no rules or learning.

M4 established rule legality by Rust replay. Verify its immutable file hashes
before trusting that evidence; this layer checks the interpretation of labels.
"""

import argparse
import hashlib
import json
import math
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

REPO = "voxelshogi/voxelshogi-synthetic-v1"
REVISION = "6e7fb29d2469b56a895042fbb089d86e7b4d074f"
CONFIG = "production-64"
RULESET = "voxelshogi-standard-v1"
ACTIONS = 1_067_985
VALUE_SCALE = 1000
MATE_SCORE = 1_000_000
ROOT = Path(__file__).resolve().parents[1]


def label_contract():
    return {
        "schema": "voxelshogi-supervision-v1",
        "repo_id": REPO,
        "revision": REVISION,
        "config": CONFIG,
        "ruleset_id": RULESET,
        "features": "voxelshogi-standard-features-v1",
        "policy_actions": ACTIONS,
        "policy_teacher": "teacher.best_move; legal; depth >= 1; nonduplicate",
        "value_teacher": "tanh(teacher.score / value_scale); already side-to-move",
        "value_scale": VALUE_SCALE,
        "mate_score": MATE_SCORE,
        "loss_policy": "mean cross entropy over engine-supplied legal actions",
        "loss_value": "mean squared error",
        "loss_value_weight": 1,
        "training_seed": 314159,
        "selection_split": "val",
        "test_role": "final selected checkpoint and predeclared conversion comparison only",
        "evaluation": evaluation_protocol(),
    }


def evaluation_protocol():
    return {
        "schema": "voxelshogi-evaluation-v1",
        "max_plies": 256,
        "opening_plies": 8,
        "opening_seeds": {
            "random": list(range(7000, 7020)),
            "search": list(range(8000, 8010)),
        },
        "swap_model_colors": True,
        "search_limits": {"max_depth": 2, "max_nodes": 10000, "table_capacity": 4096},
        "policy": "argmax engine-legal logits; ties smallest canonical action ID",
        "opponent_seed": "100000 + opening seed",
        "primary_win_rate": "wins / games_started",
        "cutoff_is_draw": False,
        "interval": "95% paired bootstrap over opening seeds; 10000 resamples; seed 314159",
    }


def _integer(value, lower, upper):
    return type(value) is int and lower <= value <= upper


def move_action(text, side):
    if side not in ("b", "w") or not isinstance(text, str):
        raise ValueError("invalid move side or notation")

    def square(digits):
        x, y, z = (int(c) - 1 for c in digits)
        index = z * 81 + y * 9 + x
        return index if side == "b" else 728 - index

    if re.fullmatch(r"[PLNSGBR]\*[1-9]{3}", text):
        return 1062882 + "PLNSGBR".index(text[0]) * 729 + square(text[2:])
    if re.fullmatch(r"[1-9]{6}\+?", text):
        return 2 * (square(text[:3]) * 729 + square(text[3:6])) + text.endswith("+")
    raise ValueError("invalid move notation")


def score_value(score):
    if not _integer(score, -MATE_SCORE, MATE_SCORE):
        raise ValueError("search score must be an integer in mate bounds")
    return math.tanh(score / VALUE_SCALE)


@dataclass(frozen=True)
class TrainingTarget:
    example_id: str
    game_id: str
    ply: int
    split: str
    action: int
    value: float
    completed_depth: int
    legal_actions: tuple[int, ...]


def _invalid_constant(value):
    raise ValueError("nonfinite JSON constant: " + value)


def _metadata(row):
    required = {
        "game_id",
        "ply",
        "source",
        "split",
        "ruleset_id",
        "history",
        "vsfen",
        "side",
        "legal_moves",
        "legal_actions",
        "played_move",
        "teacher",
        "teacher_valid",
        "finished",
        "result",
        "termination",
        "duplicate_of",
    }
    if not isinstance(row, dict) or not required <= row.keys():
        raise ValueError("missing supervision metadata")
    if not isinstance(row["game_id"], str) or not re.fullmatch(
        r"g[0-9]{6}", row["game_id"]
    ):
        raise ValueError("invalid game ID")
    if not _integer(row["ply"], 0, 64) or row["ruleset_id"] != RULESET:
        raise ValueError("invalid ply or ruleset")
    bucket = (
        int(hashlib.sha256(f"split:17:{row['game_id']}".encode()).hexdigest()[:8], 16)
        % 10
    )
    split = "train" if bucket < 8 else "val" if bucket == 8 else "test"
    if row["split"] != split or row["source"] not in ("random", "rules", "search"):
        raise ValueError("invalid split or source")
    if row["side"] not in ("b", "w") or not isinstance(row["vsfen"], str):
        raise ValueError("invalid side or position key")
    parts = row["vsfen"].split()
    if (
        len(parts) != 4
        or parts[1] != row["side"]
        or not parts[3].isdigit()
        or int(parts[3]) < 1
    ):
        raise ValueError("position metadata differs from side")
    if (
        not isinstance(row["history"], list)
        or len(row["history"]) != row["ply"]
        or any(not isinstance(move, str) for move in row["history"])
    ):
        raise ValueError("history length differs from ply")
    if type(row["teacher_valid"]) is not bool or type(row["finished"]) is not bool:
        raise ValueError("flags must be booleans")
    duplicate = row["duplicate_of"]
    if duplicate is not None and (
        not isinstance(duplicate, str)
        or not re.fullmatch(r"g[0-9]{6}:[0-9]+", duplicate)
    ):
        raise ValueError("invalid duplicate reference")
    moves, actions = row["legal_moves"], row["legal_actions"]
    if (
        not isinstance(moves, list)
        or not isinstance(actions, list)
        or any(not isinstance(move, str) for move in moves)
        or any(not _integer(a, 0, ACTIONS - 1) for a in actions)
    ):
        raise ValueError("invalid legal action metadata")
    if (
        len(set(moves)) != len(moves)
        or actions != sorted(set(actions))
        or set(actions) != {move_action(move, row["side"]) for move in moves}
    ):
        raise ValueError("legal moves and canonical IDs differ")
    final = row["termination"]
    if final not in (None, "natural", "max_plies") or row["finished"] != (
        final == "natural"
    ):
        raise ValueError("termination metadata differs")
    if (row["result"] is not None) != row["finished"]:
        raise ValueError("result metadata differs")
    if final == "max_plies" and row["ply"] != 64:
        raise ValueError("truncation differs from production horizon")
    if final is not None:
        if (
            row["played_move"] is not None
            or row["teacher"] is not None
            or row["teacher_valid"]
        ):
            raise ValueError("final rows cannot have a teacher or played move")
    elif not moves or row["played_move"] not in moves:
        raise ValueError("nonfinal row needs a legal played move")


def select_target(row):
    _metadata(row)
    raw = row["teacher"]
    teacher = None
    if raw is not None:
        if row["source"] != "search" or not isinstance(raw, str):
            raise ValueError("only search rows may have search teachers")
        teacher = json.loads(raw, parse_constant=_invalid_constant)
        if not isinstance(teacher, dict) or not _integer(
            teacher.get("completed_depth"), 0, 2
        ):
            raise ValueError("invalid completed depth")
        if not _integer(teacher.get("nodes"), 0, 10000) or teacher.get(
            "stop_reason"
        ) not in ("depth", "nodes"):
            raise ValueError("teacher search budget differs")
        if teacher.get("best_move") not in row["legal_moves"]:
            raise ValueError("teacher move is not legal")
        if teacher["completed_depth"] >= 1:
            score_value(teacher.get("score"))
        elif teacher.get("score") is not None:
            raise ValueError("unfinished teacher cannot have a valid score")
    valid = teacher is not None and teacher["completed_depth"] >= 1
    if row["teacher_valid"] != valid:
        raise ValueError("teacher eligibility flag differs")
    if row["duplicate_of"] is not None or row["termination"] is not None or not valid:
        return None
    return TrainingTarget(
        example_id=f"{row['game_id']}:{row['ply']}",
        game_id=row["game_id"],
        ply=row["ply"],
        split=row["split"],
        action=move_action(teacher["best_move"], row["side"]),
        value=score_value(teacher["score"]),
        completed_depth=teacher["completed_depth"],
        legal_actions=tuple(row["legal_actions"]),
    )


def audit_rows(rows, *, expected=None, require_all_splits=True):
    seen, ids, games = {}, set(), set()
    counts = Counter()
    sources, eligible_sources, splits, teacher_splits, depths, exclusions = (
        Counter() for _ in range(6)
    )
    for row in rows:
        target = select_target(row)
        example_id = f"{row['game_id']}:{row['ply']}"
        if example_id in ids:
            raise ValueError("repeated example ID")
        ids.add(example_id)
        games.add(row["game_id"])
        position = " ".join(row["vsfen"].split()[:3])
        if row["duplicate_of"] != seen.get(position):
            raise ValueError("duplicate marker differs; possible cross-split leakage")
        seen.setdefault(position, example_id)
        counts["rows"] += 1
        sources[row["source"]] += 1
        counts["valid_teachers"] += row["teacher_valid"]
        if row["duplicate_of"] is not None:
            counts["duplicates"] += 1
            exclusions["duplicate"] += 1
        else:
            counts["eligible_rows"] += 1
            splits[row["split"]] += 1
            eligible_sources[row["source"]] += 1
            if target is None:
                exclusions[
                    "final" if row["termination"] else "unlabelled_or_unfinished"
                ] += 1
        if target is not None:
            counts["eligible_teachers"] += 1
            teacher_splits[target.split] += 1
            depths[str(target.completed_depth)] += 1
    if not counts["rows"] or not counts["eligible_teachers"]:
        raise ValueError("empty supervision corpus")
    if require_all_splits and any(
        not teacher_splits[s] for s in ("train", "val", "test")
    ):
        raise ValueError("every split requires nonduplicate search teachers")
    report = {
        **{
            k: counts[k]
            for k in (
                "rows",
                "duplicates",
                "eligible_rows",
                "valid_teachers",
                "eligible_teachers",
            )
        },
        "games": len(games),
        "sources": dict(sources),
        "eligible_splits": dict(splits),
        "eligible_sources": dict(eligible_sources),
        "teacher_splits": {s: teacher_splits[s] for s in ("train", "val", "test")},
        "teacher_depths": dict(depths),
        "exclusions": dict(exclusions),
    }
    if expected and any(report.get(k) != value for k, value in expected.items()):
        raise ValueError("corpus differs from pinned M4 validation counts")
    return report


def verify_files(folder, inventory):
    folder = Path(folder)
    if folder.is_symlink() or not inventory:
        raise ValueError("file inventory must be nonempty and use a real directory")
    names = set()
    for entry in inventory:
        name = entry["file"]
        if (
            not isinstance(name, str)
            or not re.fullmatch(
                r"game-[0-9]{6}\.parquet|(?:manifest|generation|validation)\.json", name
            )
            or name in names
        ):
            raise ValueError("invalid or repeated corpus path")
        names.add(name)
        path = folder / name
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size != entry["bytes"]
        ):
            raise ValueError("corpus file type or size differs")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != entry["sha256"]:
            raise ValueError("corpus file hash differs")


def validate_manifest(manifest, config, inventory, *, expected_rows):
    if (
        manifest.get("complete") is not True
        or manifest.get("schema") != "voxelshogi-dataset-v1"
        or manifest.get("ruleset_id") != RULESET
        or manifest.get("config") != config
    ):
        raise ValueError("generation settings differ from the pinned production job")
    shards = manifest["shards"]
    if (
        len(shards) != config["games"]
        or any(
            shard["file"] != f"game-{index:06d}.parquet"
            or not _integer(shard["rows"], 1, config["max_plies"] + 1)
            for index, shard in enumerate(shards)
        )
        or sum(shard["rows"] for shard in shards) != expected_rows
    ):
        raise ValueError("manifest shard order/count differs")
    files = {entry["file"]: entry for entry in inventory}
    if (
        len(files) != len(inventory)
        or set(files)
        != {
            "manifest.json",
            "generation.json",
            "validation.json",
            *(shard["file"] for shard in shards),
        }
        or any(files[shard["file"]]["sha256"] != shard["sha256"] for shard in shards)
    ):
        raise ValueError("manifest differs from verified inventory")


def audit_corpus(folder):
    if sys.platform != "linux":
        raise ValueError("audit real data only on external Linux")
    import pyarrow.parquet as pq

    from training.data import SCHEMA

    proof = json.loads(
        (ROOT / "docs/experiments/m4-production-release-2026-10-29.json").read_text()
    )
    publication = proof["publication"]
    if (
        not publication["complete"]
        or not publication["receipt"]["verified"]
        or publication["receipt"]["hub_commit"] != REVISION
    ):
        raise ValueError("unverified or wrong M4 release")
    plan, receipt = publication["plan"], publication["receipt"]
    plan_hash = hashlib.sha256(
        json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if (
        plan["repo_id"] != REPO
        or plan["repo_type"] != "dataset"
        or plan["private"] is not False
        or plan["gated"] != "manual"
        or receipt["release_sha256"] != plan_hash
    ):
        raise ValueError("release plan destination or receipt hash differs")
    inventory = [
        {
            "file": f["path"].removeprefix(CONFIG + "/"),
            "bytes": f["bytes"],
            "sha256": f["sha256"],
        }
        for f in publication["plan"]["files"]
        if f["path"].startswith(CONFIG + "/")
    ]
    verify_files(folder, inventory)
    manifest = json.loads((Path(folder) / "manifest.json").read_text())
    validate_manifest(
        manifest,
        proof["production_job"]["config"],
        inventory,
        expected_rows=proof["production_report"]["validation"]["rows"],
    )

    def rows():
        for shard in manifest["shards"]:
            path = Path(folder) / shard["file"]
            table = pq.read_table(path)
            if (
                not table.schema.equals(SCHEMA, check_metadata=True)
                or len(table) != shard["rows"]
            ):
                raise ValueError("Parquet schema or row count differs")
            yield from table.to_pylist()

    return {
        "contract": label_contract(),
        "counts": audit_rows(rows(), expected=proof["production_report"]["validation"]),
        "files": inventory,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "folder", type=Path, help="Verified production-64 folder on Linux"
    )
    parser.add_argument("output", type=Path, help="Small audit JSON under runs/")
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT / "runs"):
        parser.error("audit output must remain under ignored runs/")
    report = audit_corpus(args.folder)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n"
    )
    temporary.replace(args.output)
    print(json.dumps(report["counts"], sort_keys=True))


if __name__ == "__main__":
    main()
