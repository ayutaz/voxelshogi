"""Linux-only pilot for approved GPU hosts; never provisions a cloud instance."""

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def summarize(samples):
    if not samples:
        raise ValueError("empty measurement")
    total = 0.0
    teachers = 0
    for sample in samples:
        seconds = sample["search_seconds"]
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError("invalid measured duration")
        total += seconds
        teachers += sample["completed_depth"] >= 1 and sample["score"] is not None
    return {
        "sample_count": len(samples),
        "teacher_count": teachers,
        "unlabelled_count": len(samples) - teachers,
        "total_search_seconds": total,
        "samples_per_second": len(samples) / total,
        "teacher_samples_per_second": teachers / total,
        "completed_depths": dict(Counter(str(s["completed_depth"]) for s in samples)),
        "stop_reasons": dict(Counter(s["stop_reason"] for s in samples)),
    }


def parse_gpu_inventory(text):
    rows = list(csv.reader(text.strip().splitlines(), skipinitialspace=True))
    if len(rows) != 1 or len(rows[0]) != 3:
        raise ValueError("exactly one GPU is required")
    name, memory, driver = (v.strip() for v in rows[0])
    try:
        memory = int(memory)
    except ValueError as error:
        raise ValueError("invalid GPU memory") from error
    if not name or memory < 1 or not driver:
        raise ValueError("invalid GPU inventory")
    return {"name": name, "memory_mib": memory, "driver": driver}


def check_execution_host(system, *, allow_no_gpu, ci):
    if system != "linux":
        raise ValueError("pilot execution requires Linux; do not benchmark on Mac")
    if allow_no_gpu and not ci:
        raise ValueError("no-GPU mode is limited to CI correctness smoke")


def _cases(smoke):
    from voxelshogi import Game

    if smoke:
        fixture = json.loads(
            (ROOT / "crates/voxelshogi-wasm/tests/fixtures/search.json").read_text()
        )[0]
        return [
            {"name": "ci-corner-kings", "record": fixture["record"], "kind": "ci-only"}
        ]
    fixtures = json.loads((ROOT / "export/fixtures/positions.json").read_text())
    middle = Game()
    for ply in range(64):
        s = middle.snapshot()
        if s["finished"]:
            raise ValueError("fixed trajectory ended before its 64-ply checkpoint")
        moves = sorted(s["legal_moves"])
        choice = int.from_bytes(
            hashlib.sha256(f"m4-pilot-v1:1729:{ply}".encode()).digest(), "big"
        ) % len(moves)
        middle.play(moves[choice])
    return [
        {
            "name": "opening-b",
            "record": fixtures[0]["record"],
            "kind": "standard-opening",
        },
        {
            "name": "opening-w",
            "record": fixtures[1]["record"],
            "kind": "standard-opening",
        },
        {
            "name": "trajectory-64",
            "record": middle.record(),
            "kind": "fixed-random-trajectory-not-strategic-phase",
        },
        {
            "name": "sparse-mate",
            "record": fixtures[2]["record"],
            "kind": "synthetic-endgame",
        },
        {
            "name": "sparse-hands",
            "record": fixtures[3]["record"],
            "kind": "synthetic-endgame-with-drops",
        },
    ]


def _worker(out, commit, smoke):
    import pyarrow as pa
    from voxelshogi import Game

    from .data import (
        GenerationConfig,
        canonical,
        digest,
        generate_dataset,
        validate_dataset,
    )

    pa.set_cpu_count(1)
    pa.set_io_thread_count(1)
    cases = _cases(smoke)
    (out / "inputs.json").write_text(canonical(cases) + "\n")
    profiles = [{"name": "d1", "max_depth": 1, "max_nodes": 100 if smoke else 1000}]
    if not smoke:
        profiles.append({"name": "d2", "max_depth": 2, "max_nodes": 10000})
    repeats = 1 if smoke else 3
    samples, warmups = [], []
    with (out / "samples.jsonl").open("w") as progress:
        for case in cases:
            started = time.perf_counter()
            game = Game.from_record(case["record"])
            s = game.snapshot()
            replay_seconds = time.perf_counter() - started
            for profile in profiles:
                limits = {k: v for k, v in profile.items() if k != "name"}
                for trial in range(-1, repeats):
                    start = time.perf_counter()
                    result = game.search(**limits)
                    elapsed = time.perf_counter() - start
                    item = {
                        "case": case["name"],
                        "kind": case["kind"],
                        "profile": profile["name"],
                        "limits": limits,
                        "trial": trial,
                        "search_seconds": elapsed,
                        "replay_seconds": replay_seconds,
                        "hash": s["hash"],
                        "legal_move_count": len(s["legal_moves"]),
                        "board_pieces": sum(p != 0 for p in s["board"]),
                        "hand_pieces": sum(s["hands"]),
                        **result,
                    }
                    if game.snapshot()["hash"] != s["hash"]:
                        raise ValueError("search mutated its input")
                    (warmups if trial == -1 else samples).append(item)
                    progress.write(canonical({"warmup": trial == -1, **item}) + "\n")
                    progress.flush()
                    os.fsync(progress.fileno())
    initial = cases[0]["record"]["initial"] if smoke else None
    config = GenerationConfig(
        engine_commit=commit,
        initial=initial,
        games=3 if smoke else 6,
        max_plies=2 if smoke else 16,
        max_depth=1 if smoke else 2,
        max_nodes=100 if smoke else 10000,
    )
    times = {}
    for label, action in [
        ("generate_seconds", lambda: generate_dataset(out / "first", config)),
        ("validate_seconds", lambda: validate_dataset(out / "first")),
        ("regenerate_seconds", lambda: generate_dataset(out / "second", config)),
    ]:
        start = time.perf_counter()
        value = action()
        times[label] = time.perf_counter() - start
        if label == "validate_seconds":
            validation = value
    first = {p.name: digest(p) for p in (out / "first").iterdir()}
    second = {p.name: digest(p) for p in (out / "second").iterdir()}
    if first != second:
        raise ValueError("regenerated files differ")
    result = {
        "complete": True,
        "measurement_kind": "ci-smoke" if smoke else "approved-remote-cpu-pilot",
        "input_sha256": digest(out / "inputs.json"),
        "profiles": profiles,
        "expected_samples": len(cases) * len(profiles) * repeats,
        "samples": samples,
        "warmups": warmups,
        "overall": summarize(samples),
        "by_case_profile": {
            f"{case['name']}:{profile['name']}": summarize(
                [
                    s
                    for s in samples
                    if s["case"] == case["name"] and s["profile"] == profile["name"]
                ]
            )
            for case in cases
            for profile in profiles
        },
        "dataset": {
            "config": config.value(),
            "validation": validation,
            **times,
            "parquet_bytes": sum(
                p.stat().st_size for p in (out / "first").glob("*.parquet")
            ),
            "files": first,
            "regenerated_bytes_match": True,
        },
    }
    (out / "worker-result.json").write_text(canonical(result) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--provider", choices=["cloudrift", "vast", "ci"], default="cloudrift"
    )
    parser.add_argument("--seconds", type=float, default=240)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--allow-no-gpu", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--commit", help=argparse.SUPPRESS)
    args = parser.parse_args()
    ci = os.environ.get("GITHUB_ACTIONS") == "true"
    check_execution_host(sys.platform, allow_no_gpu=args.allow_no_gpu, ci=ci)
    if args.worker:
        _worker(args.output, args.commit, args.smoke)
        return
    if args.allow_no_gpu and (not args.smoke or args.provider != "ci"):
        parser.error("CI no-GPU mode requires --smoke --provider ci")
    if args.provider == "ci" and not args.allow_no_gpu:
        parser.error("CI measurements must be explicitly labelled no-GPU smoke")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True):
        parser.error("commit task-owned changes before running a pilot")
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    gpu = None
    if not args.allow_no_gpu:
        raw = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=10,
        )
        gpu = parse_gpu_inventory(raw)
        if "RTX 4090" not in gpu["name"] or gpu["memory_mib"] < 20000:
            parser.error(
                "this pilot requires the approved single RTX 4090 configuration"
            )
    import psutil

    from .data import canonical
    from .runner import run_bounded

    args.output.mkdir(parents=True, exist_ok=False)
    cpu_model = next(
        (
            line.split(":", 1)[1].strip()
            for line in Path("/proc/cpuinfo").read_text().splitlines()
            if line.startswith("model name")
        ),
        "unknown",
    )
    cgroup = {}
    for name in ("cpu.max", "cpuset.cpus.effective", "memory.max"):
        path = Path("/sys/fs/cgroup") / name
        cgroup[name] = path.read_text().strip() if path.is_file() else None
    context = {
        "schema": 1,
        "source_commit": commit,
        "provider": args.provider,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "logical_cpus": os.cpu_count(),
        "cpu_model": cpu_model,
        "cgroup": cgroup,
        "system_ram_bytes": psutil.virtual_memory().total,
        "gpu": gpu,
        "gpu_training_tested": False,
    }
    (args.output / "context.json").write_text(canonical(context) + "\n")
    command = [
        sys.executable,
        "-m",
        "training.pilot",
        str(args.output),
        "--worker",
        "--commit",
        commit,
        "--provider",
        args.provider,
    ]
    if args.smoke:
        command.append("--smoke")
    if args.allow_no_gpu:
        command.append("--allow-no-gpu")
    with (args.output / "worker.log").open("w") as log:
        bounded = run_bounded(
            command,
            ledger=ROOT / "runs/m4/session-budget.json",
            seconds=args.seconds,
            log=log,
        )
    report = {"context": context, "supervisor": bounded, "complete": False}
    result_path = args.output / "worker-result.json"
    if bounded["reason"] == "completed" and result_path.exists():
        result = json.loads(result_path.read_text())
        if result["expected_samples"] != len(result["samples"]):
            raise ValueError("missing pilot measurements")
        report.update(result)
    (args.output / "report.json").write_text(canonical(report) + "\n")
    print(
        canonical(
            {
                "complete": report["complete"],
                "reason": bounded["reason"],
                "provider": args.provider,
                "report": str(args.output / "report.json"),
            }
        )
    )
    raise SystemExit(0 if report["complete"] else 1)


if __name__ == "__main__":
    main()
