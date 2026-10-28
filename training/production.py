"""External production helpers; this module's pure accounting is safe on Mac."""

import hashlib
import math


def trajectory_move(seed, game_id, ply, legal, teacher_move, opening_plies):
    if teacher_move is not None and ply >= opening_plies:
        return teacher_move
    value = hashlib.sha256(f"move:{seed}:{game_id}:{ply}".encode()).digest()
    return legal[int.from_bytes(value, "big") % len(legal)]


def merge_duplicates(rows, seen):
    for row in rows:
        key = " ".join(row["vsfen"].split()[:3])
        row["duplicate_of"] = seen.get(key)
        seen.setdefault(key, f"{row['game_id']}:{row['ply']}")


def estimate_production(
    *,
    target_eligible,
    measured_rows,
    measured_eligible,
    generate_seconds,
    validate_seconds,
    regenerate_seconds,
    setup_seconds,
    hourly_usd,
    contingency,
):
    values = (
        target_eligible,
        measured_rows,
        measured_eligible,
        generate_seconds,
        validate_seconds,
        regenerate_seconds,
        hourly_usd,
    )
    if any(isinstance(v, bool) or not math.isfinite(v) or v <= 0 for v in values):
        raise ValueError("estimate requires positive completed measurements")
    if (
        measured_eligible > measured_rows
        or not math.isfinite(setup_seconds)
        or setup_seconds < 0
        or not math.isfinite(contingency)
        or contingency < 0
    ):
        raise ValueError("invalid yield, setup or contingency")
    rows = math.ceil(target_eligible * measured_rows / measured_eligible)
    base = setup_seconds + rows / measured_rows * (
        generate_seconds + validate_seconds + regenerate_seconds
    )
    seconds = math.ceil(base * (1 + contingency))
    return {
        "raw_rows_needed": rows,
        "base_seconds": base,
        "budget_seconds": seconds,
        "estimated_usd": seconds / 3600 * hourly_usd,
        "scope": "measured configuration only; representative pilot required",
    }


def _game(config, index):
    import pyarrow as pa

    from .data import _rows

    pa.set_cpu_count(1)
    pa.set_io_thread_count(1)
    return _rows(config, index, {})


def game_rows(config, start, end, workers):
    if type(workers) is not int or not 1 <= workers <= 4:
        raise ValueError("workers must be between 1 and 4")
    if workers == 1:
        for index in range(start, end):
            yield _game(config, index)
        return
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor
    from itertools import repeat

    with ProcessPoolExecutor(
        max_workers=workers, mp_context=multiprocessing.get_context("spawn")
    ) as pool:
        yield from pool.map(
            _game, repeat(config), range(start, end), buffersize=workers
        )


def validate_job(job, *, system, ci):
    if system != "linux":
        raise ValueError("production execution requires Linux")
    if job.get("schema") != 1 or job.get("purpose") not in (
        "representative",
        "production",
        "ci-smoke",
    ):
        raise ValueError("invalid production job schema/purpose")
    smoke = job["purpose"] == "ci-smoke"
    if smoke != ci or job.get("provider") not in (
        ("ci",) if smoke else ("cloudrift", "vast")
    ):
        raise ValueError(
            "CI correctness smoke and remote measurements must be distinct"
        )
    if not smoke and job.get("approved") is not True:
        raise ValueError("explicit approval of the remote quote is required")
    seconds, rate, cap = (
        job.get(k) for k in ("approved_seconds", "hourly_usd", "max_cost_usd")
    )
    if any(
        type(v) not in (int, float) or not math.isfinite(v) or v <= 0
        for v in (seconds, rate, cap)
    ):
        raise ValueError("invalid remote cost/time budget")
    if seconds > (30 if smoke else 86400) or rate * seconds / 3600 > cap:
        raise ValueError("job exceeds its approved cost/time budget")
    if type(job.get("workers")) is not int or not 1 <= job["workers"] <= 4:
        raise ValueError("invalid worker count")
    minimum = job.get("minimum_eligible_rows")
    if type(minimum) is not int or minimum < (
        100000 if job["purpose"] == "production" else 1
    ):
        raise ValueError("production requires at least 100000 eligible rows")
    if job.get("gpu_model") not in ("rtx5090", "rtx4090"):
        raise ValueError("invalid selected GPU")
    if smoke and (
        job["config"].get("games", 0) > 6
        or job["config"].get("max_plies", 0) > 4
        or job["config"].get("max_depth", 0) > 1
        or job["config"].get("max_nodes", 0) > 100
        or job["workers"] > 2
    ):
        raise ValueError("CI smoke exceeds correctness-only scope")


def _worker(output, job):
    import time

    from .data import (
        GenerationConfig,
        canonical,
        digest,
        generate_dataset,
        validate_dataset,
    )

    config = GenerationConfig(**job["config"])
    first, second = output / "first", output / "second"
    times = {}
    start = time.perf_counter()
    generate_dataset(first, config, workers=job["workers"])
    times["generate_seconds"] = time.perf_counter() - start
    start = time.perf_counter()
    validation = validate_dataset(first)
    times["validate_seconds"] = time.perf_counter() - start
    partial = {"complete": False, "validation": validation, **times}
    (output / "worker-result.json").write_text(canonical(partial) + "\n")
    if validation["eligible_rows"] < job["minimum_eligible_rows"]:
        raise ValueError(
            "eligible row target not reached; do not substitute raw row count"
        )
    if not validation["eligible_teachers"]:
        raise ValueError("no nonduplicate valid search teachers")
    start = time.perf_counter()
    generate_dataset(second, config, workers=job["workers"])
    times["regenerate_seconds"] = time.perf_counter() - start
    first_files = {
        p.name: digest(p) for p in first.iterdir() if not p.name.endswith(".tmp")
    }
    second_files = {
        p.name: digest(p) for p in second.iterdir() if not p.name.endswith(".tmp")
    }
    if first_files != second_files:
        raise ValueError("production regeneration bytes differ")
    result = {
        "complete": True,
        "source_commit": config.engine_commit,
        "validation": validation,
        "regenerated_bytes_match": True,
        "files": first_files,
        "parquet_bytes": sum(p.stat().st_size for p in first.glob("*.parquet")),
        "dataset_manifest_sha256": digest(first / "manifest.json"),
        **times,
    }
    (output / "worker-result.json").write_text(canonical(result) + "\n")


def main():
    import argparse
    import json
    import os
    import platform
    import subprocess
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    job = json.loads(args.job.read_text())
    validate_job(
        job, system=sys.platform, ci=os.environ.get("GITHUB_ACTIONS") == "true"
    )
    if args.worker:
        _worker(args.output, job)
        return
    from .data import GenerationConfig, canonical
    from .pilot import check_gpu_configuration, parse_gpu_inventory
    from .runner import run_remote_bounded

    root = Path(__file__).resolve().parents[1]
    config = GenerationConfig(**job["config"])
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    if (
        subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True)
        or config.engine_commit != commit
    ):
        parser.error(
            "production requires a clean checkout of its recorded source commit"
        )
    if not args.output.resolve().is_relative_to(root / "runs"):
        parser.error("production output must be under ignored runs/")
    gpu = None
    if job["purpose"] != "ci-smoke":
        gpu = parse_gpu_inventory(
            subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=name,memory.total,driver_version",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                timeout=10,
            )
        )
        check_gpu_configuration(gpu, model=job["gpu_model"])
    args.output.mkdir(parents=True, exist_ok=True)
    saved = args.output / "job.json"
    if saved.exists() and json.loads(saved.read_text()) != job:
        parser.error("production resume job differs")
    report_path = args.output / "report.json"
    if report_path.exists() and json.loads(report_path.read_text()).get("complete"):
        parser.error("production already completed; preserve its receipt")
    saved.write_text(canonical(job) + "\n")
    context = {
        "source_commit": commit,
        "uv_lock_sha256": hashlib.sha256((root / "uv.lock").read_bytes()).hexdigest(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "logical_cpus": os.cpu_count(),
        "gpu": gpu,
        "measurement_kind": "ci-correctness-only"
        if job["purpose"] == "ci-smoke"
        else "external-cpu-production",
        "job_sha256": hashlib.sha256(canonical(job).encode()).hexdigest(),
    }
    with (args.output / "worker.log").open("a") as log:
        supervisor = run_remote_bounded(
            [
                sys.executable,
                "-m",
                "training.production",
                str(saved),
                str(args.output),
                "--worker",
            ],
            ledger=args.output / "budget.json",
            seconds=job["approved_seconds"],
            approved_seconds=job["approved_seconds"],
            log=log,
        )
    report = {"complete": False, "context": context, "supervisor": supervisor}
    result = args.output / "worker-result.json"
    if result.exists():
        report.update(json.loads(result.read_text()))
    if supervisor["reason"] != "completed":
        report["complete"] = False
    report_path.write_text(canonical(report) + "\n")
    print(
        canonical(
            {
                "complete": report["complete"],
                "reason": supervisor["reason"],
                "report": str(report_path),
            }
        )
    )
    raise SystemExit(0 if report["complete"] else 1)


if __name__ == "__main__":
    main()
