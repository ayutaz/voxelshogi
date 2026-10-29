"""M6 purpose allocation inside the existing total budget; control-side only."""

import fcntl
import hashlib
import json
import math
import os
from pathlib import Path

from training.rental_control import QUOTES, Rental, save


class M6Rental(Rental):
    def __init__(
        self, *args, approval=None, phase="trial", maximum_seconds=14400, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.approval = Path(approval) if approval is not None else None
        self.phase, self.maximum_seconds = phase, maximum_seconds

    def quote_seconds(self):
        if (
            self.approval is None
            or self.approval.is_symlink()
            or not self.approval.is_file()
            or self.approval.stat().st_size > 65536
        ):
            raise ValueError("M6 purpose approval is required before rental")
        approval = json.loads(self.approval.read_text())
        if (
            approval.get("schema") != "voxelshogi-m6-rental-approval-v1"
            or approval.get("approved") is not True
            or approval.get("maximum_usd") != 24
            or approval.get("maximum_seconds") != 86400
            or approval.get("maximum_hourly_usd") != 1
            or approval.get("license") != "Apache-2.0"
            or approval.get("state_publication_approved") is not True
        ):
            raise ValueError(
                "M6 purpose, license and state publication must be approved"
            )
        limit = {"trial": 14400, "main": 72000}.get(self.phase)
        if (
            self.sku not in QUOTES
            or limit is None
            or type(self.maximum_seconds) is not int
            or not 1800 <= self.maximum_seconds <= limit
        ):
            raise ValueError("M6 phase time differs from the proposed quote")
        if not self.tag.startswith("voxelshogi-m6-"):
            raise ValueError("M6 requires its own ownership tag")
        if self.phase == "main":
            estimate = approval.get("main_estimate", {})
            trial = self.approval.parent / "trial.json"
            if (
                estimate.get("maximum_seconds") != self.maximum_seconds
                or type(estimate.get("estimated_seconds")) is not int
                or not 0 < estimate["estimated_seconds"] <= self.maximum_seconds - 900
                or trial.is_symlink()
                or not trial.is_file()
                or trial.stat().st_size > 4 * 1024 * 1024
                or hashlib.sha256(trial.read_bytes()).hexdigest()
                != estimate.get("trial_sha256")
            ):
                raise ValueError(
                    "M6 main requires a hash-pinned trial and fitting estimate"
                )
            report = json.loads(trial.read_text())
            speed = report.get("full_examples_per_second_including_logging_save")
            if (
                report.get("schema") != "voxelshogi-cuda-trial-v1"
                or report.get("verified") is not True
                or report.get("same_example_order") is not True
                or report.get("test_used") is not False
                or report.get("config", {}).get("device") != "cuda"
                or type(report.get("steps")) is not int
                or report["steps"] < 64
                or type(speed) not in (int, float)
                or not math.isfinite(speed)
                or speed <= 0
                or type(report.get("peak_allocated_bytes")) is not int
                or report["peak_allocated_bytes"] <= 0
            ):
                raise ValueError("M6 main estimate does not bind a verified CUDA trial")
        return self.maximum_seconds

    def rent(self, start_guard):
        self.quote_seconds()  # Approval/estimate failures precede even read-only API calls.
        return super().rent(start_guard)

    def reserve(self):
        seconds = self.quote_seconds()
        cap = seconds / 3600
        with self.budget.open("r+") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            data = json.load(stream)
            rows = data.get("reservations")
            if (
                data.get("approved_total_usd") != 100
                or not isinstance(rows, list)
                or any(
                    type(row.get("maximum_usd")) not in (int, float)
                    or not math.isfinite(row["maximum_usd"])
                    or row["maximum_usd"] < 0
                    for row in rows
                )
            ):
                raise ValueError("invalid shared approved budget")
            reserved = sum(row["maximum_usd"] for row in rows)
            owned = [row for row in rows if str(row.get("task", "")).startswith("m6-")]
            if any(
                type(row.get("maximum_seconds")) is not int
                or row["maximum_seconds"] <= 0
                for row in owned
            ):
                raise ValueError("invalid prior M6 reservation")
            if (
                reserved + cap > 100
                or sum(row["maximum_usd"] for row in owned) + cap > 24
                or sum(row["maximum_seconds"] for row in owned) + seconds > 86400
                or any(row.get("tag") == self.tag for row in rows)
            ):
                raise ValueError(
                    "M6 allocation/shared budget exceeded or tag already reserved"
                )
            rows.append(
                {
                    "task": f"m6-{self.phase}",
                    "tag": self.tag,
                    "maximum_usd": cap,
                    "maximum_seconds": seconds,
                    "state": "reserved; invoice not retrieved",
                }
            )
            data.update(
                reserved_total_usd=reserved + cap,
                remaining_unreserved_usd=100 - reserved - cap,
            )
            stream.seek(0)
            json.dump(data, stream, indent=2)
            stream.truncate()
            stream.flush()
            os.fsync(stream.fileno())
        save(
            self.state / "m6-purpose.json",
            {
                "phase": self.phase,
                "approval_sha256": hashlib.sha256(
                    self.approval.read_bytes()
                ).hexdigest(),
                "maximum_seconds": seconds,
                "maximum_usd": cap,
            },
        )
