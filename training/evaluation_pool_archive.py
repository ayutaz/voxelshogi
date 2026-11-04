"""Lossless stopped evaluation pools; Parquet and real replay stay on Linux."""

import hashlib
import json
import os
import re
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path

from training.checkpoint import atomic_json
from training.evaluation_jobs import (
    _handle_live,
    _lease,
    check_previous_launch,
    read_case_rows,
    validate_case_plan,
)
from training.evaluation_v2 import NEURAL_POLICIES, fingerprint
from training.evaluation_v2_runner import (
    checked_execution,
    execution_runtime,
    verify_record,
)
from training.feature_cache import file_hash

SCHEMA = "voxelshogi-evaluation-pool-archive-v1"


def _linux():
    if sys.platform != "linux":
        raise ValueError("evaluation pool data execution requires external Linux")


def _read(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32 * 1024**2:
        raise ValueError("invalid pool metadata/member")
    return path.read_bytes()


def _artifacts(cohorts, artifacts):
    if type(artifacts) is not dict or set(artifacts) != set(cohorts):
        raise ValueError("every cohort artifact mapping is required")
    for name, spec in cohorts.items():
        roles = {
            k for k, p in spec["participants"].items() if p["policy"] in NEURAL_POLICIES
        }
        if type(artifacts[name]) is not dict or set(artifacts[name]) != roles:
            raise ValueError("artifact roles differ from the full protocol")
        for path in artifacts[name].values():
            if (
                not isinstance(path, str)
                or "\x00" in path
                or not Path(path).is_absolute()
            ):
                raise ValueError("absolute local model artifact paths required")
    return artifacts


def collect_pool(folder, expected_plan, *, replay=None, is_live=_handle_live):
    """Inspect committed prefixes; caller holds the pool lease when packing."""
    if replay is None:
        _linux()
        replay = verify_record
    cohorts = validate_case_plan(expected_plan)
    folder = Path(folder)
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("invalid evaluation pool")
    files = {name: _read(folder / name) for name in ("plan.json", "artifacts.json")}
    if json.loads(files["plan.json"]) != expected_plan:
        raise ValueError("saved pool plan differs")
    _artifacts(cohorts, json.loads(files["artifacts.json"]))
    if (folder / "protocols").is_symlink() or {
        p.name for p in (folder / "protocols").iterdir()
    } != {n + ".json" for n in cohorts}:
        raise ValueError("pool protocol inventory differs")
    for name, spec in cohorts.items():
        key = "protocols/" + name + ".json"
        files[key] = _read(folder / key)
        if json.loads(files[key]) != spec:
            raise ValueError("pool cohort protocol differs")
    known = {j["job_id"] for j in expected_plan["jobs"]}
    for directory in ("jobs", "launches"):
        path = folder / directory
        if path.is_symlink() or not path.is_dir():
            raise ValueError("invalid pool job/launch directory")
        names = {p.name for p in path.iterdir()}
        if directory == "jobs":
            locks = {"." + name + ".evaluation.lock" for name in known}
            for name in names & locks:
                item = path / name
                if item.is_symlink() or not item.is_file() or item.stat().st_size != 0:
                    raise ValueError("invalid case lease metadata")
            names -= locks
        allowed = known if directory == "jobs" else {n + ".json" for n in known}
        if not names <= allowed:
            raise ValueError("foreign pool job/launch")
    launches = {}
    # Resolve every handle before replaying or archiving any completed work.
    for job in expected_plan["jobs"]:
        name = job["job_id"]
        old = check_previous_launch(
            folder / "launches" / (name + ".json"), is_live=is_live
        )
        if old is not None:
            launches[name] = old
    games, complete, present = 0, 0, []
    counts = dict.fromkeys(cohorts, 0)
    runtimes = {}
    for job in expected_plan["jobs"]:
        name, cohort = job["job_id"], job["cohort"]
        path = folder / "jobs" / name
        if path.is_symlink():
            raise ValueError("symlink case job cannot be archived")
        if not path.exists():
            continue
        rows, receipt = read_case_rows(path, job["protocol"], case_id=job["case_id"])
        if cohort in runtimes and runtimes[cohort] != receipt["runtime"]:
            raise ValueError("saved cohort runtime differs across jobs")
        runtimes[cohort] = receipt["runtime"]
        case = next(c for c in job["protocol"]["cases"] if c["id"] == job["case_id"])
        for row in rows:
            replay(row, case)
        for member in (
            "protocol.json",
            "job.json",
            *(x["path"] for x in receipt["files"]),
        ):
            key = "jobs/" + name + "/" + member
            raw = _read(folder / key)
            if member == "protocol.json" and json.loads(raw) != job["protocol"]:
                raise ValueError("pool protocol changed during snapshot")
            if member == "job.json" and json.loads(raw) != receipt:
                raise ValueError("pool receipt changed during snapshot")
            if member not in ("protocol.json", "job.json"):
                entry = next(x for x in receipt["files"] if x["path"] == member)
                if (
                    len(raw) != entry["bytes"]
                    or hashlib.sha256(raw).hexdigest() != entry["sha256"]
                ):
                    raise ValueError("pool match changed during snapshot")
            files[key] = raw
        games += len(rows)
        counts[cohort] += len(rows)
        complete += int(receipt["complete"])
        present.append(name)
    if not games:
        raise ValueError("empty committed pool is not an evaluation dataset")
    return {
        "games": games,
        "target_games": expected_plan["games"],
        "completed_jobs": complete,
        "jobs_present": present,
        "games_by_cohort": counts,
        "runtime_by_cohort": runtimes,
        "launch_observations": launches,
        "files": files,
    }


def _owner(value):
    if (
        type(value) is not dict
        or set(value) != {"provider", "instance_id", "tag"}
        or value["provider"] != "vast.ai"
        or type(value["instance_id"]) is not int
        or value["instance_id"] <= 0
        or not isinstance(value["tag"], str)
        or not re.fullmatch(r"voxelshogi-phase5-[a-z0-9-]+", value["tag"])
    ):
        raise ValueError("explicit owned evaluation instance required")
    return value


def pack_pool(folder, output, *, expected_plan, owner):
    _linux()
    import pyarrow as pa
    import pyarrow.parquet as pq

    _owner(owner)
    validate_case_plan(expected_plan)
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    with _lease(Path(folder)), ExitStack() as leases:
        for job in expected_plan["jobs"]:
            leases.enter_context(_lease(Path(folder) / "jobs" / job["job_id"]))
        collected = collect_pool(folder, expected_plan)
        records = [
            {"path": key, "data": raw}
            for key, raw in sorted(collected.pop("files").items())
        ]
        output.mkdir(parents=True, exist_ok=False)
        table = pa.Table.from_pylist(
            records, schema=pa.schema([("path", pa.string()), ("data", pa.binary())])
        )
        data = output / "pool.parquet"
        pq.write_table(table, data, compression="zstd")
        if pq.read_table(data).to_pylist() != records:
            raise ValueError("pool Parquet roundtrip differs")
        manifest = {
            "schema": SCHEMA,
            "source_commit": expected_plan["jobs"][0]["protocol"]["source_commit"],
            "owner": owner,
            "plan_sha256": fingerprint(expected_plan),
            "pipeline_complete": False,
            "rust_replayed_all_committed_games": True,
            **collected,
            "members": [
                {
                    "path": r["path"],
                    "bytes": len(r["data"]),
                    "sha256": hashlib.sha256(r["data"]).hexdigest(),
                }
                for r in records
            ],
            "files": [
                {
                    "path": "pool.parquet",
                    "bytes": data.stat().st_size,
                    "sha256": file_hash(data),
                }
            ],
            "scope": "stopped committed case prefixes only; full input audit and final cohort aggregation are separate; parent PID observations are historical",
        }
        atomic_json(output / "manifest.json", manifest)
        atomic_json(
            output / "validation.json",
            {
                "roundtrip_verified": True,
                "rust_replayed_all_committed_games": True,
                "games": collected["games"],
                "target_games": collected["target_games"],
                "pipeline_complete": False,
            },
        )
        return manifest


def _materialize(files, folder):
    for name, raw in files.items():
        path = Path(folder) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    for name in ("jobs", "protocols", "launches", "logs", "cohorts"):
        (Path(folder) / name).mkdir(exist_ok=True)


def read_pool_archive(folder, *, expected_plan):
    _linux()
    import pyarrow.parquet as pq

    cohorts = validate_case_plan(expected_plan)
    folder = Path(folder)
    manifest = json.loads(_read(folder / "manifest.json"))
    if (
        manifest.get("schema") != SCHEMA
        or manifest.get("source_commit")
        != expected_plan["jobs"][0]["protocol"]["source_commit"]
        or manifest.get("plan_sha256") != fingerprint(expected_plan)
        or manifest.get("pipeline_complete") is not False
        or manifest.get("rust_replayed_all_committed_games") is not True
    ):
        raise ValueError("pool archive plan/completion binding differs")
    _owner(manifest["owner"])
    data = folder / "pool.parquet"
    expected_file = [
        {
            "path": "pool.parquet",
            "bytes": data.stat().st_size,
            "sha256": file_hash(data),
        }
    ]
    if (
        data.is_symlink()
        or manifest.get("files") != expected_file
        or data.stat().st_size > 256 * 1024**2
    ):
        raise ValueError("pool archive data hash/size differs")
    allowed = {
        "plan.json",
        "artifacts.json",
        *("protocols/" + n + ".json" for n in cohorts),
    }
    for job in expected_plan["jobs"]:
        prefix = "jobs/" + job["job_id"] + "/"
        allowed.update(
            prefix + n
            for n in (
                "protocol.json",
                "job.json",
                job["case_id"] + "-b.json",
                job["case_id"] + "-w.json",
            )
        )
    records = pq.read_table(data).to_pylist()
    files = {}
    for row in records:
        if (
            set(row) != {"path", "data"}
            or row["path"] not in allowed
            or row["path"] in files
            or type(row["data"]) is not bytes
            or len(row["data"]) > 32 * 1024**2
        ):
            raise ValueError("foreign, duplicate or oversized archive member")
        files[row["path"]] = row["data"]
    descriptors = [
        {"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        for name, raw in sorted(files.items())
    ]
    if manifest.get("members") != descriptors:
        raise ValueError("archive member bytes/hash differ")
    with tempfile.TemporaryDirectory(prefix="voxelshogi-pool-verify-") as temp:
        _materialize(files, temp)
        collected = collect_pool(temp, expected_plan)
        for key in (
            "games",
            "target_games",
            "completed_jobs",
            "jobs_present",
            "games_by_cohort",
            "runtime_by_cohort",
        ):
            if manifest.get(key) != collected[key]:
                raise ValueError("archive declared coverage/runtime differs")
    return manifest, files


def restore_pool(
    folder, output, *, expected_plan, artifacts, parent_release, current_owner
):
    _linux()
    _owner(current_owner)
    header = json.loads(_read(Path(folder) / "manifest.json"))
    previous = _owner(header["owner"])
    if (
        type(parent_release) is not dict
        or parent_release.get("owner") != previous
        or parent_release.get("destruction_acknowledged") is not True
        or parent_release.get("inventory_absent") is not True
        or not isinstance(parent_release.get("evidence_sha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", parent_release["evidence_sha256"])
        or current_owner["instance_id"] == previous["instance_id"]
    ):
        raise ValueError(
            "verified released parent and a different owned instance required"
        )
    cohorts = validate_case_plan(expected_plan)
    _artifacts(cohorts, artifacts)
    manifest, files = read_pool_archive(folder, expected_plan=expected_plan)
    for name, runtime in manifest["runtime_by_cohort"].items():
        _, required, commit = checked_execution(cohorts[name], artifacts[name])
        if execution_runtime(cohorts[name], required, commit) != runtime:
            raise ValueError("restored cohort runtime differs before any new games")
    output = Path(output)
    with _lease(output):
        output.mkdir(exist_ok=False)
        _materialize(files, output)
        atomic_json(output / "artifacts.json", artifacts)
        restoration = {
            "schema": SCHEMA,
            "archive_manifest_sha256": file_hash(Path(folder) / "manifest.json"),
            "games_restored": manifest["games"],
            "target_games": expected_plan["games"],
            "parent_owner": previous,
            "current_owner": current_owner,
            "parent_release": parent_release,
            "parent_launch_observations": manifest["launch_observations"],
            "scope": "original case bytes restored; historical PIDs are not restored as current process handles; no games rerun",
        }
        atomic_json(output / "restoration.json", restoration)
        return restoration
