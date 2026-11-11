"""One scientific M pilot and an identical CUDA replay companion.

This does not choose data, hyperparameters, compute budgets, independent seeds,
or models. Freeze those only after actual admission and teacher review. It also
does not evaluate development games, the final holdout, or publish Web models.
"""

import json
import math
import runpy
import sys
import time
from pathlib import Path


def load_ports():
    root = Path(__file__).resolve().parent
    child = runpy.run_path(str(root / "child.py"))
    transfer = runpy.run_path(str(root / "state_transfer.py"))
    proof = runpy.run_path(str(root / "resume_proof.py"))
    return {
        "launch": child["run_attempt"],
        "pack": transfer["prepare_archive"],
        "transfer": transfer["publish_restore"],
        "prove": proof["verify_runs"],
    }


def recover_cycle(
    base,
    *,
    deadline,
    api,
    fetch,
    upload_budget,
    ports,
    clock=time.time,
):
    """Preserve terminal child states; never retire a host or repeat an upload.

    The caller has joined/stopped its owned fitting child before entering here.
    Real packing validates checkpoint receipts/binding/history. The control
    side must still collect the updated ledger and verify owned retirement.
    """
    if sys.platform != "linux":
        raise ValueError("pilot recovery requires external Linux")
    from training.checkpoint import atomic_json

    base = Path(base)
    candidates = [
        name
        for name in ("continuous", "interrupted", "restored")
        if (base / name / "run.json").exists()
    ]
    result = {
        "schema": "voxelshogi-research-pilot-failure-recovery-v1",
        "job_complete": False,
        "host_retirement_authorized": False,
        "states_preserved": False,
        "records": [],
        "unpreserved_runs": list(candidates),
        "controller_ledger_collection_required": True,
    }

    def finish(reason):
        result["reason"] = reason
        atomic_json(base / "failure-rescue-result.json", result)
        return result

    if not candidates:
        return finish("no-checkpoint-evidence")
    if (
        type(deadline) not in (int, float)
        or not math.isfinite(deadline)
        or clock() >= deadline
    ):
        return finish("transfer-deadline")
    # An attempt marker without a verified completed roundtrip is ambiguous.
    # Inspect it before making *any* additional publication request.
    for attempt in base.glob("*-transfer/publication-attempt.json"):
        complete = attempt.parent / "complete.json"
        try:
            evidence = json.loads(complete.read_text())
        except OSError, ValueError:
            return finish("publication-needs-reconciliation")
        if (
            evidence.get("receipt", {}).get("verified") is not True
            or evidence.get("restored") is not True
        ):
            return finish("publication-needs-reconciliation")
    marker = base / "failure-rescue-request.json"
    try:
        with marker.open("x") as stream:
            json.dump({"at": clock()}, stream)
    except FileExistsError:
        return finish("existing-rescue-needs-reconciliation")
    for name in candidates:
        if clock() >= deadline:
            return finish("transfer-deadline")
        source = base / name
        folder = base / ("failure-rescue-" + name + "-archive")
        control = base / ("failure-rescue-" + name + "-transfer")
        restored = base / ("failure-rescue-" + name + "-reconstruction")
        stage = "packing"
        try:
            if source.is_symlink() or (source / "run.json").is_symlink():
                raise ValueError("owned regular run required")
            ports["pack"](source, folder)
            stage = "publication-verification-restoration"
            transfer = ports["transfer"](
                folder,
                control,
                restored,
                api=api,
                fetch=fetch,
                upload_budget=upload_budget,
                deadline=deadline,
            )
            if (
                transfer["receipt"]["verified"] is not True
                or transfer["restored"] is not True
            ):
                raise ValueError("failure state roundtrip not verified")
            result["records"].append({"run": name, "transfer": transfer})
            result["unpreserved_runs"].remove(name)
        except BaseException as error:
            result["records"].append(
                {"run": name, "stage": stage, "error_type": type(error).__name__}
            )
            if stage != "packing":
                # A failed/unknown write is not permission to publish again.
                return finish("publication-needs-reconciliation")
    result["states_preserved"] = not result["unpreserved_runs"]
    return finish("preserved" if result["states_preserved"] else "checkpoint-invalid")


def run_cycle(
    inputs,
    base,
    *,
    split_step,
    deadline,
    compute_deadline,
    api,
    fetch,
    upload_budget,
    stop_requested=lambda: False,
    ports=None,
):
    if sys.platform != "linux":
        raise ValueError("pilot cycle requires external Linux")
    from training.checkpoint import atomic_json
    from training.evaluation_v2 import fingerprint

    root = Path(__file__).resolve().parent
    config, _ = runpy.run_path(str(root / "attempt.py"))["validate_inputs"](inputs)
    if (
        type(split_step) is not int
        or not 1 <= split_step < config.total_updates
        or type(deadline) not in (int, float)
        or not math.isfinite(deadline)
        or time.time() >= deadline
        or type(compute_deadline) not in (int, float)
        or not math.isfinite(compute_deadline)
        or not time.time() < compute_deadline < deadline
        or stop_requested()
    ):
        raise ValueError("invalid frozen cycle split/deadline")
    ports = load_ports() if ports is None else ports
    if set(ports) != {"launch", "pack", "transfer", "prove"}:
        raise ValueError("incomplete cycle execution ports")
    base = Path(base)
    base.mkdir(parents=True, exist_ok=False)
    input_path = base / "inputs.json"
    atomic_json(input_path, inputs)
    atomic_json(
        base / "launch-request.json",
        {
            "source_commit": inputs["source_commit"],
            "inputs_sha256": fingerprint(inputs),
            "split_step": split_step,
            "deadline": deadline,
            "compute_deadline": compute_deadline,
        },
    )
    current = "continuous"

    def stage(name):
        nonlocal current
        current = name
        if stop_requested() or time.time() >= deadline:
            raise InterruptedError("fixed pilot cycle stop")
        atomic_json(base / "status.json", {"stage": name, "complete": False})

    def launch(name, *, resume=False, steps=None):
        result = ports["launch"](
            root / "attempt.py",
            input_path,
            base / name,
            deadline=compute_deadline,
            resume=resume,
            max_new_steps=steps,
            stop_requested=stop_requested,
        )
        if result["fit"]["reason"] != (
            "complete" if steps is None else "max_new_steps"
        ):
            raise ValueError("partial child cannot complete a scientific cycle")
        return result

    def transfer(name, source, restore_name):
        folder = base / (name + "-archive")
        ports["pack"](source, folder)
        result = ports["transfer"](
            folder,
            base / (name + "-transfer"),
            base / restore_name,
            api=api,
            fetch=fetch,
            upload_budget=upload_budget,
            deadline=deadline,
        )
        if result["receipt"]["verified"] is not True or result["restored"] is not True:
            raise ValueError("HF roundtrip has not been verified")
        return result

    try:
        stage("continuous")
        full = launch("continuous")
        stage("interrupted")
        partial = launch("interrupted", steps=split_step)
        stage("intermediate-HF-roundtrip")
        intermediate = transfer("intermediate", base / "interrupted", "restored")
        stage("restored-continuation")
        resumed = launch("restored", resume=True)
        stage("exact-CUDA-parity")
        parity = ports["prove"](
            base / "continuous", base / "restored", total_updates=config.total_updates
        )
        if parity["verified"] is not True:
            raise ValueError("exact CUDA continuation is not verified")
        atomic_json(base / "resume-proof.json", parity)
        stage("final-HF-roundtrip")
        final = transfer("final", base / "continuous", "final-reconstruction")
        result = {
            "schema": "voxelshogi-research-pilot-cycle-v1",
            "source_commit": inputs["source_commit"],
            "inputs_sha256": fingerprint(inputs),
            "scientific_pilots": 1,
            "additional_independent_seeds": 0,
            "architecture": config.architecture.architecture,
            "continuous": full,
            "interrupted": partial,
            "resumed": resumed,
            "resume_proof": parity,
            "intermediate_transfer": intermediate,
            "final_transfer": final,
            "development_evaluation_executed": False,
            "final_holdout_evaluated": False,
            "scope": "One fixed-update scientific pilot plus an identical-trajectory control; count both in actual cost/updates, not as independent seeds. No teacher adoption, strength decision, development matches, final holdout or public inference completion claim.",
        }
        atomic_json(base / "complete.json", result)
        return result
    except BaseException as error:
        failure = {"stage": current, "error_type": type(error).__name__}
        atomic_json(base / "failure.json", failure)
        try:
            failure["recovery"] = recover_cycle(
                base,
                deadline=deadline,
                api=api,
                fetch=fetch,
                upload_budget=upload_budget,
                ports=ports,
                clock=time.time,
            )
        except BaseException as recovery_error:
            failure["recovery"] = {
                "states_preserved": False,
                "error_type": type(recovery_error).__name__,
                "host_retirement_authorized": False,
            }
        atomic_json(
            base / "failure.json",
            failure,
        )
        raise
