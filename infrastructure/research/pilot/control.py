"""Operate an admitted owned Vast pilot; collect small proofs before one deletion.

No rental or cost reservation is exposed here. Freeze source/workload, admit the
real independent guard and rent through Phase6VastRental before using this CLI.
"""

import argparse
import base64
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

from infrastructure.research.pilot.collection import small_json
from infrastructure.research.pilot.retirement import (
    persist_collection,
    process_identity,
    review_collection,
    watch_pilot,
)
from training.checkpoint import atomic_json
from training.evaluation_v2 import fingerprint
from training.feature_cache import file_hash

REMOTE = "/root/voxelshogi"


class PilotController:
    def __init__(self, state, *, shared_budget, request, retire, clock=time.time):
        self.state, self.shared_budget = Path(state), Path(shared_budget)
        self.request, self.retire, self.clock = request, retire, clock
        self.value = small_json(self.state / "workflow.json")
        self.owner = small_json(self.state / "owner.json")
        workload = small_json(self.state / "workload.json")
        if (
            not re.fullmatch(r"research-pilot[1-9][0-9]*-control", self.state.name)
            or workload.get("admitted") is not True
            or workload.get("stage") != "research-pilot"
            or workload.get("source_commit") != self.value["job"]["source_commit"]
            or workload.get("workflow_sha256") != fingerprint(self.value)
            or workload.get("run_label") != "voxelshogi-phase6-" + self.state.name
            or self.owner.get("tag") != workload["run_label"]
        ):
            raise ValueError("frozen admitted controller/workflow/owner differs")
        if (
            file_hash(self.state / "state-upload-budget-initial.json")
            != self.value["job"]["state_upload_budget_sha256"]
        ):
            raise ValueError("initial shared ledger copy differs")

    def upload_inputs(self):
        return self.request(
            "install",
            {
                "workflow": self.value,
                "ledger_base64": base64.b64encode(
                    (self.state / "state-upload-budget-initial.json").read_bytes()
                ).decode(),
                "owner": self.owner,
            },
        )

    def start_worker(self, hf_token, *, start_watcher):
        if any(
            (self.state / name).exists()
            for name in ("launch-submission.json", "job-launch.json")
        ):
            raise ValueError("existing launch submission: reconnect without resending")
        installed = self.upload_inputs()
        if installed.get("installed") is not True or installed.get(
            "workflow_sha256"
        ) != fingerprint(self.value):
            raise ValueError("frozen input installation not confirmed")
        with (self.state / "launch-submission.json").open("x") as stream:
            json.dump(
                {"at": self.clock(), "workflow_sha256": fingerprint(self.value)}, stream
            )
        result = self.request(
            "launch",
            {"workflow": self.value, "owner": self.owner, "hf_token": hf_token},
        )
        process_identity({"process": {**result, "running": True}}, result)
        if result.get("source_commit") != self.value["job"]["source_commit"]:
            raise ValueError("returned worker source differs")
        atomic_json(self.state / "job-launch.json", result)
        watcher = start_watcher()
        atomic_json(self.state / "completion-watcher-launch.json", watcher)
        return result

    def observe(self):
        return self.request(
            "observe",
            {
                "workflow": self.value,
                "expected_process": small_json(self.state / "job-launch.json"),
            },
        )

    def collect(self, *, deadline=None):
        if deadline is None:
            deadline = small_json(self.state / "deadline.json")["maximum_end_at"] - 1260
        result = self.request(
            "collect",
            {
                "workflow": self.value,
                "expected_process": small_json(self.state / "job-launch.json"),
                "deadline": deadline,
            },
        )
        atomic_json(self.state / "observed-terminal.json", result)
        return result

    def persist(self, snapshot, review):
        return persist_collection(
            self.state, self.shared_budget, self.value, snapshot, review
        )

    def retire_once(self):
        with (self.state / "pilot-retirement-request.json").open("x") as stream:
            json.dump(
                {
                    "at": self.clock(),
                    "source_commit": self.value["job"]["source_commit"],
                },
                stream,
            )
        return self.retire()

    def watch(self, *, wait=time.sleep):
        if (self.state / "pilot-retirement-request.json").exists():
            raise ValueError(
                "previous retirement: inspect acknowledgement/inventory without resending"
            )
        return watch_pilot(
            self.value,
            expected_process=small_json(self.state / "job-launch.json"),
            initial_budget=small_json(self.state / "state-upload-budget-initial.json"),
            observe=self.observe,
            collect=self.collect,
            persist=self.persist,
            retire=self.retire_once,
            deadline=small_json(self.state / "deadline.json")["maximum_end_at"] - 1260,
            clock=self.clock,
            wait=wait,
            save=lambda result: atomic_json(
                self.state / "completion-watcher-status.json", result
            ),
        )


class VastTransport:
    def __init__(self, state, workload, root):
        from training.vast_phase6_control import Phase6VastRental
        from training.vast_rental_control import VastClient, project_key

        self.state, self.workload, self.root = state, workload, root
        self.rental = Phase6VastRental(
            state,
            VastClient(project_key(root, "VAST_API_KEY")),
            tag=workload["run_label"],
            budget=root / "runs/m4/cost-budget.json",
            plan=state / "plan.json",
            workload=state / "workload.json",
            phase="phase6",
        )

    def shell(self, command, data=None):
        rows = self.rental.owned()
        expected = small_json(self.state / "rent-response.json")["instance_ids"]
        owner = small_json(self.state / "owner.json")
        if (
            len(rows) != 1
            or expected != [rows[0]["id"]]
            or owner.get("provider") != "vast.ai"
            or owner.get("instance_id") != rows[0]["id"]
            or owner.get("tag") != self.workload["run_label"]
            or rows[0]["actual_status"] != "running"
        ):
            raise ValueError("one live owned host required")
        row = rows[0]
        if (
            not re.fullmatch(r"[a-zA-Z0-9.-]+", str(row["ssh_host"]))
            or type(row["ssh_port"]) is not int
            or not 1 <= row["ssh_port"] <= 65535
        ):
            raise ValueError("invalid provider SSH coordinates")
        known = self.state / "known_hosts"
        argv = [
            "ssh",
            "-T",
            "-i",
            str(self.state / "id_ed25519"),
            "-p",
            str(row["ssh_port"]),
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=20",
            "-o",
            "ServerAliveInterval=30",
            "-o",
            "ServerAliveCountMax=3",
            "-o",
            "UserKnownHostsFile=" + str(known),
            "-o",
            "StrictHostKeyChecking=" + ("yes" if known.exists() else "accept-new"),
            "root@" + row["ssh_host"],
            command,
        ]
        result = subprocess.run(
            argv, input=data, capture_output=True, check=True, timeout=180
        )
        if len(result.stdout) > 4 * 1024**2:
            raise ValueError("remote reply exceeds metadata bound")
        return result.stdout

    def request(self, mode, payload):
        module = "remote" if mode in ("install", "launch") else "collection"
        body = json.dumps({"mode": mode, **payload}, allow_nan=False).encode()
        if len(body) > 4 * 1024**2:
            raise ValueError("remote request exceeds metadata bound")
        command = (
            "cd "
            + REMOTE
            + " && /root/.local/bin/uv run --project infrastructure/cuda --locked --no-sync python -m infrastructure.research.pilot."
            + module
        )
        return json.loads(self.shell(command, body))

    def start_bootstrap(self):
        source = self.workload["source_commit"]
        raw = (self.state / "bootstrap.sh").read_text()
        expected = (
            (self.root / "infrastructure/research/pilot/bootstrap.sh")
            .read_text()
            .replace("SOURCE_COMMIT_PLACEHOLDER", source)
        )
        if (
            raw != expected
            or file_hash(self.state / "bootstrap.sh")
            != self.workload["files"]["bootstrap.sh"]
        ):
            raise ValueError("bootstrap differs from admitted Git source")
        self.shell("test ! -e /root/voxelshogi-pilot-bootstrap-request")
        self.shell("umask 077; cat > /root/voxelshogi-pilot-bootstrap.sh", raw.encode())
        inner = 'printf "%s\\n" "$$" > /root/voxelshogi-pilot-bootstrap.pid\nbash /root/voxelshogi-pilot-bootstrap.sh\npilot_exit=$?\nprintf "%s\\n" "$pilot_exit" > /root/voxelshogi-pilot-bootstrap-exit\nexit "$pilot_exit"'
        outer = (
            "umask 077\nset -C\n: > /root/voxelshogi-pilot-bootstrap-request\nnohup setsid bash -c "
            + shlex.quote(inner)
            + " > /root/voxelshogi-pilot-bootstrap.log 2>&1 < /dev/null &\nprintf 'started\\n'"
        )
        return self.shell("bash -c " + shlex.quote(outer)).decode().strip()


def main():
    from infrastructure.research.pilot import job

    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("control")
    parser.add_argument(
        "mode",
        choices=(
            "start-bootstrap",
            "bootstrap-status",
            "upload-inputs",
            "start-worker",
            "observe",
            "collect",
            "watch",
            "retirement-status",
        ),
    )
    args = parser.parse_args()
    if not re.fullmatch(r"research-pilot[1-9][0-9]*-control", args.control):
        raise ValueError("owned pilot control directory required")
    root = Path.cwd()
    state = root / "runs/p6" / args.control
    workload = small_json(state / "workload.json")
    job.check_source(workload["source_commit"])
    transport = VastTransport(state, workload, root)
    controller = PilotController(
        state,
        shared_budget=root / "runs/m6/state-upload-budget.json",
        request=transport.request,
        retire=transport.rental.terminate,
    )
    if args.mode == "start-bootstrap":
        result = {"bootstrap": transport.start_bootstrap()}
    elif args.mode == "bootstrap-status":
        result = {
            "bootstrap": transport.shell(
                "if test -f /root/voxelshogi-pilot-bootstrap-exit; then cat /root/voxelshogi-pilot-bootstrap-exit; else printf pending; fi"
            )
            .decode()
            .strip()
        }
    elif args.mode == "upload-inputs":
        result = controller.upload_inputs()
    elif args.mode == "start-worker":
        from huggingface_hub import get_token

        token = get_token()
        if not token:
            raise ValueError("HF CLI authentication required")

        def watcher():
            env = dict(os.environ)
            env.pop("HF_TOKEN", None)
            with (state / "completion-watcher.log").open("xb") as log:
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "infrastructure.research.pilot.control",
                        args.control,
                        "watch",
                    ],
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            return {"pid": process.pid, "at": time.time()}

        result = controller.start_worker(token, start_watcher=watcher)
    elif args.mode == "observe":
        result = controller.observe()
    elif args.mode == "collect":
        snapshot = controller.collect()
        review = review_collection(
            controller.value,
            snapshot,
            expected_process=small_json(state / "job-launch.json"),
            initial_budget=small_json(state / "state-upload-budget-initial.json"),
        )
        result = controller.persist(snapshot, review)
    elif args.mode == "watch":
        result = controller.watch()
    else:
        result = transport.rental.status()
        ack = (
            small_json(state / "termination-request.json")
            if (state / "termination-request.json").is_file()
            else {}
        )
        expected = small_json(state / "rent-response.json")["instance_ids"]
        result["complete"] = (
            not result["instances"]
            and ack.get("destruction_acknowledged") is True
            and ack.get("instance_ids") == expected
        )
        atomic_json(state / "retirement-status.json", result)
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        print(
            json.dumps({"control_complete": False, "error_type": type(error).__name__}),
            flush=True,
        )
        sys.exit(1)
