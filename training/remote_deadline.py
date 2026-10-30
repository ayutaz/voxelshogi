"""CloudRift termination on an independent, protected-main Actions runner.

This is a second control process, not a provider-enforced lease expiry. Provider
or Actions failures can still delay termination; never claim a hard spend cap.
"""

import argparse
import json
import os
import re
import signal
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from training.rental_control import TERMINAL, NoRedirect, save

WORKFLOW = ".github/workflows/gpu-deadline.yml"
REPOSITORY = "ayutaz/voxelshogi"


@dataclass(frozen=True)
class Deadline:
    tag: str
    maximum_end_at: int

    def validate(self, *, now=None):
        if (
            not isinstance(self.tag, str)
            or re.fullmatch(r"voxelshogi-phase[56]-[a-z0-9][a-z0-9-]{0,79}", self.tag)
            is None
            or type(self.maximum_end_at) is not int
        ):
            raise ValueError("invalid remote deadline identity")
        if now is not None and not 1800 <= self.maximum_end_at - now <= 14400:
            raise ValueError("remote deadline outside bounded window")

    @property
    def stop_at(self):
        return self.maximum_end_at - 900


def owned(spec, api):
    rows = api(
        "/api/v1/instances/list",
        {
            "selector": {"ByTags": {"all": [spec.tag], "any": []}},
            "mask": {"with_usage_info": False, "with_credentials": False},
        },
    )["instances"]
    if any(spec.tag not in row.get("tags", []) or not row.get("id") for row in rows):
        raise ValueError("remote guard ownership mismatch")
    return rows


def arm(spec, api, *, clock=time.time):
    now = clock()
    spec.validate(now=now)
    if owned(spec, api):
        raise ValueError("tag already exists; use a fresh rental identity")
    return {"tag": spec.tag, "maximum_end_at": spec.maximum_end_at, "armed_at": now}


def watch(spec, api, *, clock=time.time, pause=time.sleep, stopping=lambda: False):
    spec.validate()
    seen = set()
    while True:
        now = clock()
        try:
            rows = owned(spec, api)
            seen.update(row["id"] for row in rows)
            present = {row["id"] for row in rows}
            if (
                seen
                and present == seen
                and all(
                    row["status"] in TERMINAL and row.get("resources_released") is True
                    for row in rows
                )
            ):
                return {"complete": True, "instance_ids": sorted(seen)}
            if now >= spec.stop_at or stopping():
                active = [row["id"] for row in rows if row["status"] not in TERMINAL]
                if active:
                    api("/api/v1/instances/terminate", {"selector": {"ById": active}})
                    # The successful response alone is not release confirmation.
                if not seen and (now >= spec.maximum_end_at or stopping()):
                    return {
                        "complete": True,
                        "instance_ids": [],
                        "no_rental_observed": True,
                    }
        except RuntimeError:
            # The transport emits no response body or credential-bearing exception.
            print(
                json.dumps({"event": "provider observation unavailable", "at": now}),
                flush=True,
            )
        remaining = spec.stop_at - clock()
        pause(min(60, remaining) if remaining > 0 else 60)


def verify_run(run, jobs, *, tag, now, minimum_seconds):
    match = re.fullmatch(
        r"GPU deadline: ([a-z0-9-]+) @ ([0-9]+)", run.get("display_title", "")
    )
    if (
        run.get("event") != "workflow_dispatch"
        or run.get("head_branch") != "main"
        or run.get("path") != WORKFLOW
        or run.get("status") != "in_progress"
        or match is None
        or match[1] != tag
    ):
        raise ValueError("independent deadline workflow is not running on main")
    spec = Deadline(tag, int(match[2]))
    spec.validate(now=now)
    if spec.maximum_end_at - now < minimum_seconds:
        raise ValueError("independent deadline leaves insufficient workload time")
    candidates = [
        job
        for job in jobs.get("jobs", [])
        if job.get("name") == "Independent CloudRift deadline"
    ]
    if len(candidates) != 1 or candidates[0].get("status") != "in_progress":
        raise ValueError("independent deadline job is not running")
    steps = {step["name"]: step for step in candidates[0].get("steps", [])}
    if (
        steps.get("Arm deadline", {}).get("conclusion") != "success"
        or steps.get("Guard CloudRift deadline", {}).get("status") != "in_progress"
    ):
        raise ValueError("independent deadline provider readiness is unconfirmed")
    return spec


def live_guard(run_id, *, tag, now, minimum_seconds):
    if type(run_id) is not int or run_id <= 0:
        raise ValueError("an actual Actions guard run ID is required")
    base = f"repos/{REPOSITORY}/actions/runs/{run_id}"

    def read(path):
        return json.loads(subprocess.check_output(["gh", "api", path], text=True))

    run = read(base)
    if run.get("id") != run_id:
        raise ValueError("guard run identity differs")
    jobs = read(base + "/jobs?filter=latest&per_page=100")
    return verify_run(run, jobs, tag=tag, now=now, minimum_seconds=minimum_seconds)


def client():
    key = os.environ.get("CLOUDRIFT_API_KEY")
    if not key:
        raise ValueError("CloudRift control secret is missing")
    opener = urllib.request.build_opener(NoRedirect)

    def api(path, data):
        if path not in ("/api/v1/instances/list", "/api/v1/instances/terminate"):
            raise ValueError("remote guard has no rental operation")
        request = urllib.request.Request(
            "https://api.cloudrift.ai" + path,
            data=json.dumps({"version": "2026-09-08", "data": data}).encode(),
            headers={"X-API-Key": key, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with opener.open(request, timeout=40) as response:
                return json.load(response)["data"]
        except urllib.error.URLError, TimeoutError, OSError:
            raise RuntimeError("CloudRift guard request failed") from None

    return api


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("command", choices=("arm", "watch"))
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    # Only the protected, environment-bound manual workflow is a control host.
    if (
        os.environ.get("GITHUB_REPOSITORY") != REPOSITORY
        or os.environ.get("GITHUB_REF") != "refs/heads/main"
        or os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
    ):
        parser.error("remote deadline is restricted to protected main Actions")
    spec = Deadline(os.environ["RENTAL_TAG"], int(os.environ["MAXIMUM_END_AT"]))
    api = client()
    if args.command == "arm":
        if args.state.exists():
            raise ValueError("deadline already armed")
        result = arm(spec, api)
        save(args.state, result)
    else:
        receipt = json.loads(args.state.read_text())
        if (
            receipt["tag"] != spec.tag
            or receipt["maximum_end_at"] != spec.maximum_end_at
        ):
            raise ValueError("armed deadline changed")
        stopping = [False]

        def stop(_signum, _frame):
            stopping[0] = True

        for signum in (signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, stop)
        result = watch(spec, api, stopping=lambda: stopping[0])
    print(json.dumps(result, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
