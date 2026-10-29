"""Control-side only: one quoted CloudRift rental, budget and deadline guardian."""

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SKU = "rtx59-7-48-750-xam.1"
DC = "na_west_us_gr_1"
QUOTES = {SKU: 43200, "rtx59-3-24-750-xam.1": 86400}
M6_SHARED_SKU = "rtx59-7-23-800-ig.1"
M6_SHARED_DC = "ap_northeast_kr_se_1"
TERMINAL = {"Inactive", "Failed", "Deleted", "Terminated"}


def save(path, value):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w") as stream:
        os.chmod(tmp, 0o600)
        json.dump(value, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    tmp.replace(path)


class Rental:
    def __init__(
        self, state, api, *, tag, budget, clock=time.time, pause=time.sleep, sku=SKU
    ):
        self.state, self.api, self.tag, self.budget, self.clock = (
            Path(state),
            api,
            tag,
            Path(budget),
            clock,
        )
        self.pause = pause
        self.sku = sku
        self.state.mkdir(parents=True, exist_ok=True)

    def quote_seconds(self):
        return QUOTES[self.sku]

    def configuration(self):
        return {"skus": tuple(QUOTES), "datacenter": DC, "with_public_ip": True}

    def reserve(self):
        maximum_seconds = self.quote_seconds()
        cap = maximum_seconds / 3600
        with self.budget.open("r+") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            data = json.load(stream)
            reserved = sum(item["maximum_usd"] for item in data["reservations"])
            if (
                data["approved_total_usd"] != 100
                or reserved + cap > 100
                or any(item.get("tag") == self.tag for item in data["reservations"])
            ):
                raise ValueError(
                    "production exceeds the remaining approved budget or was already reserved"
                )
            data["reservations"].append(
                {
                    "task": "m4-production",
                    "tag": self.tag,
                    "maximum_usd": cap,
                    "maximum_seconds": maximum_seconds,
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

    def rent(self, start_guard):
        configuration = self.configuration()
        dc, public_ip = configuration["datacenter"], configuration["with_public_ip"]
        if self.sku not in configuration["skus"]:
            raise ValueError("SKU has no production quote")
        maximum_seconds = self.quote_seconds()
        cap = maximum_seconds / 3600
        if any(
            (self.state / name).exists()
            for name in (
                "rent-request.json",
                "terminal.json",
                "deadline.json",
                "guardian-ready.json",
            )
        ):
            raise ValueError(
                "rental request exists; audit it instead of creating another"
            )
        catalog = self.api(
            "/api/v1/instance-types/list",
            {
                "selector": {
                    "ByServiceAndLocation": {"services": ["vm"], "datacenters": [dc]}
                }
            },
        )
        offers = [
            v
            for group in catalog["instance_types"]
            for v in group["variants"]
            if v["name"] == self.sku
        ]
        if len(offers) != 1:
            raise ValueError("selected SKU is not uniquely available")
        offer = offers[0]
        if not (
            0 < offer["cost_per_hour"] <= 100
            and offer["gpu_count"] == 1
            and offer["available_nodes_per_dc"].get(dc, 0) > 0
            and (
                not public_ip
                or offer["ip_availability_per_dc"].get(dc, {}).get("public_ips")
            )
        ):
            raise ValueError(
                "selected price, stock or IP differs from the approved quote"
            )
        existing = self.api(
            "/api/v1/instances/list",
            {
                "selector": {
                    "ByStatus": {
                        "statuses": ["Initializing", "Active", "Deactivating"],
                        "scope": "Personal",
                        "limit": 1000,
                    }
                },
                "mask": {"with_usage_info": True},
            },
        )["instances"]
        if any(
            row["status"] not in TERMINAL
            and any(str(tag).startswith("voxelshogi-") for tag in row.get("tags", []))
            for row in existing
        ):
            raise ValueError("another VoxelShogi rental is active")
        public_key = (self.state / "id_ed25519.pub").read_text().strip()
        if not public_key.startswith("ssh-ed25519 "):
            raise ValueError("dedicated public SSH key is missing")
        self.reserve()
        now = self.clock()
        save(
            self.state / "deadline.json",
            {
                "requested_at": now,
                "stop_at": now + maximum_seconds - 900,
                "maximum_end_at": now + maximum_seconds,
                "hourly_usd": offer["cost_per_hour"] / 100,
                "consumption_cap_usd": cap,
            },
        )
        save(
            self.state / "preflight.json",
            {
                "sku": self.sku,
                "datacenter": dc,
                "with_public_ip": public_ip,
                "cost_per_hour_cents": offer["cost_per_hour"],
                "available_nodes": offer["available_nodes_per_dc"][dc],
                "checked_at": now,
            },
        )
        save(
            self.state / "rent-request.json",
            {
                "at": now,
                "tag": self.tag,
                "sku": self.sku,
                "datacenter": dc,
                "with_public_ip": public_ip,
            },
        )
        start_guard()  # Must be alive before the API can create a paid resource.
        payload = {
            "selector": {
                "ByInstanceTypeAndLocation": {
                    "instance_type": self.sku,
                    "datacenters": [dc],
                }
            },
            "config": {
                "VirtualMachine": {
                    "image_url": "https://storage.googleapis.com/cloudrift-vm-disks/disks/github/ubuntu-noble-server-gpu-580-129-20260716-134310.img",
                    "cloudinit_url": "https://storage.googleapis.com/cloudrift-vm-disks/cloudinit/ubuntu-base.cloudinit",
                    "ssh_key": {"PublicKeys": [public_key]},
                    "ports": ["22"],
                }
            },
            "with_public_ip": public_ip,
            "tags": [self.tag],
            "name": self.tag,
        }
        result = self.api("/api/v1/instances/rent", payload)
        save(self.state / "rent-response.json", result)
        if len(result.get("instance_ids", [])) != 1:
            self.terminate()
            raise ValueError("rental did not create exactly one instance")
        return {
            "instance_ids": result["instance_ids"],
            "stop_at": now + maximum_seconds - 900,
        }

    def owned(self):
        response = self.state / "rent-response.json"
        ids = (
            json.loads(response.read_text()).get("instance_ids", [])
            if response.exists()
            else []
        )
        selector = {"ById": ids} if ids else {"ByTags": {"all": [self.tag], "any": []}}
        rows = self.api(
            "/api/v1/instances/list",
            {
                "selector": selector,
                "mask": {"with_connection_info": True, "with_usage_info": True},
            },
        )["instances"]
        if any(
            self.tag not in row.get("tags", []) or (ids and row["id"] not in ids)
            for row in rows
        ):
            raise ValueError("instance ownership differs; refuse to terminate")
        return rows

    def status(self):
        rows = [
            {
                k: row.get(k)
                for k in (
                    "id",
                    "status",
                    "resources_released",
                    "host_address",
                    "port_mappings",
                )
            }
            for row in self.owned()
        ]
        result = {"checked_at": self.clock(), "instances": rows}
        save(self.state / "status.json", result)
        return result

    def terminate(self):
        rows = self.owned()
        response_path = self.state / "rent-response.json"
        if rows and not response_path.exists():
            save(
                response_path,
                {
                    "instance_ids": [row["id"] for row in rows],
                    "recovered_from_tag": True,
                },
            )
        active = [row["id"] for row in rows if row["status"] not in TERMINAL]
        if active:
            self.api("/api/v1/instances/terminate", {"selector": {"ById": active}})
            save(
                self.state / "termination-request.json",
                {"at": self.clock(), "instance_ids": active},
            )
        result = self.status()
        expected_path = self.state / "rent-response.json"
        expected = (
            json.loads(expected_path.read_text()).get("instance_ids", [])
            if expected_path.exists()
            else []
        )
        actual = result["instances"]
        result["complete"] = (
            bool(actual)
            and bool(expected)
            and {row["id"] for row in actual} == set(expected)
            and all(
                row["status"] in TERMINAL and row["resources_released"] is True
                for row in actual
            )
        )
        if result["complete"]:
            save(self.state / "terminal.json", result)
        return result

    def guard(self):
        limits = json.loads((self.state / "deadline.json").read_text())
        while self.clock() < limits["stop_at"]:
            if (self.state / "terminal.json").exists():
                return
            self.pause(min(60, max(0.1, limits["stop_at"] - self.clock())))
        while self.clock() < limits["maximum_end_at"]:
            try:
                if self.terminate()["complete"]:
                    return
            except Exception:
                save(
                    self.state / "guardian-error.json",
                    {"at": self.clock(), "status": "termination not confirmed"},
                )
            self.pause(60)
        # Keep attempting cleanup after an unconfirmed provider response. Never
        # interpret an observation timeout as proof that billing has stopped.
        save(
            self.state / "deadline-exceeded.json",
            {"at": self.clock(), "complete": False},
        )
        while True:
            try:
                if self.terminate()["complete"]:
                    return
            except Exception:
                pass
            self.pause(60)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def guard_command(state, budget, *, purpose, sku):
    return [
        sys.executable,
        "-m",
        "training.rental_control",
        str(state),
        "guard",
        "--budget",
        str(budget),
        "--ready-file",
        str(Path(state) / "guardian-ready.json"),
        "--purpose",
        purpose,
        "--sku",
        sku,
    ]


def wait_for_guard(
    ready, child, *, tag, deadline_sha256, clock=time.monotonic, pause=time.sleep
):
    end = clock() + 10
    while clock() < end:
        if child.poll() is not None:
            raise RuntimeError("deadline guardian exited before readiness")
        if ready.exists():
            if ready.is_symlink():
                raise RuntimeError("deadline guardian readiness mismatch")
            value = json.loads(ready.read_text())
            if value != {
                "pid": child.pid,
                "tag": tag,
                "deadline_sha256": deadline_sha256,
            }:
                raise RuntimeError("deadline guardian readiness mismatch")
            return
        pause(0.1)  # Local process startup only, never a provider/CI status poll.
    raise RuntimeError("deadline guardian readiness timed out")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", type=Path)
    parser.add_argument("command", choices=("rent", "status", "terminate", "guard"))
    parser.add_argument("--budget", type=Path)
    parser.add_argument("--sku", choices=(*QUOTES, M6_SHARED_SKU), default=SKU)
    parser.add_argument("--purpose", choices=("m4", "m6"), default="m4")
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--phase", choices=("trial", "main"), default="trial")
    parser.add_argument("--maximum-seconds", type=int, default=14400)
    parser.add_argument("--ready-file", type=Path)
    args = parser.parse_args()
    if args.purpose != "m6" and (
        args.approval is not None
        or args.phase != "trial"
        or args.maximum_seconds != 14400
    ):
        parser.error("M6 settings require --purpose m6")
    root = Path(__file__).resolve().parents[1]
    state = args.state.resolve()
    if not state.is_relative_to(root / "runs") or not re.fullmatch(
        r"[a-z0-9-]+", state.name
    ):
        parser.error("control state must be a dedicated ignored runs/ directory")
    budget = (args.budget or root / "runs/m4/cost-budget.json").resolve()
    if not budget.is_relative_to(root / "runs"):
        parser.error("budget must remain in ignored runs/")
    if args.approval is not None:
        args.approval = args.approval.resolve()
        if not args.approval.is_relative_to(root / "runs"):
            parser.error("approval record must remain in ignored runs/")
    tag = "voxelshogi-" + args.purpose + "-" + state.name
    key = ""
    for line in (root / ".env").read_text().splitlines():
        match = re.match(r"^\s*(?:export\s+)?CLOUDRIFT_API_KEY\s*=\s*(.*?)\s*$", line)
        if match:
            key = match[1].strip().strip("\"'")
    if not key:
        parser.error("CloudRift credential is missing")

    def api(path, data):
        request = urllib.request.Request(
            "https://api.cloudrift.ai" + path,
            data=json.dumps({"version": "2026-09-08", "data": data}).encode(),
            headers={"X-API-Key": key, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.build_opener(NoRedirect).open(
                request, timeout=40
            ) as response:
                return json.load(response)["data"]
        except urllib.error.HTTPError as error:
            raise RuntimeError("CloudRift HTTP " + str(error.code)) from None

    if args.purpose == "m6":
        from training.m6_rental_control import M6Rental

        control = M6Rental(
            state,
            api,
            tag=tag,
            budget=budget,
            sku=args.sku,
            approval=args.approval,
            phase=args.phase,
            maximum_seconds=args.maximum_seconds,
        )
    else:
        control = Rental(state, api, tag=tag, budget=budget, sku=args.sku)

    def start_guard():
        ready = state / "guardian-ready.json"
        ready.unlink(missing_ok=True)
        with (state / "guardian.log").open("a") as stream:
            child = subprocess.Popen(
                guard_command(
                    state,
                    budget,
                    purpose=args.purpose,
                    sku=args.sku,
                ),
                stdout=stream,
                stderr=stream,
                start_new_session=True,
                cwd=root,
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
                parser.error("guardian readiness file must belong to the control state")
            raw = (state / "deadline.json").read_bytes()
            limits = json.loads(raw)
            if not all(
                type(limits.get(name)) in (int, float)
                for name in ("stop_at", "maximum_end_at")
            ):
                raise ValueError("guardian deadline is incomplete")
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
    print(json.dumps(result))


if __name__ == "__main__":
    main()
