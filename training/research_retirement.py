"""Control-side browser-job retirement after collecting terminal evidence.

This watcher neither rents hosts nor contains credentials. The supplied ports
verify the live account/owner, exact worker PID/birth/source, small record
collection and provider destruction acknowledgement. The independent deadline
remains responsible when observation, preservation or termination is uncertain.
"""

import math
import re
import time


def _snapshot(value):
    process = value["process"]
    if (
        type(process.get("running")) is not bool
        or type(process.get("pid")) is not int
        or process["pid"] < 1
        or type(process.get("create_time")) not in (int, float)
        or not math.isfinite(process["create_time"])
        or process["create_time"] <= 0
        or not isinstance(process.get("source_commit"), str)
        or re.fullmatch(r"[0-9a-f]{40}", process["source_commit"]) is None
        or type(value.get("records")) is not dict
    ):
        raise ValueError("missing owned worker identity/status")
    return process


def _preserved(observed, collected):
    process = _snapshot(collected)
    if process["running"] or any(
        process[k] != observed[k] for k in ("pid", "create_time", "source_commit")
    ):
        return None
    records = collected["records"]
    finished = records.get("worker-finished.json", {})
    if type(finished.get("complete")) is not bool:
        return None
    complete = records.get("complete.json", {})
    if finished["complete"]:
        receipt = records.get("publication-receipt.json", {})
        if (
            complete.get("complete") is not True
            or complete.get("source_commit") != process["source_commit"]
            or receipt.get("verified") is not True
            or receipt.get("community_disabled") is not True
            or receipt.get("dry_run") is not False
            or receipt.get("repo_type") != "dataset"
            or receipt.get("repo_id") != "voxelshogi/voxelshogi-research-browser-v1"
            or re.fullmatch(r"[0-9a-f]{40}", str(receipt.get("hub_commit"))) is None
            or re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("release_sha256"))) is None
        ):
            return None
        return True
    failures = [
        records.get(k, {}) for k in ("failure.json", "partial-publication-failure.json")
    ]
    if complete or not any(
        f.get("complete") is False
        and isinstance(f.get("error_type"), str)
        and f["error_type"]
        for f in failures
    ):
        return None
    # Operator-only measurements/diagnosis are reproducible from fixed inputs;
    # a retained failure is not an unpublished model/checkpoint to discard.
    return False


def watch_browser(
    observe,
    collect,
    retire,
    *,
    deadline,
    clock=time.time,
    wait=time.sleep,
    save=lambda _: None,
    stop_requested=lambda: False,
):
    if type(deadline) not in (int, float) or not math.isfinite(deadline):
        raise ValueError("fixed independent retirement deadline required")
    while not stop_requested() and clock() < deadline:
        current = observe()
        process = _snapshot(current)
        if process["running"] or "worker-finished.json" not in current["records"]:
            wait(min(60, max(0, deadline - clock())))
            continue
        collected = collect()
        complete = _preserved(process, collected)
        if complete is None:
            result = {
                "event": "preservation-incomplete",
                "resources_released": False,
                "independent_guard_required": True,
            }
            save(result)
            return result
        save(
            {
                "event": "evidence-preserved",
                "job_complete": complete,
                "pid": process["pid"],
                "source_commit": process["source_commit"],
            }
        )
        # One request only. The ownership-aware retirement port independently
        # checks account/label and both acknowledgement and inventory absence.
        retirement = retire()
        result = {
            "event": "retirement-result",
            "job_complete": complete,
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
