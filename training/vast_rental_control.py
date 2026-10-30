"""Vast.ai M6-only lifecycle control. Importing never accesses the provider."""

import json
import math
import re

from training.m6_rental_control import M6Rental, validate_m6_approval
from training.rental_control import save

DISK_GB = 80
MAXIMUM_SECONDS = 14400
IMAGE = "nvidia/cuda@sha256:e3fd439288969c0c78d52768cda4a10ab20f408180d6fa2933f94f7af7810cb0"


def quote_offer(offer):
    """A deliberately narrow quote: one RTX5090, free transfers, disk included."""
    try:
        numbers = [
            offer[k]
            for k in (
                "dph_base",
                "dph_total",
                "storage_total_cost",
                "inet_up_cost",
                "inet_down_cost",
            )
        ]
        if any(
            type(n) not in (int, float) or not math.isfinite(n) or n < 0
            for n in numbers
        ):
            raise ValueError("nonfinite/negative Vast.ai price")
        if any(
            type(offer[k]) not in (int, float) or not math.isfinite(offer[k])
            for k in (
                "num_gpus",
                "gpu_ram",
                "cpu_ram",
                "cpu_cores_effective",
                "disk_space",
                "reliability2",
                "cuda_max_good",
                "direct_port_count",
            )
        ):
            raise ValueError("nonfinite Vast.ai resource facts")
        hourly = max(
            offer["dph_total"], offer["dph_base"] + offer["storage_total_cost"]
        )
        if (
            type(offer["id"]) is not int
            or offer["id"] <= 0
            or offer["gpu_name"] not in ("RTX 5090", "RTX_5090")
            or offer["num_gpus"] != 1
            or offer["gpu_ram"] < 30000
            or offer["cpu_ram"] < 24576
            or offer["cpu_cores_effective"] < 6
            or offer["disk_space"] < DISK_GB
            or offer["rentable"] is not True
            or offer["rented"] is not False
            or offer["verification"] != "verified"
            or offer["reliability2"] < 0.99
            or offer["cuda_max_good"] < 13
            or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", offer["driver_version"])
            or int(offer["driver_version"].split(".")[0]) < 580
            or offer["direct_port_count"] < 1
            or offer["inet_up_cost"] != 0
            or offer["inet_down_cost"] != 0
            or not 0 < hourly <= 1
        ):
            raise ValueError("Vast.ai hardware/price/availability differs from quote")
        return {
            "offer_id": offer["id"],
            "gpu": "RTX 5090",
            "disk_gb": DISK_GB,
            "hourly_usd": hourly,
            "maximum_seconds": MAXIMUM_SECONDS,
            "maximum_usd": 4,
            "bandwidth": "unmetered",
        }
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("incomplete Vast.ai quote") from error


def instance_inventory(api):
    rows, tokens = [], set()
    token = None
    total = None
    for _ in range(100):
        params = {
            "limit": 25,
            "select_cols": json.dumps(
                ["id", "label", "actual_status", "ssh_host", "ssh_port"]
            ),
        }
        if token is not None:
            params["after_token"] = token
        page = api("GET", "/api/v1/instances", params=params)
        if (
            page.get("success") is not True
            or not isinstance(page.get("instances"), list)
            or page.get("instances_found") != len(page["instances"])
        ):
            raise ValueError("incomplete Vast.ai inventory")
        if total is None:
            total = page["total_instances"]
        if type(total) is not int or total < 0 or page["total_instances"] != total:
            raise ValueError("Vast.ai inventory changed during pagination")
        rows.extend(page["instances"])
        token = page.get("next_token")
        if token is None:
            if len(rows) != total or len({row["id"] for row in rows}) != len(rows):
                raise ValueError("incomplete/duplicate Vast.ai inventory")
            return rows
        if not isinstance(token, str) or not token or token in tokens:
            raise ValueError("repeated Vast.ai inventory cursor")
        tokens.add(token)
    raise ValueError("Vast.ai inventory pagination exceeds limit")


class VastRental(M6Rental):
    def __init__(self, *args, other_provider_idle, **kwargs):
        super().__init__(*args, sku="vast", **kwargs)
        self.other_provider_idle = other_provider_idle

    def check_account(self, minimum_usd=0):
        account = self.api("GET", "/api/v0/users/current")
        identity = account.get("id")
        if type(identity) is not int or identity <= 0:
            raise ValueError("Vast.ai account identity is missing")
        path = self.state / "account.json"
        if path.exists() and json.loads(path.read_text()).get("id") != identity:
            raise ValueError("Vast.ai account differs from the rented account")
        balance = account.get("balance")
        if minimum_usd and (
            type(balance) not in (int, float)
            or not math.isfinite(balance)
            or balance < minimum_usd
        ):
            raise ValueError("Vast.ai balance does not cover the full quoted rental")
        if not path.exists():
            save(path, {"id": identity})

    def quote_seconds(self):
        seconds = validate_m6_approval(
            self.approval, self.tag, self.phase, self.maximum_seconds
        )
        if seconds != MAXIMUM_SECONDS:
            raise ValueError("Vast.ai quote is limited to four hours")
        return seconds

    def rent(self, offer_id, start_guard):
        self.quote_seconds()
        if type(offer_id) is not int or offer_id <= 0:
            raise ValueError("invalid Vast.ai offer ID")
        if any(
            (self.state / name).exists()
            for name in (
                "rent-request.json",
                "rent-response.json",
                "deadline.json",
                "terminal.json",
                "guardian-ready.json",
            )
        ):
            raise ValueError("existing rental request requires audit")
        if any(
            str(row.get("label") or "").startswith("voxelshogi-")
            for row in instance_inventory(self.api)
        ):
            raise ValueError("existing VoxelShogi Vast.ai rental")
        self.other_provider_idle()
        offers = self.api(
            "POST",
            "/api/v0/bundles",
            {
                "id": {"eq": offer_id},
                "type": "on-demand",
                "allocated_storage": DISK_GB,
                "limit": 2,
            },
        )["offers"]
        if (
            not isinstance(offers, list)
            or len(offers) != 1
            or offers[0].get("id") != offer_id
        ):
            raise ValueError("selected Vast.ai offer is not uniquely available")
        quote = quote_offer(offers[0])
        key = (self.state / "id_ed25519.pub").read_text().strip()
        if not key.startswith("ssh-ed25519 "):
            raise ValueError("dedicated SSH public key is missing")
        self.check_account(minimum_usd=quote["hourly_usd"] * MAXIMUM_SECONDS / 3600)
        self.reserve()
        now = self.clock()
        save(
            self.state / "preflight.json",
            {"provider": "vast.ai", **quote, "checked_at": now},
        )
        save(
            self.state / "deadline.json",
            {
                "requested_at": now,
                "stop_at": now + MAXIMUM_SECONDS - 900,
                "maximum_end_at": now + MAXIMUM_SECONDS,
                "hourly_usd": quote["hourly_usd"],
                "consumption_cap_usd": 4,
            },
        )
        start_guard()
        save(
            self.state / "rent-request.json",
            {"at": now, "tag": self.tag, "offer_id": offer_id, "provider": "vast.ai"},
        )
        response = self.api(
            "PUT",
            f"/api/v0/asks/{offer_id}",
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
        identity = response.get("new_contract")
        if (
            response.get("success") is not True
            or type(identity) is not int
            or identity <= 0
        ):
            raise RuntimeError(
                "Vast.ai create did not return a unique contract; audit label"
            )
        save(
            self.state / "rent-response.json",
            {"instance_ids": [identity], "provider": "vast.ai"},
        )
        return {"instance_ids": [identity], "stop_at": now + MAXIMUM_SECONDS - 900}

    def owned(self):
        self.check_account()
        rows = instance_inventory(self.api)
        response = self.state / "rent-response.json"
        ids = (
            json.loads(response.read_text())["instance_ids"]
            if response.exists()
            else []
        )
        selected = (
            [row for row in rows if row["id"] in ids]
            if ids
            else [row for row in rows if row.get("label") == self.tag]
        )
        if any(row.get("label") != self.tag for row in selected):
            raise ValueError("Vast.ai instance ownership differs")
        return selected

    def status(self):
        rows = [
            {
                key: row.get(key)
                for key in ("id", "label", "actual_status", "ssh_host", "ssh_port")
            }
            for row in self.owned()
        ]
        result = {"provider": "vast.ai", "checked_at": self.clock(), "instances": rows}
        save(self.state / "status.json", result)
        return result

    def attach_key(self):
        rows = self.owned()
        if len(rows) != 1:
            raise ValueError("one owned Vast.ai instance required for SSH")
        key = (self.state / "id_ed25519.pub").read_text().strip()
        if not key.startswith("ssh-ed25519 "):
            raise ValueError("dedicated SSH public key is missing")
        response = self.api(
            "POST", f"/api/v0/instances/{rows[0]['id']}/ssh", {"ssh_key": key}
        )
        if response.get("success") is not True:
            raise RuntimeError("Vast.ai SSH attachment not confirmed")
        save(
            self.state / "ssh-key-attached.json",
            {"instance_id": rows[0]["id"], "success": True},
        )
        return {"success": True}

    def terminate(self):
        rows = self.owned()
        response = self.state / "rent-response.json"
        if rows and not response.exists():
            save(
                response,
                {
                    "instance_ids": [row["id"] for row in rows],
                    "recovered_from_label": True,
                    "provider": "vast.ai",
                },
            )
        expected = (
            json.loads(response.read_text())["instance_ids"]
            if response.exists()
            else []
        )
        for row in rows:
            deleted = self.api("DELETE", f"/api/v0/instances/{row['id']}")
            if deleted.get("success") is not True:
                raise RuntimeError("Vast.ai destruction not acknowledged")
        if rows:
            save(
                self.state / "termination-request.json",
                {
                    "at": self.clock(),
                    "instance_ids": expected,
                    "destruction_acknowledged": True,
                },
            )
        result = self.status()
        ack = self.state / "termination-request.json"
        result["complete"] = (
            bool(expected)
            and not result["instances"]
            and ack.exists()
            and json.loads(ack.read_text()).get("instance_ids") == expected
        )
        if result["complete"]:
            save(self.state / "terminal.json", result)
        return result


class VastClient:
    """Official API only; credentials never appear in URLs or error bodies."""

    def __init__(self, key, opener=None):
        import urllib.request

        from training.rental_control import NoRedirect

        if not key:
            raise ValueError("Vast.ai credential is missing")
        self.key = key
        self.opener = opener or urllib.request.build_opener(NoRedirect)

    def __call__(self, method, path, data=None, params=None):
        import urllib.error
        import urllib.parse
        import urllib.request

        if method not in ("GET", "POST", "PUT", "DELETE") or not re.fullmatch(
            r"/api/v[01]/[a-z0-9/_-]+", path
        ):
            raise ValueError("invalid official Vast.ai API path")
        url = "https://console.vast.ai" + path.rstrip("/") + "/"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(
            url,
            data=json.dumps(data).encode() if data is not None else None,
            headers={
                "Authorization": "Bearer " + self.key,
                "Content-Type": "application/json",
            },
            method=method,
        )
        try:
            with self.opener.open(request, timeout=40) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            raise RuntimeError("Vast.ai HTTP " + str(error.code)) from None


def project_key(root, name):
    key = ""
    for line in (root / ".env").read_text().splitlines():
        match = re.match(
            r"^\s*(?:export\s+)?" + re.escape(name) + r"\s*=\s*(.*?)\s*$", line
        )
        if match:
            key = match[1].strip().strip("\"'")
    if not key:
        raise ValueError(name + " is missing from the project configuration")
    return key


def require_cloudrift_idle(root):
    """Check live cross-provider ownership before accepting any paid Vast.ai offer."""
    import urllib.request

    from training.rental_control import NoRedirect

    request = urllib.request.Request(
        "https://api.cloudrift.ai/api/v1/instances/list",
        data=json.dumps(
            {
                "version": "2026-09-08",
                "data": {
                    "selector": {
                        "ByStatus": {
                            "statuses": ["Initializing", "Active", "Deactivating"],
                            "scope": "Personal",
                            "limit": 1000,
                        }
                    },
                    "mask": {"with_usage_info": True},
                },
            }
        ).encode(),
        headers={
            "X-API-Key": project_key(root, "CLOUDRIFT_API_KEY"),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.build_opener(NoRedirect).open(request, timeout=40) as response:
        rows = json.load(response)["data"]["instances"]
    if any(
        any(str(tag).startswith("voxelshogi-") for tag in row.get("tags", []))
        for row in rows
    ):
        raise ValueError("existing CloudRift VoxelShogi rental must be audited first")


def search_offers(api):
    result = api(
        "POST",
        "/api/v0/bundles",
        {
            "gpu_name": {"in": ["RTX 5090", "RTX_5090"]},
            "num_gpus": {"eq": 1},
            "rentable": {"eq": True},
            "rented": {"eq": False},
            "verification": {"eq": "verified"},
            "inet_up_cost": {"eq": 0},
            "inet_down_cost": {"eq": 0},
            "gpu_ram": {"gte": 30000},
            "cpu_ram": {"gte": 24576},
            "cpu_cores_effective": {"gte": 6},
            "disk_space": {"gte": DISK_GB},
            "cuda_max_good": {"gte": 13},
            "dph_total": {"lte": 1},
            "type": "on-demand",
            "allocated_storage": DISK_GB,
            "limit": 100,
            "order": [["dph_total", "asc"]],
        },
    )
    quotes = []
    if not isinstance(result.get("offers"), list):
        raise ValueError("invalid Vast.ai offers response")
    for row in result["offers"]:
        try:
            quotes.append(quote_offer(row))
        except ValueError:
            pass
    return sorted(quotes, key=lambda row: (row["hourly_usd"], row["offer_id"]))


def main():
    import argparse
    import hashlib
    import os
    import subprocess
    import sys
    import time
    from pathlib import Path

    from training.rental_control import wait_for_guard

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", type=Path)
    parser.add_argument(
        "command",
        choices=["search", "rent", "status", "attach-key", "terminate", "guard"],
    )
    parser.add_argument("--offer", type=int)
    parser.add_argument("--budget", type=Path)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--ready-file", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    state = args.state.resolve()
    budget = (args.budget or root / "runs/m4/cost-budget.json").resolve()
    if (
        not state.is_relative_to(root / "runs")
        or not re.fullmatch(r"[a-z0-9-]+", state.name)
        or not budget.is_relative_to(root / "runs")
    ):
        parser.error("dedicated ignored control state and budget under runs/ required")
    if args.approval is not None:
        args.approval = args.approval.resolve()
        if not args.approval.is_relative_to(root / "runs"):
            parser.error("approval must remain under runs/")
    api = VastClient(project_key(root, "VAST_API_KEY"))
    if args.command == "search":
        result = {
            "provider": "vast.ai",
            "checked_at": time.time(),
            "quotes": search_offers(api),
        }
        state.mkdir(parents=True, exist_ok=True)
        save(state / "offers.json", result)
        print(json.dumps(result))
        return
    tag = "voxelshogi-m6-" + state.name
    control = VastRental(
        state,
        api,
        tag=tag,
        budget=budget,
        approval=args.approval,
        phase="main",
        maximum_seconds=MAXIMUM_SECONDS,
        other_provider_idle=lambda: require_cloudrift_idle(root),
    )

    def start_guard():
        ready = state / "guardian-ready.json"
        with (state / "guardian.log").open("a") as log:
            child = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "training.vast_rental_control",
                    str(state),
                    "guard",
                    "--budget",
                    str(budget),
                    "--ready-file",
                    str(ready),
                ],
                stdout=log,
                stderr=log,
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
        if sys.platform == "darwin":
            awake = subprocess.Popen(
                ["/usr/bin/caffeinate", "-i", "-w", str(child.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            save(
                state / "caffeinate.json", {"pid": awake.pid, "guardian_pid": child.pid}
            )

    if args.command == "guard":
        if (
            args.ready_file is None
            or args.ready_file.resolve() != state / "guardian-ready.json"
        ):
            parser.error("guard requires its dedicated readiness file")
        raw = (state / "deadline.json").read_bytes()
        limits = json.loads(raw)
        if (
            not all(
                type(limits.get(key)) in (int, float) and math.isfinite(limits[key])
                for key in ("stop_at", "maximum_end_at")
            )
            or limits["stop_at"] >= limits["maximum_end_at"]
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
    if args.command == "rent":
        result = control.rent(args.offer, start_guard)
    else:
        result = getattr(control, args.command.replace("-", "_"))()
    print(json.dumps(result))


if __name__ == "__main__":
    main()
