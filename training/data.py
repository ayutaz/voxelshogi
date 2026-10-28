"""Deterministic per-game Parquet shards and a replay-based validator.

Use the resource-bounded CLI for actual generation; these functions also serve
small tests. A manifest is the commit point; unlisted files are never samples.
"""

import hashlib
import json
import os
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from voxelshogi import RULESET_ID, Game

SCHEMA_ID = "voxelshogi-dataset-v1"
OWNER_FILE = ".voxelshogi-dataset-v1"
SCHEMA = pa.schema(
    [
        ("game_id", pa.string()),
        ("ply", pa.int32()),
        ("source", pa.string()),
        ("split", pa.string()),
        ("ruleset_id", pa.string()),
        ("initial", pa.string()),
        ("history", pa.list_(pa.field("element", pa.string()))),
        ("vsfen", pa.string()),
        ("hash", pa.string()),
        ("side", pa.string()),
        ("in_check", pa.bool_()),
        ("finished", pa.bool_()),
        ("result", pa.string()),
        ("evaluation", pa.int32()),
        ("legal_moves", pa.list_(pa.field("element", pa.string()))),
        ("legal_actions", pa.list_(pa.field("element", pa.int32()))),
        ("played_move", pa.string()),
        ("teacher", pa.string()),
        ("teacher_valid", pa.bool_()),
        ("termination", pa.string()),
        ("duplicate_of", pa.string()),
    ],
    metadata={b"schema_id": SCHEMA_ID.encode()},
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass(frozen=True)
class GenerationConfig:
    engine_commit: str
    seed: int = 17
    games: int = 3
    max_plies: int = 2
    sources: tuple[str, ...] = ("random", "rules", "search")
    initial: str | None = None
    max_depth: int = 1
    max_nodes: int = 1000
    table_capacity: int = 4096

    def __post_init__(self):
        if not isinstance(self.engine_commit, str) or not re.fullmatch(
            r"[0-9a-f]{40}", self.engine_commit
        ):
            raise ValueError("engine_commit must be a full lowercase SHA")
        for name, low, high in [
            ("seed", 0, 2**64 - 1),
            ("games", 1, 1000000),
            ("max_plies", 1, 20000),
            ("max_depth", 0, 64),
            ("max_nodes", 0, 2**63 - 1),
            ("table_capacity", 0, 1000000),
        ]:
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"invalid {name}")
        if not self.sources or any(
            s not in ("random", "rules", "search") for s in self.sources
        ):
            raise ValueError("invalid sources")
        if self.initial is not None and not isinstance(self.initial, str):
            raise ValueError("invalid initial")

    def search_limits(self):
        return {
            "max_depth": self.max_depth,
            "max_nodes": self.max_nodes,
            "table_capacity": self.table_capacity,
        }

    def value(self):
        return json.loads(canonical(asdict(self)))


def game_split(seed, game_id):
    bucket = (
        int(hashlib.sha256(f"split:{seed}:{game_id}".encode()).hexdigest()[:8], 16) % 10
    )
    return "train" if bucket < 8 else "val" if bucket == 8 else "test"


def position_key(vsfen):
    # Ignore move number for conservative duplicate/leakage exclusion. Full history
    # is still retained for rule outcomes; duplicate labels are never substituted.
    return " ".join(vsfen.split()[:3])


def _atomic_bytes(path, data):
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _write_manifest(path, manifest):
    _atomic_bytes(path, (canonical(manifest) + "\n").encode())


def _manifest(config):
    return {
        "schema": SCHEMA_ID,
        "ruleset_id": RULESET_ID,
        "config": config.value(),
        "config_sha256": hashlib.sha256(canonical(config.value()).encode()).hexdigest(),
        "writer": {
            "pyarrow": pa.__version__,
            "compression": "zstd",
            "level": 3,
            "version": "2.6",
            "row_group_size": 128,
        },
        "shards": [],
        "complete": False,
    }


def _load(directory):
    try:
        if not _owned(directory):
            raise ValueError("invalid dataset ownership marker")
        manifest = json.loads((directory / "manifest.json").read_text())
        config = GenerationConfig(**manifest["config"])
        expected = _manifest(config)
        if set(manifest) != set(expected) or any(
            manifest[k] != expected[k]
            for k in expected
            if k not in ("shards", "complete")
        ):
            raise ValueError("invalid manifest/config/writer")
        shards = manifest["shards"]
        if (
            type(shards) is not list
            or len(shards) > config.games
            or type(manifest["complete"]) is not bool
        ):
            raise ValueError("invalid shard list")
        if manifest["complete"] != (len(shards) == config.games):
            raise ValueError("invalid completion")
        for index, entry in enumerate(shards):
            if (
                set(entry) != {"file", "sha256", "rows"}
                or entry["file"] != f"game-{index:06d}.parquet"
            ):
                raise ValueError("invalid shard path/order")
            if digest(directory / entry["file"]) != entry["sha256"]:
                raise ValueError("shard hash mismatch")
        return manifest, config
    except (KeyError, TypeError, OSError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid dataset: {error}") from error


def _owned(directory):
    marker = directory / OWNER_FILE
    return not marker.is_symlink() and marker.is_file() and marker.stat().st_size == 0


def _rows(config, index, seen):
    game_id = f"g{index:06d}"
    source = config.sources[index % len(config.sources)]
    game = Game(config.initial)
    initial = game.snapshot()["vsfen"]
    rows = []
    for ply in range(config.max_plies + 1):
        snapshot = game.snapshot()
        actions = game.legal_actions()
        moves = sorted(actions.values())
        teacher, played = None, None
        final = snapshot["finished"] or ply == config.max_plies
        if not final:
            if source == "search":
                teacher = game.search(**config.search_limits())
                played = teacher["best_move"]
            else:
                # Stable across workers and scheduling, without process-global RNG.
                random_id = hashlib.sha256(
                    f"move:{config.seed}:{game_id}:{ply}".encode()
                ).digest()
                played = moves[int.from_bytes(random_id, "big") % len(moves)]
        key = position_key(snapshot["vsfen"])
        duplicate = seen.get(key)
        seen.setdefault(key, f"{game_id}:{ply}")
        rows.append(
            {
                "game_id": game_id,
                "ply": ply,
                "source": source,
                "split": game_split(config.seed, game_id),
                "ruleset_id": RULESET_ID,
                "initial": initial,
                "history": game.record()["moves"],
                **{
                    k: snapshot[k]
                    for k in (
                        "vsfen",
                        "hash",
                        "side",
                        "in_check",
                        "finished",
                        "evaluation",
                    )
                },
                "result": canonical(snapshot["result"]) if snapshot["result"] else None,
                "legal_moves": moves,
                "legal_actions": sorted(actions),
                "played_move": played,
                "teacher": canonical(teacher) if teacher is not None else None,
                "teacher_valid": teacher is not None
                and teacher["completed_depth"] >= 1
                and teacher["score"] is not None,
                "termination": "natural"
                if snapshot["finished"]
                else "max_plies"
                if final
                else None,
                "duplicate_of": duplicate,
            }
        )
        if final:
            break
        if played is None or played not in moves:
            raise ValueError("no legal move for nonterminal position")
        game.play(played)
    return rows


def generate_dataset(directory, config, *, max_games=None):
    """Commit complete games only. Resume verifies every committed row first."""
    directory = Path(directory)
    if max_games is not None and (type(max_games) is not int or max_games < 0):
        raise ValueError("invalid max_games")
    # Validate initial state before creating an owned dataset.
    Game(config.initial)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "manifest.json"
    if not path.exists():
        if not (directory / OWNER_FILE).exists():
            if any(directory.iterdir()):
                raise ValueError("refusing unowned nonempty directory")
            # Creating an empty marker is atomic, even if initialization is killed
            # before the first manifest is committed. No partial JSON is trusted.
            (directory / OWNER_FILE).touch(exist_ok=False)
        elif not _owned(directory) or {p.name for p in directory.iterdir()} - {
            OWNER_FILE,
            "manifest.json.tmp",
        }:
            raise ValueError("refusing unowned initialization files")
        _write_manifest(path, _manifest(config))
    manifest, old = _load(directory)
    if old.value() != config.value():
        raise ValueError("resume config mismatch")
    report = validate_dataset(directory, require_complete=False)
    seen = report.pop("_seen")
    start = len(manifest["shards"])
    end = config.games if max_games is None else min(config.games, start + max_games)
    for index in range(start, end):
        rows = _rows(config, index, seen)
        name = f"game-{index:06d}.parquet"
        target = directory / name
        temporary = target.with_name(name + ".tmp")
        pq.write_table(
            pa.Table.from_pylist(rows, schema=SCHEMA),
            temporary,
            version="2.6",
            compression="zstd",
            compression_level=3,
            use_dictionary=False,
            write_statistics=False,
            row_group_size=128,
        )
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        manifest["shards"].append(
            {"file": name, "sha256": digest(target), "rows": len(rows)}
        )
        manifest["complete"] = index + 1 == config.games
        _write_manifest(path, manifest)
    return manifest


def validate_dataset(directory, *, require_complete=True):
    """Replay each committed game; independently check facts and recompute teachers.

    Never use the generator's row-building function as the validation oracle.
    duplicate_of means excluded from *all* training/evaluation sampling; it is
    retained only for replay/provenance. No duplicate can leak into another split.
    """
    directory = Path(directory)
    manifest, config = _load(directory)
    if require_complete and (not manifest["complete"] or not manifest["shards"]):
        raise ValueError("incomplete dataset")
    seen, sources, splits = {}, Counter(), Counter()
    total, duplicates = 0, 0
    for index, entry in enumerate(manifest["shards"]):
        table = pq.read_table(directory / entry["file"])
        if not table.schema.equals(SCHEMA, check_metadata=True):
            raise ValueError("Parquet schema mismatch")
        rows = table.to_pylist()
        if len(rows) != entry["rows"] or not rows or len(rows) > config.max_plies + 1:
            raise ValueError("invalid row count")
        game = Game(config.initial)
        initial = game.snapshot()["vsfen"]
        game_id = f"g{index:06d}"
        source = config.sources[index % len(config.sources)]
        for ply, row in enumerate(rows):
            s = game.snapshot()
            actions = game.legal_actions()
            expected = {
                "game_id": game_id,
                "ply": ply,
                "source": source,
                "split": game_split(config.seed, game_id),
                "ruleset_id": RULESET_ID,
                "initial": initial,
                "history": game.record()["moves"],
                "result": canonical(s["result"]) if s["result"] else None,
                "legal_moves": sorted(actions.values()),
                "legal_actions": sorted(actions),
            }
            expected.update(
                {
                    k: s[k]
                    for k in (
                        "vsfen",
                        "hash",
                        "side",
                        "in_check",
                        "finished",
                        "evaluation",
                    )
                }
            )
            for key, value in expected.items():
                if row[key] != value:
                    raise ValueError(f"invalid {key} at {game_id}:{ply}")
            key = position_key(s["vsfen"])
            if row["duplicate_of"] != seen.get(key):
                raise ValueError("invalid duplicate exclusion")
            seen.setdefault(key, f"{game_id}:{ply}")
            if row["duplicate_of"] is not None:
                duplicates += 1
            else:
                splits[row["split"]] += 1
            final = s["finished"] or ply == config.max_plies
            if (ply == len(rows) - 1) != final:
                raise ValueError("missing/extra final row")
            termination = "natural" if s["finished"] else "max_plies" if final else None
            if row["termination"] != termination:
                raise ValueError("invalid termination")
            teacher = (
                game.search(**config.search_limits())
                if source == "search" and not final
                else None
            )
            if row["teacher"] != (canonical(teacher) if teacher is not None else None):
                raise ValueError("invalid teacher")
            valid = (
                teacher is not None
                and teacher["completed_depth"] >= 1
                and teacher["score"] is not None
            )
            if row["teacher_valid"] != valid:
                raise ValueError("invalid teacher eligibility")
            if final:
                if row["played_move"] is not None:
                    raise ValueError("move after termination")
            else:
                played = row["played_move"]
                if teacher is None:
                    random_id = hashlib.sha256(
                        f"move:{config.seed}:{game_id}:{ply}".encode()
                    ).digest()
                    legal = sorted(actions.values())
                    if played != legal[int.from_bytes(random_id, "big") % len(legal)]:
                        raise ValueError("invalid seeded move")
                if (
                    played not in actions.values()
                    or teacher is not None
                    and played != teacher["best_move"]
                ):
                    raise ValueError("invalid played move")
                game.play(played)
            sources[source] += 1
            total += 1
    return {
        "games": len(manifest["shards"]),
        "rows": total,
        "sources": dict(sources),
        "eligible_splits": dict(splits),
        "duplicates": duplicates,
        **({"_seen": seen} if not require_complete else {}),
    }
