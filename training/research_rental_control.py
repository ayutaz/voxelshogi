"""Phase5/6 small single-GPU rentals inside the existing project budget.

No provider access happens at import. Multi-GPU jobs and conditional extra-budget
activation require measured quotes and a separate extension of this controller.
"""

import fcntl
import hashlib
import json
import math
import os
import re
import subprocess
from pathlib import Path

from training.rental_control import (
    DC,
    M6_SHARED_DC,
    M6_SHARED_SKU,
    QUOTES,
    Rental,
    save,
)

ROOT = Path(__file__).resolve().parents[1]
ALLOCATIONS = {"phase5": 20, "phase6": 19}
PURPOSES = {
    "phase5-evaluation",
    "phase5-data",
    "phase5-selfplay",
    "phase5-distributed",
    "phase6-operators",
    "phase6-training",
    "phase6-publication",
}


def _source_check(commit):
    actual = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True
    )
    if actual != commit or dirty:
        raise ValueError("research rental requires its workload's clean source commit")


class ResearchRental(Rental):
    def __init__(
        self,
        *args,
        plan=None,
        workload=None,
        phase="phase5",
        other_provider_idle=None,
        source_check=_source_check,
        remote_guard=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.plan = Path(plan) if plan is not None else None
        self.workload = Path(workload) if workload is not None else None
        self.phase = phase
        self.other_provider_idle = other_provider_idle
        self.source_check = source_check
        self._plan_sha256 = None
        self.remote_guard = remote_guard
        self._remote_deadline = None

    def read_plan(self):
        if (
            self.plan is None
            or self.plan.is_symlink()
            or not self.plan.is_file()
            or self.plan.stat().st_size > 65536
        ):
            raise ValueError("research requires a dedicated rental plan")
        raw = self.plan.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if self._plan_sha256 is not None and digest != self._plan_sha256:
            raise ValueError("research rental plan changed")
        plan = json.loads(raw)
        if (
            set(plan)
            != {
                "schema",
                "purpose",
                "source_commit",
                "workload_sha256",
                "sku",
                "datacenter",
                "with_public_ip",
                "maximum_seconds",
                "maximum_hourly_usd",
                "maximum_usd",
                "estimated_seconds",
            }
            or plan["schema"] != "voxelshogi-research-rental-plan-v1"
            or self.phase not in ALLOCATIONS
            or plan["purpose"] not in PURPOSES
            or not plan["purpose"].startswith(self.phase + "-")
            or not self.tag.startswith("voxelshogi-" + self.phase + "-")
            or not isinstance(plan["source_commit"], str)
            or re.fullmatch(r"[0-9a-f]{40}", plan["source_commit"]) is None
            or not isinstance(plan["workload_sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", plan["workload_sha256"]) is None
            or type(plan["maximum_seconds"]) is not int
            or not 1800 <= plan["maximum_seconds"] <= 14400
            or type(plan["maximum_hourly_usd"]) not in (int, float)
            or plan["maximum_hourly_usd"] != 1
            or type(plan["maximum_usd"]) not in (int, float)
            or plan["maximum_usd"] != plan["maximum_seconds"] / 3600
            or type(plan["estimated_seconds"]) is not int
            or not 0 < plan["estimated_seconds"] <= plan["maximum_seconds"] - 900
        ):
            raise ValueError("invalid research purpose, estimate, or budget plan")
        shared = plan["sku"] == M6_SHARED_SKU
        if (
            plan["sku"] not in (*QUOTES, M6_SHARED_SKU)
            or plan["datacenter"] != (M6_SHARED_DC if shared else DC)
            or type(plan["with_public_ip"]) is not bool
            or plan["with_public_ip"] != (not shared)
        ):
            raise ValueError(
                "research hardware/location/IP differs from quoted configuration"
            )
        if (
            self.workload is None
            or self.workload.is_symlink()
            or not self.workload.is_file()
            or self.workload.stat().st_size > 16 * 1024 * 1024
            or hashlib.sha256(self.workload.read_bytes()).hexdigest()
            != plan["workload_sha256"]
            or json.loads(self.workload.read_text()).get("source_commit")
            != plan["source_commit"]
        ):
            raise ValueError("research workload/source hash differs")
        self._plan_sha256 = digest
        self.sku = plan["sku"]
        return plan

    def quote_seconds(self):
        seconds = self.read_plan()["maximum_seconds"]
        if self._remote_deadline is not None:
            seconds = min(seconds, int(self._remote_deadline - self.clock()) - 60)
        if seconds < 900:
            raise ValueError("independent deadline has expired")
        return seconds

    def configuration(self):
        plan = self.read_plan()
        return {
            "skus": (*QUOTES, M6_SHARED_SKU),
            "datacenter": plan["datacenter"],
            "with_public_ip": plan["with_public_ip"],
        }

    def rent(self, start_guard):
        plan = self.read_plan()
        self.source_check(plan["source_commit"])
        if self.remote_guard is None:
            raise ValueError("a live independent deadline guard is required")
        spec = self.remote_guard(
            tag=self.tag,
            now=self.clock(),
            minimum_seconds=plan["estimated_seconds"] + 960,
        )
        spec.validate(now=self.clock())
        if (
            spec.tag != self.tag
            or spec.maximum_end_at - self.clock() < plan["estimated_seconds"] + 960
        ):
            raise ValueError("independent deadline identity or remaining time differs")
        self._remote_deadline = spec.maximum_end_at
        if self.other_provider_idle is None:
            raise ValueError("cross-provider ownership check is required")
        self.other_provider_idle()
        return super().rent(start_guard)

    def reserve(self):
        plan = self.read_plan()
        cap = plan["maximum_usd"]
        with self.budget.open("r+") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            ledger = json.load(stream)
            rows = ledger.get("reservations")
            if (
                ledger.get("approved_total_usd") != 100
                or not isinstance(rows, list)
                or any(
                    not isinstance(row, dict)
                    or type(row.get("maximum_usd")) not in (int, float)
                    or not math.isfinite(row["maximum_usd"])
                    or row["maximum_usd"] < 0
                    for row in rows
                )
            ):
                raise ValueError("invalid shared project budget")
            reserved = sum(row["maximum_usd"] for row in rows)
            phase_reserved = sum(
                row["maximum_usd"]
                for row in rows
                if str(row.get("task", "")).startswith(self.phase + "-")
            )
            if (
                reserved + cap > 100
                or phase_reserved + cap > ALLOCATIONS[self.phase]
                or any(row.get("tag") == self.tag for row in rows)
            ):
                raise ValueError(
                    "research phase/project budget exceeded or tag already reserved"
                )
            rows.append(
                {
                    "task": plan["purpose"],
                    "tag": self.tag,
                    "maximum_usd": cap,
                    "maximum_seconds": plan["maximum_seconds"],
                    "plan_sha256": self._plan_sha256,
                    "workload_sha256": plan["workload_sha256"],
                    "state": "reserved; invoice not retrieved",
                }
            )
            ledger.update(
                reserved_total_usd=reserved + cap,
                remaining_unreserved_usd=100 - reserved - cap,
            )
            stream.seek(0)
            json.dump(ledger, stream, indent=2)
            stream.truncate()
            stream.flush()
            os.fsync(stream.fileno())
        save(
            self.state / "research-purpose.json",
            {"phase": self.phase, "plan": plan, "plan_sha256": self._plan_sha256},
        )


def guard_command(state, budget, *, phase):
    import sys

    return [
        sys.executable,
        "-m",
        "training.research_rental_control",
        str(state),
        "guard",
        "--budget",
        str(budget),
        "--phase",
        phase,
        "--ready-file",
        str(Path(state) / "guardian-ready.json"),
    ]


def main():
    import argparse
    import time
    import urllib.error
    import urllib.request

    from training.rental_control import NoRedirect, wait_for_guard
    from training.vast_rental_control import VastClient, instance_inventory, project_key

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", type=Path)
    parser.add_argument("command", choices=("rent", "status", "terminate", "guard"))
    parser.add_argument("--phase", choices=tuple(ALLOCATIONS), default="phase5")
    parser.add_argument(
        "--budget", type=Path, default=ROOT / "runs/m4/cost-budget.json"
    )
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--workload", type=Path)
    parser.add_argument("--ready-file", type=Path)
    parser.add_argument("--guard-run", type=int)
    args = parser.parse_args()
    state, budget = args.state.resolve(), args.budget.resolve()
    if (
        not state.is_relative_to(ROOT / "runs")
        or not re.fullmatch(r"[a-z0-9-]+", state.name)
        or not budget.is_relative_to(ROOT / "runs")
    ):
        parser.error("dedicated control state and shared budget under runs/ required")
    if args.command == "rent" and (args.plan is None or args.workload is None):
        parser.error("rent requires --plan and --workload")
    for path in (args.plan, args.workload):
        if path is not None and (
            path.is_symlink() or not path.resolve().is_relative_to(ROOT / "runs")
        ):
            parser.error("research plan/workload must be regular files under runs/")
    if args.command == "rent" and args.guard_run is None:
        parser.error("rent requires --guard-run from the independent main workflow")
    key = project_key(ROOT, "CLOUDRIFT_API_KEY")
    opener = urllib.request.build_opener(NoRedirect)

    def api(path, data):
        if not re.fullmatch(r"/api/v1/[a-z0-9/_-]+", path):
            raise ValueError("invalid official CloudRift API path")
        request = urllib.request.Request(
            "https://api.cloudrift.ai" + path,
            data=json.dumps({"version": "2026-09-08", "data": data}).encode(),
            headers={"X-API-Key": key, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with opener.open(request, timeout=40) as response:
                return json.load(response)["data"]
        except urllib.error.HTTPError as error:
            raise RuntimeError("CloudRift HTTP " + str(error.code)) from None

    def other_provider_idle():
        rows = instance_inventory(VastClient(project_key(ROOT, "VAST_API_KEY")))
        if any(str(row.get("label") or "").startswith("voxelshogi-") for row in rows):
            raise ValueError("existing Vast.ai VoxelShogi rental requires audit")

    tag = "voxelshogi-" + args.phase + "-" + state.name
    from training.remote_deadline import live_guard

    control = ResearchRental(
        state,
        api,
        tag=tag,
        budget=budget,
        phase=args.phase,
        plan=args.plan,
        workload=args.workload,
        other_provider_idle=other_provider_idle,
        remote_guard=lambda **kwargs: live_guard(args.guard_run, **kwargs),
    )

    def start_guard():
        ready = state / "guardian-ready.json"
        ready.unlink(missing_ok=True)
        with (state / "guardian.log").open("a") as log:
            child = subprocess.Popen(
                guard_command(state, budget, phase=args.phase),
                stdout=log,
                stderr=log,
                stdin=subprocess.DEVNULL,
                cwd=ROOT,
                start_new_session=True,
            )
        try:
            wait_for_guard(
                ready,
                child,
                tag=tag,
                deadline_sha256=hashlib.sha256(
                    (state / "deadline.json").read_bytes()
                ).hexdigest(),
            )
        except Exception:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
            raise
        save(state / "guardian.json", {"pid": child.pid, "at": time.time()})

    if args.command == "rent":
        result = control.rent(start_guard)
    elif args.command == "guard":
        if args.ready_file is not None:
            if args.ready_file.resolve() != state / "guardian-ready.json":
                parser.error("guardian ready file must belong to control state")
            raw = (state / "deadline.json").read_bytes()
            limits = json.loads(raw)
            if (
                any(
                    type(limits.get(k)) not in (int, float)
                    or not math.isfinite(limits[k])
                    for k in ("stop_at", "maximum_end_at")
                )
                or limits["maximum_end_at"] <= limits["stop_at"]
            ):
                raise ValueError("invalid research guardian deadline")
            save(
                args.ready_file,
                {
                    "pid": os.getpid(),
                    "tag": tag,
                    "deadline_sha256": hashlib.sha256(raw).hexdigest(),
                },
            )
        control.guard()
        return
    else:
        result = getattr(control, args.command)()
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
