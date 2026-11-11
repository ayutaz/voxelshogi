"""Controller preservation checks for actual M pilots; never rent or discard state."""

import math
import re
import time

from training.evaluation_v2 import fingerprint
from training.hub_release import _policy
from training.research_visit_fit import validate_binding
from training.state_upload_budget import upload_budget_limit


def _sha(value, length=64):
    return (
        isinstance(value, str)
        and re.fullmatch(f"[0-9a-f]{{{length}}}", value) is not None
    )


def process_identity(snapshot, expected):
    process = snapshot["process"]
    if (
        type(process.get("running")) is not bool
        or type(process.get("pid")) is not int
        or process["pid"] <= 0
        or type(process.get("create_time")) not in (int, float)
        or not math.isfinite(process["create_time"])
        or any(
            process.get(k) != expected[k]
            for k in ("pid", "create_time", "source_commit")
        )
    ):
        raise ValueError("owned worker PID/birth/source differs")
    return process


def checked_publication(item, *, source, repo, kind, state=False):
    plan, receipt = item["plan"], item["receipt"]
    _policy(plan)
    if (
        plan["source_commit"] != source
        or plan["repo_id"] != repo
        or plan["repo_type"] != kind
        or receipt.get("repo_id") != repo
        or receipt.get("repo_type") != kind
        or receipt.get("verified") is not True
        or receipt.get("community_disabled") is not True
        or receipt.get("dry_run") is not False
        or not _sha(receipt.get("hub_commit"), 40)
        or receipt.get("release_sha256") != fingerprint(plan)
        or not plan["files"]
    ):
        raise ValueError("immutable verified publication differs")
    if state and (
        plan.get("artifact_role") != "research-training-state"
        or plan["license"] != "apache-2.0"
        or item.get("archive_verified") is not True
        or item.get("restored") is not True
    ):
        raise ValueError("typed research archive verification/restoration required")
    names = []
    for entry in plan["files"]:
        from pathlib import PurePosixPath

        name = PurePosixPath(entry["path"])
        if (
            name.is_absolute()
            or ".." in name.parts
            or not name.parts
            or type(entry["bytes"]) is not int
            or entry["bytes"] <= 0
            or not _sha(entry["sha256"])
        ):
            raise ValueError("invalid publication inventory")
        names.append(entry["path"])
    if len(set(names)) != len(names):
        raise ValueError("duplicate publication inventory")
    return plan, receipt


def _parity(name, proof, states, inputs):
    continuous, restored = (
        states.get(name + "/continuous"),
        states.get(name + "/restored"),
    )
    if continuous is None or restored is None:
        return False
    if (
        proof.get("schema") != "voxelshogi-research-pilot-cuda-resume-proof-v1"
        or proof.get("verified") is not True
        or proof.get("source_commit") != inputs["source_commit"]
        or proof.get("total_updates") != inputs["config"]["total_updates"]
        or continuous["binding"] != restored["binding"]
        or proof.get("binding_sha256") != fingerprint(continuous["binding"])
        or proof.get("history_sha256") != continuous["history_sha256"]
        or proof.get("history_sha256") != restored["history_sha256"]
        or proof.get("history_events") != continuous["history_events"]
        or proof.get("history_events") != restored["history_events"]
    ):
        return False
    for role in ("latest", "best"):
        p = proof.get("checkpoints", {}).get(role, {})
        left, right = (
            continuous["checkpoints"].get(role, {}),
            restored["checkpoints"].get(role, {}),
        )
        if (
            p.get("exact_equal") is not True
            or type(p.get("compared", {}).get("tensors")) is not int
            or p["compared"]["tensors"] <= 0
            or not left
            or not right
            or p.get("progress") != left["progress"]
            or p.get("progress") != right["progress"]
            or p.get("state_sha256") != [left["sha256"], right["sha256"]]
        ):
            return False
    return (
        continuous["checkpoints"]["latest"]["progress"]["step"]
        == inputs["config"]["total_updates"]
    )


def review_collection(value, snapshot, *, expected_process, initial_budget):
    """Require every current original checkpoint to be covered, including failures."""
    source = value["job"]["source_commit"]
    process = process_identity(snapshot, expected_process)
    if (
        snapshot.get("schema") != "voxelshogi-research-pilot-collection-v1"
        or snapshot.get("source_commit") != source
        or snapshot.get("workflow_sha256") != fingerprint(value)
        or process.get("source_commit") != source
        or process["running"]
        or snapshot.get("owned_compute") != []
        or snapshot.get("unknown_run_paths") != []
        or snapshot.get("unresolved_transfers", []) != []
    ):
        raise ValueError("terminal owned workflow and all compute must be observed")
    records, states, transfers = (
        snapshot["records"],
        snapshot["run_states"],
        snapshot["state_transfers"],
    )
    finished = records.get("workflow-worker-finished.json", {})
    if (
        type(finished.get("pipeline_complete")) is not bool
        or finished.get("source_commit") != source
        or finished.get("observer_stopped") is not True
    ):
        raise ValueError("terminal worker/observer evidence required")
    complete = finished["pipeline_complete"]
    final = snapshot["state_budget"]
    upload_budget_limit(initial_budget)
    upload_budget_limit(final)
    if (
        {k: v for k, v in initial_budget.items() if k != "reservations"}
        != {k: v for k, v in final.items() if k != "reservations"}
        or final["reservations"][: len(initial_budget["reservations"])]
        != initial_budget["reservations"]
        or records.get("state-budget-final.json") != final
    ):
        raise ValueError("collected state ledger history/cap differs")
    inputs_by_name = {
        i["config"]["architecture"]["architecture"]: i for i in value["job"]["inputs"]
    }
    permitted = {
        name + "/" + run
        for name in ("full", "geometry")
        for run in ("continuous", "interrupted", "restored")
    }
    if set(states) - permitted or complete and set(states) != permitted:
        raise ValueError("current fitted-run inventory differs")
    for name, state in states.items():
        inputs = inputs_by_name[name.split("/")[0]]
        binding = state["binding"]
        validate_binding(binding)
        if (
            binding["source_commit"] != source
            or binding["config"] != inputs["config"]
            or binding["contract"]["admission_sha256"] != inputs["admission_sha256"]
            or not {"latest"} <= set(state["checkpoints"]) <= {"latest", "best"}
            or not _sha(state["history_sha256"])
            or type(state["history_events"]) is not int
            or state["history_events"] < 0
            or any(not _sha(c["sha256"]) for c in state["checkpoints"].values())
        ):
            raise ValueError("current M checkpoint binding differs")
    archives, reservations = [], {}
    for item in transfers.values():
        plan, receipt = checked_publication(
            item,
            source=source,
            repo="voxelshogi/voxelshogi-research-training-state-v1",
            kind="model",
            state=True,
        )
        manifest = item["manifest"]
        if (
            manifest.get("schema") != "voxelshogi-research-resume-archive-v1"
            or manifest.get("purpose") != "resume-state"
            or manifest.get("complete") is not True
            or manifest["binding"] != plan["expected_binding"]
            or not {"latest"} <= set(manifest["roles"]) <= {"latest", "best"}
            or not any(
                f["path"] == "manifest.json" and f["sha256"] == item["manifest_sha256"]
                for f in plan["files"]
            )
        ):
            raise ValueError("actual verified archive manifest differs")
        archives.append(manifest)
        reservations[receipt["release_sha256"]] = sum(f["bytes"] for f in plan["files"])
    for row in final["reservations"][len(initial_budget["reservations"]) :]:
        if reservations.get(row["release_sha256"]) != row["maximum_bytes"]:
            raise ValueError("new state reservation lacks a verified transfer")
    for release, amount in reservations.items():
        if {"release_sha256": release, "maximum_bytes": amount} not in final[
            "reservations"
        ]:
            raise ValueError("verified state transfer missing from collected ledger")
    covered = set()
    for name, state in states.items():
        if any(
            a["binding"] == state["binding"]
            and set(a["roles"]) == set(state["checkpoints"])
            and all(
                a["roles"][r]["source_checkpoint_sha256"] == c["sha256"]
                and a["roles"][r]["progress"] == c["progress"]
                for r, c in state["checkpoints"].items()
            )
            for a in archives
        ):
            covered.add(name)
    for name, inputs in inputs_by_name.items():
        parity = _parity(name, snapshot["resume_proofs"].get(name, {}), states, inputs)
        if parity and name + "/continuous" in covered:
            covered.add(name + "/restored")
        if complete and not parity:
            raise ValueError("full CUDA continuation proof differs")
    if covered != set(states):
        raise ValueError("current checkpoint states remain unpreserved")
    trace = snapshot.get("query_trace")
    publication = snapshot.get("result_publication")
    if complete or trace and trace["bytes"] > 0:
        if publication is None:
            raise ValueError("actual NN trace/results must be published")
        plan, receipt = checked_publication(
            publication,
            source=source,
            repo="voxelshogi/voxelshogi-research-pilot-results-v1",
            kind="dataset",
        )
        manifest = publication["manifest"]
        if (
            not any(
                f["path"] == "records.parquet"
                and f["sha256"] == manifest["records_parquet_sha256"]
                for f in plan["files"]
            )
            or manifest.get("pipeline_complete") is not complete
        ):
            raise ValueError("result dataset completion/hash differs")
        if (
            trace
            and trace["bytes"] > 0
            and not any(
                f["path"] == "development/queries.jsonl"
                and f["sha256"] == trace["sha256"]
                and f["bytes"] == trace["bytes"]
                for f in manifest["files"]
            )
        ):
            raise ValueError("current NN trace differs from published result")
    if complete:
        done = records.get("workflow-complete.json", {})
        if (
            done.get("pipeline_complete") is not True
            or done.get("source_commit") != source
            or done.get("workflow_sha256") != fingerprint(value)
            or done.get("scientific_pilots") != 2
            or done.get("games") != 48
            or done.get("state_budget_final_sha256") != fingerprint(final)
            or done.get("publication", {}).get("receipt") != publication["receipt"]
        ):
            raise ValueError("complete workflow result/ledger differs")
    elif (
        records.get("workflow-complete.json")
        or records.get("workflow-failure.json", {}).get("pipeline_complete")
        is not False
        or not records["workflow-failure.json"].get("error_type")
    ):
        raise ValueError("retained terminal failure record required")
    return {
        "job_complete": complete,
        "covered_runs": sorted(covered),
        "collection_sha256": fingerprint(snapshot),
        "state_budget_sha256": fingerprint(final),
        "phase6_complete": False,
    }


def watch_pilot(
    value,
    *,
    expected_process,
    initial_budget,
    observe,
    collect,
    persist,
    retire,
    deadline,
    clock=time.time,
    wait=time.sleep,
    save=lambda _: None,
    stop_requested=lambda: False,
):
    if type(deadline) not in (int, float) or not math.isfinite(deadline):
        raise ValueError("fixed controller retirement deadline required")
    while not stop_requested() and clock() < deadline:
        observed = observe()
        process = process_identity(observed, expected_process)
        if process["running"] or observed.get("owned_compute"):
            wait(min(60, max(0, deadline - clock())))
            continue
        snapshot = collect()
        try:
            review = review_collection(
                value,
                snapshot,
                expected_process=expected_process,
                initial_budget=initial_budget,
            )
        except ValueError as error:
            result = {
                "event": "preservation-incomplete",
                "resources_released": False,
                "independent_guard_required": True,
                "error_type": type(error).__name__,
            }
            save(result)
            return result
        stored = persist(snapshot, review)
        if (
            stored.get("verified") is not True
            or stored.get("collection_sha256") != review["collection_sha256"]
            or stored.get("state_budget_sha256") != review["state_budget_sha256"]
        ):
            raise ValueError("durable collection/ledger receipt differs")
        save({"event": "evidence-and-ledger-preserved", **review})
        retirement = retire()
        result = {
            "event": "retirement-result",
            "job_complete": review["job_complete"],
            "resources_released": retirement.get("complete") is True
            and retirement.get("instances") == [],
            "retirement": retirement,
        }
        save(result)
        return result
    result = {
        "event": "independent-guard-required",
        "resources_released": False,
        "independent_guard_required": True,
    }
    save(result)
    return result


def persist_collection(control, shared_budget, value, snapshot, review):
    """Collect only small metadata and fsync the shared ledger before deletion.

    Same-file flock matches reserve_state_upload; an acknowledged earlier write
    can be reconciled, while any third-party ledger update stops this operation.
    """
    import fcntl
    import json
    import os
    from pathlib import Path

    from infrastructure.research.pilot.results import read_owned
    from training.checkpoint import atomic_json
    from training.feature_cache import file_hash

    control, shared_budget = Path(control), Path(shared_budget)
    initial_path = control / "state-upload-budget-initial.json"
    if file_hash(initial_path) != value["job"]["state_upload_budget_sha256"]:
        raise ValueError("original frozen ledger bytes differ")
    initial = json.loads(read_owned(initial_path))
    expected = json.loads(read_owned(control / "job-launch.json"))
    actual = review_collection(
        value, snapshot, expected_process=expected, initial_budget=initial
    )
    if actual != review:
        raise ValueError("collection changed before persistence")
    serialized = json.dumps(
        snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    if len(serialized.encode()) > 4 * 1024**2:
        raise ValueError("collection is not small controller metadata")
    collected = control / "collection.json"
    if collected.exists() and json.loads(read_owned(collected)) != snapshot:
        raise ValueError("existing collection differs; reconcile without overwriting")
    atomic_json(collected, snapshot)
    atomic_json(control / "collection-review.json", review)
    if (
        any(p.is_symlink() for p in (shared_budget, *shared_budget.parents))
        or not shared_budget.is_file()
        or shared_budget.stat().st_size > 1024**2
    ):
        raise ValueError("bounded regular shared state ledger required")
    final = snapshot["state_budget"]
    with shared_budget.open("r+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        current = json.load(stream)
        upload_budget_limit(current)
        if current != initial and current != final:
            raise ValueError("shared state ledger changed independently")
        if current != final:
            stream.seek(0)
            json.dump(final, stream, indent=2)
            stream.truncate()
            stream.flush()
            os.fsync(stream.fileno())
        stream.seek(0)
        if json.load(stream) != final:
            raise ValueError("shared state ledger readback differs")
    receipt = {
        "verified": True,
        "collection_sha256": review["collection_sha256"],
        "state_budget_sha256": review["state_budget_sha256"],
        "shared_ledger_file_sha256": file_hash(shared_budget),
        "source_commit": value["job"]["source_commit"],
    }
    atomic_json(control / "collection-receipt.json", receipt)
    return receipt
