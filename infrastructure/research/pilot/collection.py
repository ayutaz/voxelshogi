"""External-Linux terminal checkpoint inspection; export bounded metadata only."""

import json
import math
import os
import sys
import time
from pathlib import Path

from infrastructure.research.pilot import job
from infrastructure.research.pilot.results import finite_json, read_owned
from infrastructure.research.pilot.retirement import process_identity
from training.evaluation_v2 import fingerprint
from training.feature_cache import file_hash

RECORDS = (
    "workflow-worker-finished.json",
    "workflow-complete.json",
    "workflow-failure.json",
    "workflow-publication.json",
    "state-budget-final.json",
    "resource-samples-final.json",
    "job-failure.json",
    "output-repositories.json",
    "cuda-preflight.json",
)


def small_json(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > 1024**2:
        raise ValueError("bounded small collection record required")
    return finite_json(read_owned(path).decode("utf-8"))


def inspect_process(expected, base):
    if sys.platform != "linux":
        raise ValueError("owned worker inspection requires external Linux")
    import psutil

    if type(expected.get("pid")) is not int or expected["pid"] <= 0:
        raise ValueError("exact worker launch identity required")
    try:
        worker = psutil.Process(expected["pid"])
        if worker.create_time() != expected["create_time"]:
            raise ValueError("worker PID reused")
        running = worker.is_running() and worker.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        running = False
    root, base = Path.cwd().resolve(), Path(base)
    names = {
        "infrastructure.research.pilot.workflow",
        "infrastructure.research.pilot.job",
        "infrastructure.research.pilot.post",
    }
    attempts = {
        str(root / "infrastructure/research/pilot/attempt.py"),
        "infrastructure/research/pilot/attempt.py",
    }
    owned = []
    for process in psutil.process_iter():
        try:
            if process.pid == os.getpid() or process.status() == psutil.STATUS_ZOMBIE:
                continue
            command = process.cmdline()
            relevant = bool(
                names.intersection(command) or attempts.intersection(command)
            )
            if not relevant:
                continue
            if Path(process.cwd()).resolve() != root:
                continue
            if any(
                arg == str(base)
                or arg.startswith(str(base) + "/")
                or arg.startswith(str(root / base) + "/")
                for arg in command
            ):
                owned.append({"pid": process.pid, "create_time": process.create_time()})
        except psutil.NoSuchProcess:
            continue
    return {
        "process": {**expected, "running": running},
        "owned_compute": sorted(owned, key=lambda p: p["pid"]),
    }


def load_ports():
    from training.checkpoint import checkpoint_receipt
    from training.research_visit_fit import validate_history
    from training.resume_archive import verify_archive

    return {
        "source": job.check_source,
        "process": inspect_process,
        "checkpoint": checkpoint_receipt,
        "archive": verify_archive,
        "history": validate_history,
    }


def _check_files(folder, plan, *, already_verified=()):
    verified = {f["path"]: f for f in already_verified}
    for entry in plan["files"]:
        name = Path(entry["path"])
        if name.is_absolute() or ".." in name.parts or not name.parts:
            raise ValueError("publication path escaped owned folder")
        if entry["path"] in verified:
            if entry != verified[entry["path"]]:
                raise ValueError("state publication descriptor differs from archive")
        else:
            path = folder / name
            if (
                any(p.is_symlink() for p in (path, *path.parents))
                or not path.is_file()
                or path.stat().st_size != entry["bytes"]
                or file_hash(path) != entry["sha256"]
            ):
                raise ValueError("published local artifact bytes changed")


def observe_snapshot(value, expected, *, ports=None):
    if sys.platform != "linux":
        raise ValueError("pilot observation requires external Linux")
    ports = load_ports() if ports is None else ports
    ports["source"](value["job"]["source_commit"])
    status = ports["process"](expected, Path(value["job"]["base"]))
    process_identity(status, expected)
    return status


def collect_snapshot(value, expected, *, deadline, clock=time.time, ports=None):
    if sys.platform != "linux":
        raise ValueError("pilot collection requires external Linux")
    if type(deadline) not in (int, float) or not math.isfinite(deadline):
        raise ValueError("fixed collection deadline required")
    from infrastructure.research.pilot.state_transfer import validate_pilot_binding
    from infrastructure.research.pilot.workflow import validate_workflow

    validate_workflow(value, now=value["job"]["compute_deadline"] - 1)
    ports = load_ports() if ports is None else ports
    if set(ports) != {"source", "process", "checkpoint", "archive", "history"}:
        raise ValueError("complete Linux collection ports required")

    def boundary():
        if clock() >= deadline:
            raise InterruptedError("fixed checkpoint collection deadline")

    boundary()
    base = Path(value["job"]["base"])
    status = observe_snapshot(value, expected, ports=ports)
    if status["process"]["running"] or status["owned_compute"]:
        raise ValueError("owned fitting/worker processes still active")
    records = {
        name: small_json(base / name) for name in RECORDS if (base / name).exists()
    }
    states, transfers, proofs, unknown, unresolved, replicas = {}, {}, {}, [], [], []
    for inputs in value["job"]["inputs"]:
        architecture = inputs["config"]["architecture"]["architecture"]
        folder = base / architecture
        if not folder.exists():
            continue
        if folder.is_symlink():
            raise ValueError("owned architecture folder must be regular")
        for item in sorted(folder.iterdir()):
            boundary()
            if item.is_symlink():
                raise ValueError("symlink in owned pilot output")
            if not item.is_dir():
                continue
            if (item / "run.json").exists():
                if item.name not in ("continuous", "interrupted", "restored"):
                    replicas.append((architecture, item))
                    continue
                saved = small_json(item / "run.json")
                binding = saved["binding"]
                validate_pilot_binding(binding)
                if (
                    binding["source_commit"] != value["job"]["source_commit"]
                    or binding["config"] != inputs["config"]
                ):
                    raise ValueError("owned run differs from frozen model/source")
                selector = small_json(item / "checkpoints/latest.json")
                checkpoints = {}
                for role in (
                    ("latest", "best")
                    if selector.get("best") is not None
                    else ("latest",)
                ):
                    _, receipt = ports["checkpoint"](
                        item / "checkpoints", binding=binding, which=role
                    )
                    checkpoints[role] = {
                        "sha256": receipt["sha256"],
                        "progress": receipt["progress"],
                    }
                raw_events = read_owned(item / "events.jsonl")
                events = [
                    finite_json(line.decode()) for line in raw_events.splitlines()
                ]
                ports["history"](
                    events, binding["config"], checkpoints["latest"]["progress"]
                )
                states[architecture + "/" + item.name] = {
                    "binding": binding,
                    "checkpoints": checkpoints,
                    "history_sha256": fingerprint(events),
                    "history_events": len(events),
                }
            if item.name.endswith("-transfer"):
                stem = item.name.removesuffix("-transfer")
                if stem not in (
                    "intermediate",
                    "final",
                    "failure-rescue-continuous",
                    "failure-rescue-interrupted",
                    "failure-rescue-restored",
                ):
                    unresolved.append(str(item.relative_to(base)))
                    continue
                if not (item / "complete.json").is_file():
                    unresolved.append(str(item.relative_to(base)))
                    continue
                plan, receipt, completed = [
                    small_json(item / (n + ".json"))
                    for n in ("publication-plan", "publication-receipt", "complete")
                ]
                archive = folder / (stem + "-archive")
                manifest = ports["archive"](
                    archive,
                    expected_binding=plan["expected_binding"],
                    profile="research",
                )
                _check_files(archive, plan, already_verified=manifest.get("files", ()))
                if (
                    completed.get("receipt") != receipt
                    or completed.get("restored") is not True
                ):
                    raise ValueError("actual transfer restoration/receipt differs")
                transfers[architecture + "/" + stem] = {
                    "plan": plan,
                    "receipt": receipt,
                    "manifest": manifest,
                    "manifest_sha256": file_hash(archive / "manifest.json"),
                    "archive_verified": True,
                    "restored": True,
                }
        if (folder / "resume-proof.json").exists():
            proofs[architecture] = small_json(folder / "resume-proof.json")
    for architecture, item in replicas:
        stem = (
            "final"
            if item.name == "final-reconstruction"
            else item.name.removesuffix("-reconstruction")
            if item.name.startswith("failure-rescue-")
            and item.name.endswith("-reconstruction")
            else None
        )
        transfer = transfers.get(architecture + "/" + str(stem))
        if transfer is None or not (item / "restoration.json").is_file():
            unknown.append(str(item.relative_to(base)))
            continue
        restoration, saved = (
            small_json(item / "restoration.json"),
            small_json(item / "run.json"),
        )
        manifest = transfer["manifest"]
        if (
            restoration.get("verified") is not True
            or restoration.get("archive_manifest_sha256") != transfer["manifest_sha256"]
            or restoration.get("source_checkpoints")
            != {r: d["source_checkpoint_sha256"] for r, d in manifest["roles"].items()}
            or saved["binding"] != manifest["binding"]
        ):
            unknown.append(str(item.relative_to(base)))
    result, trace = None, None
    if (base / "development/queries.jsonl").exists():
        path = base / "development/queries.jsonl"
        read_owned(path)
        trace = {"bytes": path.stat().st_size, "sha256": file_hash(path)}
    if (base / "results-transfer/complete.json").exists():
        control = base / "results-transfer"
        output = base / "publication"
        plan, receipt, completed = [
            small_json(control / (n + ".json"))
            for n in ("publication-plan", "publication-receipt", "complete")
        ]
        _check_files(output, plan)
        if completed.get("receipt") != receipt:
            raise ValueError("actual result transfer receipt differs")
        result = {
            "plan": plan,
            "receipt": receipt,
            "manifest": small_json(output / "manifest.json"),
            "manifest_sha256": file_hash(output / "manifest.json"),
        }
    boundary()
    final_status = observe_snapshot(value, expected, ports=ports)
    if final_status["process"]["running"] or final_status["owned_compute"]:
        raise ValueError("owned compute changed during collection")
    snapshot = {
        "schema": "voxelshogi-research-pilot-collection-v1",
        "source_commit": value["job"]["source_commit"],
        "workflow_sha256": fingerprint(value),
        **final_status,
        "records": records,
        "run_states": states,
        "state_transfers": transfers,
        "resume_proofs": proofs,
        "unknown_run_paths": unknown,
        "unresolved_transfers": unresolved,
        "state_budget": small_json(base / "state-upload-budget.json"),
        "query_trace": trace,
        "result_publication": result,
    }
    if len(json.dumps(snapshot).encode()) > 4 * 1024**2:
        raise ValueError("collection exceeds small metadata bound")
    return snapshot


def main():
    if sys.platform != "linux":
        raise ValueError("collection RPC requires external Linux")
    payload = sys.stdin.buffer.read(4 * 1024**2 + 1)
    if len(payload) > 4 * 1024**2:
        raise ValueError("oversized collection request")
    request = finite_json(payload.decode())
    value, expected = request["workflow"], request["expected_process"]
    if request["mode"] == "observe":
        result = observe_snapshot(value, expected)
    elif request["mode"] == "collect":
        result = collect_snapshot(value, expected, deadline=request["deadline"])
    else:
        raise ValueError("unknown collection operation")
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        print(
            json.dumps(
                {"collection_complete": False, "error_type": type(error).__name__}
            ),
            flush=True,
        )
        sys.exit(1)
