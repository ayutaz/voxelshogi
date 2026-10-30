"""Linux-only paired teacher pilot, atomic per-game Parquet, replay and audits."""

import argparse
import fcntl
import json
import os
import subprocess
import sys
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

from training.checkpoint import atomic_json
from training.evaluation_v2_runner import verify_run
from training.feature_cache import file_hash
from training.research_data import (
    SCHEMA,
    audit_samples,
    canonical,
    generate_game,
    input_identity,
    pilot_protocol,
    validate_game,
    validate_protocol,
)

ROOT = Path(__file__).resolve().parents[1]
OWNER = ".voxelshogi-paired-teachers-v1"


def _linux():
    if sys.platform != "linux":
        raise ValueError("research data execution requires external Linux")


def _source(p):
    sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True
    )
    if sha != p["source_commit"] or dirty:
        raise ValueError("research workload requires its exact clean source commit")


def _read(path, maximum=2 * 1024 * 1024):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise ValueError("invalid research metadata file")

    def invalid(value):
        raise ValueError("nonfinite research JSON: " + value)

    return json.loads(path.read_text(), parse_constant=invalid)


def _schema():
    import pyarrow as pa

    return pa.schema(
        [
            ("game_id", pa.string()),
            ("seed", pa.int64()),
            ("split", pa.string()),
            ("ply", pa.int32()),
            ("vsfen", pa.string()),
            ("side", pa.string()),
            ("history", pa.list_(pa.field("element", pa.string()))),
            ("physical_id", pa.string()),
            ("input_id", pa.string()),
            ("legal_actions", pa.list_(pa.field("element", pa.int32()))),
            ("legal_moves", pa.list_(pa.field("element", pa.string()))),
            ("teachers_json", pa.string()),
        ],
        metadata={b"schema_id": SCHEMA.encode()},
    )


def _writer():
    import pyarrow as pa

    return {
        "pyarrow": pa.__version__,
        "version": "2.6",
        "compression": "zstd",
        "compression_level": 3,
        "row_group_size": 128,
    }


def _write_shard(path, rows):
    import pyarrow as pa
    import pyarrow.parquet as pq

    converted = []
    for row in rows:
        r = dict(row)
        r["teachers_json"] = canonical(r.pop("teachers"))
        converted.append(r)
    temporary = path.with_suffix(".parquet.tmp")
    pq.write_table(
        pa.Table.from_pylist(converted, schema=_schema()),
        temporary,
        version="2.6",
        compression="zstd",
        compression_level=3,
        use_dictionary=False,
        write_statistics=False,
        row_group_size=128,
    )
    with temporary.open("rb") as stream:
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    return {
        "path": path.name,
        "bytes": path.stat().st_size,
        "sha256": file_hash(path),
        "rows": len(rows),
    }


def _rows(path, descriptor):
    import pyarrow.parquet as pq

    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_size > 2 * 1024 * 1024
        or path.stat().st_size != descriptor["bytes"]
        or file_hash(path) != descriptor["sha256"]
    ):
        raise ValueError("research data file bytes/hash differs")
    table = pq.read_table(path)
    if (
        not table.schema.equals(_schema(), check_metadata=True)
        or len(table) != descriptor["rows"]
    ):
        raise ValueError("research data schema/rows differs")
    result = []
    for r in table.to_pylist():
        r["teachers"] = json.loads(r.pop("teachers_json"))
        result.append(r)
    return result


@contextmanager
def _lock(folder):
    if folder.is_symlink():
        raise ValueError("refusing symlink dataset")
    folder.mkdir(parents=True, exist_ok=True)
    marker = folder / OWNER
    if not marker.exists():
        if any(folder.iterdir()):
            raise ValueError("refusing unowned nonempty research directory")
        marker.touch(exist_ok=False)
    if marker.is_symlink() or not marker.is_file() or marker.stat().st_size != 0:
        raise ValueError("invalid research ownership marker")
    with marker.open("rb") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def _load(folder, *, require_complete, recompute):
    from voxelshogi import Game

    m = _read(folder / "manifest.json")
    p = m["protocol"]
    if (
        set(m)
        != {"schema", "protocol", "protocol_sha256", "writer", "games", "complete"}
        or m["schema"] != SCHEMA
        or m["protocol_sha256"] != validate_protocol(p)
        or m["writer"] != _writer()
        or type(m["games"]) is not list
        or len(m["games"]) > len(p["games"])
        or type(m["complete"]) is not bool
        or m["complete"] != (len(m["games"]) == len(p["games"]))
        or require_complete
        and not m["complete"]
    ):
        raise ValueError("incomplete or changed research manifest")
    rows = []
    for i, stored in enumerate(m["games"]):
        entry = dict(stored)
        f = entry.pop("file")
        if (
            set(f) != {"path", "bytes", "sha256", "rows"}
            or f["path"] != f"game-{i:06d}.parquet"
        ):
            raise ValueError("invalid research file inventory/order")
        entry["samples"] = _rows(folder / f["path"], f)
        validate_game(p, p["games"][i], entry, Game, recompute=recompute)
        rows.extend(entry["samples"])
    return m, rows


def generate_pilot(folder, protocol, *, max_games=None, stop_requested=lambda: False):
    _linux()
    from voxelshogi import Game

    validate_protocol(protocol)
    _source(protocol)
    if max_games is not None and (
        type(max_games) is not int or not 0 <= max_games <= 8
    ):
        raise ValueError("invalid research chunk size")
    folder = Path(folder)
    with _lock(folder):
        manifest = folder / "manifest.json"
        if not manifest.exists():
            if {p.name for p in folder.iterdir()} != {OWNER}:
                raise ValueError("uncommitted files without a research manifest")
            atomic_json(
                manifest,
                {
                    "schema": SCHEMA,
                    "protocol": protocol,
                    "protocol_sha256": validate_protocol(protocol),
                    "writer": _writer(),
                    "games": [],
                    "complete": False,
                },
            )
        m, _ = _load(folder, require_complete=False, recompute=True)
        if m["protocol"] != protocol:
            raise ValueError("resume protocol differs")
        start = len(m["games"])
        end = (
            len(protocol["games"])
            if max_games is None
            else min(len(protocol["games"]), start + max_games)
        )
        for i in range(start, end):
            entry = generate_game(
                protocol, protocol["games"][i], Game, stop_requested=stop_requested
            )
            validate_game(protocol, protocol["games"][i], entry, Game, recompute=False)
            rows = entry.pop("samples")
            entry["file"] = _write_shard(folder / f"game-{i:06d}.parquet", rows)
            m["games"].append(entry)
            m["complete"] = len(m["games"]) == len(protocol["games"])
            atomic_json(manifest, m)
        return m


def verify_pilot(folder):
    _linux()
    m, rows = _load(Path(folder), require_complete=True, recompute=True)
    depths = {
        name: dict(
            sorted(
                Counter(
                    str(r["teachers"][name]["search"]["completed_depth"]) for r in rows
                ).items()
            )
        )
        for name in m["protocol"]["teachers"]
    }
    return {
        "complete": True,
        "protocol_sha256": m["protocol_sha256"],
        "games": len(m["games"]),
        "rows": len(rows),
        "teacher_depths": depths,
        "files": [g["file"] for g in m["games"]],
        "verification": "all moves Rust replayed; trajectory and both teachers recomputed",
    }


def _frozen_inputs(folder):
    import pyarrow.parquet as pq
    from voxelshogi import Game

    from training.supervision import audit_corpus

    audit = audit_corpus(folder)
    manifest = _read(Path(folder) / "manifest.json")
    # Bound the compact cache by physical rows; no tensor/feature cache is built.
    identities, cache = set(), {}
    for descriptor in manifest["shards"]:
        for row in pq.read_table(Path(folder) / descriptor["file"]).to_pylist():
            physical = " ".join(row["vsfen"].split()[:3])
            if physical not in cache:
                cache[physical] = input_identity(Game(row["vsfen"]).snapshot())
            identities.add(cache[physical])
    return identities, {
        "contract": audit["contract"],
        "counts": audit["counts"],
        "input_identities": len(identities),
        "files": audit["files"],
    }


def _development_inputs(folder, expected):
    from voxelshogi import Game

    folder = Path(folder)
    verify_run(folder)
    receipt = _read(folder / "run.json")
    if receipt != expected:
        raise ValueError("development records differ from the frozen P5-0 proof")
    protocol = _read(folder / "protocol.json")
    cases = {c["id"]: c for c in protocol["cases"]}
    identities = set()
    for f in receipt["files"]:
        row = _read(folder / f["path"])
        case = cases[row["case_id"]]
        prefix = len(case["opening"]["moves"])
        game = Game(row["record"]["initial"])
        for ply in range(len(row["record"]["moves"]) + 1):
            if ply >= prefix:
                identities.add(input_identity(game.snapshot()))
            if ply < len(row["record"]["moves"]):
                game.play(row["record"]["moves"][ply])
    return identities


def audit_pilot(folder, frozen_corpus, control_run, model_run):
    _linux()
    report = verify_pilot(folder)
    m, rows = _load(Path(folder), require_complete=True, recompute=False)
    protected, corpus_proof = _frozen_inputs(frozen_corpus)
    proof = _read(ROOT / "docs/experiments/p5-evaluation-pilot-2026-10-30.json")
    development = set()
    for name, path in (("control", control_run), ("m6", model_run)):
        development.update(_development_inputs(path, proof["runs"][name]))
    protected.update(development)
    return {
        **report,
        "audit": audit_samples(m["protocol"], rows, protected=protected),
        "frozen_corpus": corpus_proof,
        "development_input_identities": len(development),
        "scope": "all frozen corpus splits plus scored P5-0 continuations and new cross-split input equivalence",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["preset", "generate", "verify", "audit"])
    parser.add_argument("protocol", type=Path)
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--control-run", type=Path)
    parser.add_argument("--model-run", type=Path)
    args = parser.parse_args()
    _linux()
    if args.operation == "preset":
        if args.output is not None:
            parser.error("preset takes only its output path")
        args.output = args.protocol
    elif args.output is None:
        parser.error("operation requires protocol and output directory")
    if not args.output.resolve().is_relative_to(ROOT / "runs"):
        parser.error("research output must remain under ignored runs/")
    if args.operation == "preset":
        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        p = pilot_protocol(sha)
        validate_protocol(p)
        _source(p)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(args.output, p)
        return
    p = _read(args.protocol)
    validate_protocol(p)
    if args.operation == "generate":
        result = generate_pilot(args.output, p)
    elif args.operation == "verify":
        result = verify_pilot(args.output)
        if result["protocol_sha256"] != validate_protocol(p):
            parser.error("output protocol differs")
    else:
        if not all((args.corpus, args.control_run, args.model_run)):
            parser.error("audit requires frozen corpus and both P5-0 runs")
        result = audit_pilot(args.output, args.corpus, args.control_run, args.model_run)
        if result["protocol_sha256"] != validate_protocol(p):
            parser.error("output protocol differs")
        atomic_json(args.output / "validation.json", result)
    print(
        json.dumps(
            {"complete": result["complete"], "operation": args.operation},
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
