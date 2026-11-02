"""Phase5/6 Vast rentals using research budgets and an actual independent guard."""

import hashlib
import json
import os
from pathlib import Path

from training.rental_control import save
from training.research_rental_control import ResearchRental
from training.vast_rental_control import (
    DISK_GB,
    IMAGE,
    VastInstanceControl,
    instance_inventory,
    quote_offer,
)


class ResearchVastRental(VastInstanceControl, ResearchRental):
    PLAN_SCHEMA = "voxelshogi-vast-research-plan-v1"
    HARDWARE_FIELDS = {"offer_id", "disk_gb"}

    def validate_hardware(self, plan):
        if (
            type(plan["offer_id"]) is not int
            or plan["offer_id"] <= 0
            or type(plan["disk_gb"]) is not int
            or plan["disk_gb"] != DISK_GB
        ):
            raise ValueError("invalid Vast.ai research offer/disk quote")
        return "vast"

    def rent(self, start_guard):
        if any(
            (self.state / n).exists()
            for n in (
                "rent-request.json",
                "rent-response.json",
                "deadline.json",
                "guardian-ready.json",
                "terminal.json",
            )
        ):
            raise ValueError("existing rental request requires audit")
        plan = self.prepare()
        if any(
            str(r.get("label") or "").startswith("voxelshogi-")
            for r in instance_inventory(self.api)
        ):
            raise ValueError("existing VoxelShogi Vast.ai rental requires audit")
        offers = self.api(
            "POST",
            "/api/v0/bundles",
            {
                "id": {"eq": plan["offer_id"]},
                "type": "on-demand",
                "allocated_storage": DISK_GB,
                "limit": 2,
            },
        )["offers"]
        if (
            not isinstance(offers, list)
            or len(offers) != 1
            or offers[0].get("id") != plan["offer_id"]
        ):
            raise ValueError("Vast.ai research offer is not uniquely available")
        quote = quote_offer(offers[0])
        public_key = (self.state / "id_ed25519.pub").read_text().strip()
        if not public_key.startswith("ssh-ed25519 "):
            raise ValueError("dedicated SSH public key is missing")
        self.check_account(
            minimum_usd=quote["hourly_usd"] * plan["maximum_seconds"] / 3600
        )
        now = self.clock()
        seconds = self.quote_seconds()
        self.reserve()
        save(
            self.state / "preflight.json",
            {
                "provider": "vast.ai",
                **quote,
                "maximum_seconds": seconds,
                "maximum_usd": plan["maximum_usd"],
                "checked_at": now,
            },
        )
        save(
            self.state / "deadline.json",
            {
                "requested_at": now,
                "stop_at": now + seconds - 900,
                "maximum_end_at": now + seconds,
                "hourly_usd": quote["hourly_usd"],
                "consumption_cap_usd": plan["maximum_usd"],
            },
        )
        save(
            self.state / "rent-request.json",
            {
                "at": now,
                "tag": self.tag,
                "offer_id": plan["offer_id"],
                "provider": "vast.ai",
            },
        )
        start_guard()
        self.quote_seconds()
        result = self.api(
            "PUT",
            f"/api/v0/asks/{plan['offer_id']}",
            {
                "image": IMAGE,
                "disk": DISK_GB,
                "runtype": "ssh_direct",
                "label": self.tag,
                "target_state": "running",
                "cancel_unavail": True,
                "env": "-e NVIDIA_DRIVER_CAPABILITIES=all",
            },
        )
        identity = result.get("new_contract")
        if (
            result.get("success") is not True
            or type(identity) is not int
            or identity <= 0
        ):
            raise RuntimeError("Vast.ai create identity unconfirmed; audit exact label")
        save(
            self.state / "rent-response.json",
            {"instance_ids": [identity], "provider": "vast.ai"},
        )
        return {"instance_ids": [identity], "stop_at": now + seconds - 900}


def main():
    import argparse
    import math
    import subprocess
    import time

    from training.remote_deadline import live_guard
    from training.rental_control import wait_for_guard
    from training.research_rental_control import ALLOCATIONS, ROOT
    from training.vast_rental_control import (
        VastClient,
        project_key,
        require_cloudrift_idle,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", type=Path)
    parser.add_argument(
        "command", choices=("rent", "status", "attach-key", "terminate", "guard")
    )
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--workload", type=Path)
    parser.add_argument("--phase", choices=tuple(ALLOCATIONS), default="phase5")
    parser.add_argument("--guard-run", type=int)
    parser.add_argument(
        "--budget", type=Path, default=ROOT / "runs/m4/cost-budget.json"
    )
    parser.add_argument("--ready-file", type=Path)
    args = parser.parse_args()
    state, budget = args.state.resolve(), args.budget.resolve()
    if not state.is_relative_to(ROOT / "runs") or not budget.is_relative_to(
        ROOT / "runs"
    ):
        parser.error("dedicated control state/budget under runs/ required")
    import re

    if not re.fullmatch(r"[a-z0-9-]+", state.name):
        parser.error("invalid control directory identity")
    for path in (args.plan, args.workload):
        if path is not None and (
            path.is_symlink() or not path.resolve().is_relative_to(ROOT / "runs")
        ):
            parser.error("plan/workload must remain under ignored runs/")
    if args.command == "rent" and (
        args.plan is None or args.workload is None or args.guard_run is None
    ):
        parser.error("rent requires --plan --workload --guard-run")
    tag = "voxelshogi-" + args.phase + "-" + state.name
    control = ResearchVastRental(
        state,
        VastClient(project_key(ROOT, "VAST_API_KEY")),
        tag=tag,
        budget=budget,
        phase=args.phase,
        plan=args.plan,
        workload=args.workload,
        other_provider_idle=lambda: require_cloudrift_idle(ROOT),
        remote_guard=lambda **kw: live_guard(args.guard_run, provider="vast", **kw),
    )

    def start_guard():
        import sys

        ready = state / "guardian-ready.json"
        with (state / "guardian.log").open("a") as log:
            child = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "training.vast_research_control",
                    str(state),
                    "guard",
                    "--budget",
                    str(budget),
                    "--phase",
                    args.phase,
                    "--ready-file",
                    str(ready),
                ],
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
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
            raise
        save(state / "guardian.json", {"pid": child.pid, "at": time.time()})

    if args.command == "guard":
        if args.ready_file is not None:
            if args.ready_file.resolve() != state / "guardian-ready.json":
                parser.error("ready file must belong to this state")
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
                raise ValueError("invalid guardian deadline")
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
    result = (
        control.rent(start_guard)
        if args.command == "rent"
        else getattr(control, args.command.replace("-", "_"))()
    )
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
