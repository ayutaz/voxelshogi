"""Whole-protocol case jobs with immutable per-color progress and provenance."""

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

from training.checkpoint import atomic_json
from training.evaluation_v2 import (
    NEURAL_POLICIES,
    summarize_matches,
    validate_match_rows,
    validate_protocol,
)
from training.evaluation_v2_runner import (
    _descriptors,
    _native_player,
    _play_case,
    _prepare_players,
    _read_metadata,
    checked_execution,
    execution_runtime,
    verify_record,
    verify_run,
)
from training.feature_cache import file_hash

JOB_SCHEMA = "voxelshogi-evaluation-case-job-v1"


def plan_case_jobs(cohorts, *, max_workers):
    """Assign one opening pair per job without changing any protocol digest."""
    if (
        type(cohorts) is not dict
        or not cohorts
        or len(cohorts) > 8
        or any(
            not isinstance(n, str)
            or "--" in n
            or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,39}", n)
            for n in cohorts
        )
        or type(max_workers) is not int
        or not 1 <= max_workers <= 16
    ):
        raise ValueError("nonempty safe cohorts and bounded parallel workers required")
    jobs, reference = [], None
    for name, spec in sorted(cohorts.items()):
        digest = validate_protocol(spec)
        common = {k: v for k, v in spec.items() if k != "participants"}
        common["opponent"] = spec["participants"]["opponent"]
        if reference is not None and common != reference:
            raise ValueError("case jobs require common cases, conditions and opponent")
        reference = common
        for case in spec["cases"]:
            jobs.append(
                {
                    "job_id": name + "--" + case["id"],
                    "cohort": name,
                    "case_id": case["id"],
                    "sides": ["b", "w"],
                    "protocol": deepcopy(spec),
                    "protocol_sha256": digest,
                }
            )
    return {
        "schema": "voxelshogi-evaluation-case-plan-v1",
        "max_workers": max_workers,
        "games": 2 * len(jobs),
        "jobs": jobs,
    }


def read_case_rows(folder, protocol, *, case_id):
    """Validate a committed assigned-case prefix; Rust replay is still required."""
    digest = validate_protocol(protocol)
    if case_id not in {c["id"] for c in protocol["cases"]}:
        raise ValueError("unknown assigned evaluation case")
    folder = Path(folder)
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("invalid case job directory")
    if _read_metadata(folder / "protocol.json") != protocol:
        raise ValueError("case job protocol differs")
    receipt = _read_metadata(folder / "job.json")
    if (
        receipt.get("schema") != JOB_SCHEMA
        or type(receipt.get("complete")) is not bool
        or receipt.get("case_id") != case_id
        or receipt.get("protocol_sha256") != digest
        or type(receipt.get("games")) is not int
        or not 0 <= receipt["games"] <= 2
        or receipt["complete"]
        and receipt["games"] != 2
        or type(receipt.get("files")) is not list
        or len(receipt["files"]) != receipt["games"]
        or type(receipt.get("runtime")) is not dict
        or receipt["runtime"].get("source_commit") != protocol["source_commit"]
    ):
        raise ValueError("case job receipt/binding differs")
    expected = [f"{case_id}-{side}.json" for side in ("b", "w")][: receipt["games"]]
    if [entry.get("path") for entry in receipt["files"]] != expected or {
        p.name for p in folder.iterdir()
    } != {"protocol.json", "job.json", *expected}:
        raise ValueError("case job inventory is not its committed color prefix")
    rows = []
    for entry in receipt["files"]:
        path = folder / entry["path"]
        if (
            set(entry) != {"path", "bytes", "sha256"}
            or path.is_symlink()
            or not path.is_file()
            or type(entry["bytes"]) is not int
            or entry["bytes"] != path.stat().st_size
            or entry["sha256"] != file_hash(path)
        ):
            raise ValueError("case job match size/hash differs")
        row = _read_metadata(path)
        if row.get("case_id") != case_id:
            raise ValueError("case job contains a foreign opening")
        rows.append(row)
    validate_match_rows(rows, protocol, require_complete=False)
    if [r["model_side"] for r in rows] != ["b", "w"][: len(rows)]:
        raise ValueError("case job colors differ")
    return rows, receipt


def ordered_case_rows(protocol, parts):
    """Return the exact complete cohort rows in canonical case/color order."""
    validate_protocol(protocol)
    cases = [c["id"] for c in protocol["cases"]]
    if type(parts) is not dict or set(parts) != set(cases):
        raise ValueError("every assigned case is required for aggregation")
    flat = []
    for case_id in cases:
        group = parts[case_id]
        if (
            type(group) is not list
            or len(group) != 2
            or any(row.get("case_id") != case_id for row in group)
        ):
            raise ValueError("each case must contain both of its own colors")
        flat.extend(group)
    validate_match_rows(flat, protocol, require_complete=True)
    index = {(row["case_id"], row["model_side"]): row for row in flat}
    return [index[(case_id, side)] for case_id in cases for side in ("b", "w")]


def _linux():
    if sys.platform != "linux":
        raise ValueError("evaluation execution/replay requires external Linux")


@contextmanager
def _lease(folder):
    import fcntl

    folder.parent.mkdir(parents=True, exist_ok=True)
    lock = folder.parent / f".{folder.name}.evaluation.lock"
    if folder.is_symlink() or lock.is_symlink():
        raise ValueError("symlink evaluation output/lock")
    with lock.open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("evaluation already has a running owner") from None
        yield


def _context(protocol, artifacts, *, stop_requested=lambda: False, observe_input=None):
    game, required, commit = checked_execution(protocol, artifacts)
    players = _prepare_players(
        protocol, artifacts, stop_requested=stop_requested, observe_input=observe_input
    )
    return game, players, execution_runtime(protocol, required, commit)


def run_case_assignment(
    protocol,
    artifacts,
    folder,
    *,
    case_id,
    stop_requested=lambda: False,
    resume=False,
    observe_input=None,
):
    """Execute just one assigned pair, retaining the full cohort binding."""
    _linux()
    digest = validate_protocol(protocol)
    cases = {case["id"]: case for case in protocol["cases"]}
    if type(resume) is not bool or case_id not in cases:
        raise ValueError("explicit resume and a known assigned case required")
    folder = Path(folder)
    with _lease(folder):
        rows, saved = [], None
        if resume:
            rows, saved = read_case_rows(folder, protocol, case_id=case_id)
            for row in rows:
                verify_record(row, cases[case_id])
            if saved["complete"]:
                return saved
        elif folder.exists():
            raise FileExistsError(folder)
        game, players, runtime = _context(
            protocol,
            artifacts,
            stop_requested=stop_requested,
            observe_input=observe_input,
        )
        if saved and saved["runtime"] != runtime:
            raise ValueError("resumed case runtime differs from saved environment")
        if not resume:
            folder.mkdir(exist_ok=False)
            atomic_json(folder / "protocol.json", protocol)

        def save(*, complete=False):
            receipt = {
                "schema": JOB_SCHEMA,
                "complete": complete,
                "case_id": case_id,
                "protocol_sha256": digest,
                "runtime": runtime,
                "games": len(rows),
                "files": _descriptors(folder, rows),
            }
            atomic_json(folder / "job.json", receipt)
            return receipt

        save()
        case = cases[case_id]
        completed = {row["model_side"] for row in rows}
        for side in ("b", "w"):
            if side in completed:
                continue
            choose = {
                role: player
                or _native_player(
                    protocol["participants"][role]["policy"],
                    protocol["search_limits"],
                    case["seed"],
                )
                for role, player in players.items()
            }
            row = _play_case(
                case,
                game.from_record(case["opening"]),
                model_side=side,
                choose_model=choose["model"],
                choose_opponent=choose["opponent"],
                stop_requested=stop_requested,
            )
            row.update(
                protocol_sha256=digest,
                model_sha256=protocol["participants"]["model"]["artifact_sha256"],
                opponent_sha256=protocol["participants"]["opponent"]["artifact_sha256"],
            )
            verify_record(row, case)
            atomic_json(folder / f"{case_id}-{side}.json", row)
            rows.append(row)
            save()
        return save(complete=True)


def aggregate_case_jobs(protocol, jobs, folder):
    """Replay complete jobs and copy their original bytes in cohort order."""
    _linux()
    digest = validate_protocol(protocol)
    parts, receipts, paths, runtime = {}, [], {}, None
    cases = {case["id"]: case for case in protocol["cases"]}
    if type(jobs) is not dict or set(jobs) != set(cases):
        raise ValueError("every complete assigned case is required")
    for case_id in cases:
        source = Path(jobs[case_id])
        rows, receipt = read_case_rows(source, protocol, case_id=case_id)
        if not receipt["complete"]:
            raise ValueError("incomplete assigned case")
        if runtime is not None and receipt["runtime"] != runtime:
            raise ValueError("case job runtime differs across cohort")
        runtime = receipt["runtime"]
        for row in rows:
            verify_record(row, cases[case_id])
            paths[(case_id, row["model_side"])] = (
                source / f"{case_id}-{row['model_side']}.json"
            )
        parts[case_id] = rows
        receipts.append(
            {
                "case_id": case_id,
                "job_sha256": file_hash(source / "job.json"),
                "files": receipt["files"],
            }
        )
    rows = ordered_case_rows(protocol, parts)
    folder = Path(folder)
    with _lease(folder):
        folder.mkdir(exist_ok=False)
        atomic_json(folder / "protocol.json", protocol)
        atomic_json(
            folder / "run.json",
            {"complete": False, "protocol_sha256": digest, "games": 0, "files": []},
        )
        for row in rows:
            source = paths[(row["case_id"], row["model_side"])]
            raw = source.read_bytes()
            original = next(
                f
                for r in receipts
                if r["case_id"] == row["case_id"]
                for f in r["files"]
                if f["path"] == source.name
            )
            if (
                len(raw) != original["bytes"]
                or hashlib.sha256(raw).hexdigest() != original["sha256"]
            ):
                raise ValueError("case row changed during aggregation")
            with (folder / source.name).open("xb") as stream:
                stream.write(raw)
        summary = summarize_matches(
            rows,
            protocol,
            model_sha256=protocol["participants"]["model"]["artifact_sha256"],
            opponent_sha256=protocol["participants"]["opponent"]["artifact_sha256"],
        )
        summary["verification_scope"] = (
            "all match records Rust replayed; full-corpus leakage audit is separate"
        )
        atomic_json(folder / "summary.json", summary)
        atomic_json(
            folder / "run.json",
            {
                "complete": True,
                "protocol_sha256": digest,
                "summary_sha256": file_hash(folder / "summary.json"),
                "games": len(rows),
                "runtime": runtime,
                "files": _descriptors(folder, rows),
                "execution": "case-jobs-v1",
                "case_jobs": receipts,
            },
        )
        return verify_run(folder)


def bounded_pool(
    jobs,
    *,
    max_workers,
    start,
    retire,
    pause=lambda: time.sleep(1),
    stop_requested=lambda: False,
):
    """Keep only bounded owned process handles; failure stops all live children."""
    if type(max_workers) is not int or not 1 <= max_workers <= 16:
        raise ValueError("bounded workers required")
    pending, live = iter(jobs), []
    exhausted = False
    try:
        while live or not exhausted:
            if stop_requested():
                raise InterruptedError("evaluation pool interrupted")
            while not exhausted and len(live) < max_workers:
                if stop_requested():
                    raise InterruptedError("evaluation pool interrupted before launch")
                try:
                    item = next(pending)
                except StopIteration:
                    exhausted = True
                    break
                live.append(start(item))
            if stop_requested():
                raise InterruptedError("evaluation pool interrupted")
            for child in list(live):
                code = child.poll()
                if code is None:
                    continue
                if code != 0:
                    raise RuntimeError(f"evaluation child failed with exit code {code}")
                retire(child, False)
                live.remove(child)
            if live:
                pause()
    except BaseException as error:
        for child in live:
            try:
                retire(child, True)
            except Exception as cleanup_error:
                error.add_note(
                    f"owned-child cleanup failed: {type(cleanup_error).__name__}"
                )
        raise


def validate_case_plan(plan):
    """Rebuild assignments instead of trusting serialized job counts or hashes."""
    try:
        cohorts = {}
        for job in plan["jobs"]:
            name, spec = job["cohort"], job["protocol"]
            if name in cohorts and cohorts[name] != spec:
                raise ValueError("inconsistent cohort protocols")
            cohorts[name] = spec
        if plan_case_jobs(cohorts, max_workers=plan["max_workers"]) != plan:
            raise ValueError("serialized case plan differs from frozen assignments")
    except KeyError, TypeError:
        raise ValueError("invalid serialized case plan") from None
    return cohorts


def check_previous_launch(path, *, is_live):
    """An uncertain create is never resent; a known missing handle may resume."""
    path = Path(path)
    if not path.exists():
        return None
    info = _read_metadata(path)
    if info.get("state") == "requested":
        raise ValueError("previous child creation outcome is unknown; inspect it")
    if info.get("state") == "running":
        if type(info.get("pid")) is not int or type(info.get("create_time")) not in (
            int,
            float,
        ):
            raise ValueError("invalid previous child handle")
        if is_live(info):
            raise ValueError("previous evaluation child is still live")
    elif info.get("state") != "terminal" or type(info.get("exit_code")) is not int:
        raise ValueError("invalid previous child outcome")
    return info


def _handle_live(info):
    import psutil

    try:
        process = psutil.Process(info["pid"])
        return (
            process.create_time() == info["create_time"]
            and process.status() != psutil.STATUS_ZOMBIE
        )
    except psutil.NoSuchProcess:
        return False


def run_case_plan(
    plan, artifacts, folder, *, resume=False, stop_requested=lambda: False
):
    """Run immutable pair assignments in independent bounded Linux processes."""
    _linux()
    import psutil

    cohorts = validate_case_plan(plan)
    if (
        type(resume) is not bool
        or type(artifacts) is not dict
        or set(artifacts) != set(cohorts)
    ):
        raise ValueError("explicit resume and every cohort artifact mapping required")
    normalized = {}
    for name, spec in cohorts.items():
        required = {
            role
            for role, p in spec["participants"].items()
            if p["policy"] in NEURAL_POLICIES
        }
        if type(artifacts[name]) is not dict or set(artifacts[name]) != required:
            raise ValueError("unexpected or missing evaluation artifact")
        normalized[name] = {
            role: str(Path(path).resolve()) for role, path in artifacts[name].items()
        }
    folder = Path(folder)
    if folder.is_symlink():
        raise ValueError("symlink evaluation pool output")
    folder = folder.resolve()
    with _lease(folder):
        if resume:
            if (
                _read_metadata(folder / "plan.json") != plan
                or _read_metadata(folder / "artifacts.json") != normalized
            ):
                raise ValueError("saved evaluation plan/artifact paths differ")
        else:
            folder.mkdir(exist_ok=False)
            atomic_json(folder / "plan.json", plan)
            atomic_json(folder / "artifacts.json", normalized)
            for name in ("protocols", "jobs", "launches", "logs", "cohorts"):
                (folder / name).mkdir()
            for name, spec in cohorts.items():
                atomic_json(folder / "protocols" / (name + ".json"), spec)
        pending, previous = [], {}
        for job in plan["jobs"]:
            job_id = job["job_id"]
            prior = check_previous_launch(
                folder / "launches" / (job_id + ".json"), is_live=_handle_live
            )
            previous[job_id] = prior
            target = folder / "jobs" / job_id
            if target.exists():
                _, receipt = read_case_rows(
                    target, job["protocol"], case_id=job["case_id"]
                )
                if receipt["complete"]:
                    continue
            pending.append(job)
        children = {}

        def retire(child, failed):
            path, info = children[child]
            if child.poll() is None:
                child.send_signal(signal.SIGINT)
                try:
                    child.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=10)
            code = child.wait(timeout=1)
            atomic_json(
                path,
                {
                    **info,
                    "state": "terminal",
                    "exit_code": code,
                    "ended_at": time.time(),
                    "pool_aborted": failed,
                },
            )

        def start(job):
            job_id = job["job_id"]
            path = folder / "launches" / (job_id + ".json")
            info = {
                "state": "requested",
                "requested_at": time.time(),
                "job_id": job_id,
                "protocol_sha256": job["protocol_sha256"],
                "previous_launch": previous[job_id],
            }
            atomic_json(path, info)
            target = folder / "jobs" / job_id
            args = [
                sys.executable,
                "-m",
                "training.evaluation_jobs",
                "case",
                "--protocol",
                str(folder / "protocols" / (job["cohort"] + ".json")),
                "--case-id",
                job["case_id"],
                "--output",
                str(target),
            ]
            for role, model_path in normalized[job["cohort"]].items():
                args.extend(["--" + role, model_path])
            if target.exists():
                args.append("--resume")
            env = {
                key: value
                for key, value in os.environ.items()
                if key
                not in {
                    "HF_TOKEN",
                    "HUGGING_FACE_HUB_TOKEN",
                    "HUGGINGFACE_HUB_TOKEN",
                    "VAST_API_KEY",
                    "CLOUDRIFT_API_KEY",
                }
            }
            env.update(
                OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1"
            )
            log = folder / "logs" / (job_id + "-" + str(time.time_ns()) + ".log")
            with log.open("xb") as stream:
                child = subprocess.Popen(
                    args,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            children[child] = (path, info)
            try:
                try:
                    created = psutil.Process(child.pid).create_time()
                except psutil.NoSuchProcess:
                    if child.poll() is None:
                        raise RuntimeError(
                            "child handle disappeared without terminal status"
                        ) from None
                    created = None
                info = {
                    **info,
                    "state": "running",
                    "pid": child.pid,
                    "create_time": created,
                }
                children[child] = (path, info)
                if created is None:
                    retire(child, child.returncode != 0)
                else:
                    atomic_json(path, info)
                return child
            except BaseException:
                retire(child, True)
                raise

        bounded_pool(
            pending,
            max_workers=plan["max_workers"],
            start=start,
            retire=retire,
            stop_requested=stop_requested,
        )
        summaries = {}
        for name, spec in cohorts.items():
            target = folder / "cohorts" / name
            if target.exists():
                if _read_metadata(target / "protocol.json") != spec:
                    raise ValueError("aggregate protocol differs")
                summaries[name] = verify_run(target)
            else:
                jobs = {
                    job["case_id"]: folder / "jobs" / job["job_id"]
                    for job in plan["jobs"]
                    if job["cohort"] == name
                }
                summaries[name] = aggregate_case_jobs(spec, jobs, target)
        atomic_json(
            folder / "complete.json",
            {
                "complete": True,
                "games": plan["games"],
                "plan_sha256": hashlib.sha256(
                    (folder / "plan.json").read_bytes()
                ).hexdigest(),
                "cohorts": sorted(summaries),
            },
        )
        return summaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    case = sub.add_parser("case")
    case.add_argument("--protocol", required=True, type=Path)
    case.add_argument("--case-id", required=True)
    case.add_argument("--model", type=Path)
    case.add_argument("--opponent", type=Path)
    pool = sub.add_parser("pool")
    pool.add_argument("--plan", required=True, type=Path)
    pool.add_argument("--artifacts", required=True, type=Path)
    for command in (case, pool):
        command.add_argument("--output", required=True, type=Path)
        command.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    stopped = False

    def stop(*_):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    if args.command == "case":
        artifacts = {
            role: getattr(args, role)
            for role in ("model", "opponent")
            if getattr(args, role) is not None
        }
        result = run_case_assignment(
            _read_metadata(args.protocol),
            artifacts,
            args.output,
            case_id=args.case_id,
            resume=args.resume,
            stop_requested=lambda: stopped,
        )
    else:
        result = run_case_plan(
            _read_metadata(args.plan),
            _read_metadata(args.artifacts),
            args.output,
            resume=args.resume,
            stop_requested=lambda: stopped,
        )
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
