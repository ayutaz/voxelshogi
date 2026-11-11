"""Admitted Linux workflow: two pilots, selected-val diagnostics and48 audited games.

The provider-owning controller must collect the final ledgers/verified receipts
and retire its host. Neither learning nor this worker authorizes host deletion.
"""

import argparse
import json
import os
import signal
import sys
import threading
import time
from pathlib import Path

from infrastructure.research.pilot import job
from infrastructure.research.pilot.validation import development_protocol
from training.checkpoint import atomic_json
from training.evaluation_v2 import fingerprint
from training.feature_cache import file_hash
from training.state_upload_budget import upload_budget_limit

SCHEMA = "voxelshogi-research-pilot-workflow-v1"
RESULTS_REPO = "voxelshogi/voxelshogi-research-pilot-results-v1"


def validate_workflow(value, *, now):
    if (
        type(value) is not dict
        or set(value)
        != {"schema", "job", "m4_bundle", "development", "development_sha256"}
        or value["schema"] != SCHEMA
    ):
        raise ValueError("complete frozen pilot workflow required")
    configs = job.validate_job(value["job"], now=now)
    if [c.architecture.architecture for c in configs] != ["full", "geometry"]:
        raise ValueError("frozen Full/Geometry workflow required")
    development_protocol(
        value["development"],
        expected_sha256=value["development_sha256"],
        source_commit=value["job"]["source_commit"],
        weights_sha256="0" * 64,
    )
    proof = Path("docs/experiments/m4-production-release-2026-10-29.json")
    if proof.is_symlink() or not proof.is_file() or proof.stat().st_size > 4 * 1024**2:
        raise ValueError("committed M4 release proof required")
    trusted = json.loads(proof.read_text())["publication"]
    if trusted.get("complete") is not True or value["m4_bundle"] != {
        "plan": trusted["plan"],
        "receipt": trusted["receipt"],
    }:
        raise ValueError("M4 input differs from original production release")
    job.validate_bundle(value["m4_bundle"])
    return configs


def load_ports():
    from infrastructure.research.pilot.cycle import run_cycle
    from infrastructure.research.pilot.post import run_post
    from infrastructure.research.pilot.results import publish_results
    from infrastructure.research.pilot.validation import run_development_pair

    def learn(value, *, input_admission, **kwargs):
        def acquire(bundle, destination, **options):
            receipt = job.acquire_release(bundle, destination, **options)
            if destination.name == "input-screen":
                input_admission(destination)
            return receipt

        return job.run_job(
            value,
            ports={
                "source": job.check_source,
                "hardware": job.check_hardware,
                "acquire": acquire,
                "cycle": run_cycle,
            },
            **kwargs,
        )

    return {
        "source": job.check_source,
        "acquire": job.acquire_release,
        "learn": learn,
        "post": run_post,
        "develop": run_development_pair,
        "publish": publish_results,
    }


def verify_ledger(base, initial):
    final = json.loads((base / "state-upload-budget.json").read_text())
    upload_budget_limit(final)
    if {k: v for k, v in final.items() if k != "reservations"} != {
        k: v for k, v in initial.items() if k != "reservations"
    } or final["reservations"][: len(initial["reservations"])] != initial[
        "reservations"
    ]:
        raise ValueError("workflow state ledger history/cap changed")
    atomic_json(base / "state-budget-final.json", final)
    return fingerprint(final)


def run_workflow(
    value,
    *,
    api,
    fetch,
    ports=None,
    clock=time.time,
    stop_requested=lambda: False,
    before_publication=lambda: None,
):
    if sys.platform != "linux":
        raise ValueError("pilot workflow requires external Linux")
    configs = validate_workflow(value, now=clock())
    ports = load_ports() if ports is None else ports
    if set(ports) != {"source", "acquire", "learn", "post", "develop", "publish"}:
        raise ValueError("complete workflow ports required")
    frozen_job, frozen = value["job"], value["development"]
    base = Path(frozen_job["base"])
    if (
        base.is_symlink()
        or any(
            (base / n).exists() for n in ("workflow-request.json", "job-request.json")
        )
        or stop_requested()
    ):
        raise ValueError("existing/stopped workflow; reconnect rather than restart")
    budget = base / "state-upload-budget.json"
    if (
        budget.is_symlink()
        or not budget.is_file()
        or budget.stat().st_size > 1024**2
        or file_hash(budget) != frozen_job["state_upload_budget_sha256"]
    ):
        raise ValueError("workflow initial ledger differs")
    initial = json.loads(budget.read_text())
    upload_budget_limit(initial)
    ports["source"](frozen_job["source_commit"])
    identity = api.whoami()
    if identity.get("name") != "ayousanz" or not any(
        o.get("name") == "voxelshogi" for o in identity.get("orgs", [])
    ):
        raise ValueError("workflow HF identity differs")
    with (base / "workflow-request.json").open("x") as stream:
        json.dump({"workflow_sha256": fingerprint(value), "at": clock()}, stream)
    admitted = False

    def admit_screen(folder):
        nonlocal admitted
        path = folder / "config.json"
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size > 64 * 1024**2
        ):
            raise ValueError("bounded verified development screen required")
        screen = json.loads(path.read_text())
        actual = {
            "protocol": screen["protocols"]["legal-argmax-v1"],
            "families": screen["families"],
        }
        if actual != frozen or fingerprint(actual) != value["development_sha256"]:
            raise ValueError(
                "actual screen differs from prelearning development freeze"
            )
        admitted = True

    def boundary(stage):
        if stop_requested() or clock() >= frozen_job["compute_deadline"]:
            raise InterruptedError("fixed workflow compute boundary")
        atomic_json(
            base / "workflow-status.json", {"stage": stage, "pipeline_complete": False}
        )

    error, stage, diagnostics, learning, development = None, "M4-input", {}, None, None
    try:
        boundary(stage)
        m4_receipt = ports["acquire"](
            value["m4_bundle"],
            base / "input-m4",
            api=api,
            fetch=fetch,
            deadline=frozen_job["compute_deadline"],
        )
        if m4_receipt.get("verified") is not True:
            raise ValueError("full M4 immutable input verification required")
        atomic_json(base / "m4-input-receipt.json", m4_receipt)
        stage = "learning"
        boundary(stage)
        learning = ports["learn"](
            frozen_job,
            api=api,
            fetch=fetch,
            input_admission=admit_screen,
            clock=clock,
            stop_requested=stop_requested,
        )
        if (
            not admitted
            or learning.get("schema") != "voxelshogi-research-pilot-learning-result-v1"
            or learning.get("learning_complete") is not True
            or learning.get("scientific_pilots") != 2
            or learning.get("additional_independent_seeds") != 0
            or learning.get("job_sha256") != fingerprint(frozen_job)
            or learning.get("source_commit") != frozen_job["source_commit"]
        ):
            raise ValueError(
                "complete frozen learning and prefit screen admission required"
            )
        for inputs, config in zip(frozen_job["inputs"], configs, strict=True):
            name = config.architecture.architecture
            stage = "diagnostic-" + name
            boundary(stage)
            result = ports["post"](
                inputs,
                base / name / "continuous",
                base / name / "diagnostics",
                deadline=frozen_job["compute_deadline"],
                clock=clock,
                stop_requested=stop_requested,
            )
            if (
                result.get("schema") != "voxelshogi-research-pilot-diagnostic-v1"
                or result.get("source_commit") != frozen_job["source_commit"]
                or result.get("architecture") != name
                or result.get("inputs_sha256") != fingerprint(inputs)
                or result.get("test_features_encoded") != 0
                or result.get("final_holdout_evaluated") is not False
            ):
                raise ValueError("diagnostic escaped fixed model/source/val inputs")
            diagnostics[name] = result
        stage = "development48"
        boundary(stage)
        development = ports["develop"](
            frozen,
            {k: v["selection"] for k, v in diagnostics.items()},
            base / "development",
            expected_sha256=value["development_sha256"],
            source_commit=frozen_job["source_commit"],
            corpus=base / "input-m4/production-64",
            selfplay=base / "input-selfplay",
            selfplay_protocol=frozen_job["selfplay_protocol"],
            protection=base / "input-protection/config.json",
            deadline=frozen_job["compute_deadline"],
            clock=clock,
            stop_requested=stop_requested,
        )
        if (
            development.get("schema") != "voxelshogi-research-pilot-development-v1"
            or development.get("games") != 48
            or development.get("leakage_free") is not True
            or development.get("source_commit") != frozen_job["source_commit"]
            or development.get("frozen_development_sha256")
            != value["development_sha256"]
            or development.get("final_holdout_evaluated") is not False
        ):
            raise ValueError("complete audited frozen48 games required")
        boundary("compute-complete")
        verify_ledger(base, initial)
    except BaseException as caught:
        error = caught
        atomic_json(
            base / "workflow-failure.json",
            {
                "stage": stage,
                "error_type": type(caught).__name__,
                "pipeline_complete": False,
                "host_retirement_authorized": False,
            },
        )
    atomic_json(
        base / "workflow-compute.json",
        {
            "pipeline_complete": error is None,
            "source_commit": frozen_job["source_commit"],
            "learning": learning,
            "diagnostics": diagnostics,
            "development": development,
            "final_holdout_evaluated": False,
        },
    )
    try:
        ledger_sha = verify_ledger(base, initial)
    except BaseException as caught:
        error = error or caught
        ledger_sha = None
        # Preserve an observed invalid ledger for diagnosis; never validate it.
        atomic_json(
            base / "state-budget-final.json",
            {"verified": False, "error_type": type(caught).__name__},
        )
        atomic_json(
            base / "workflow-failure.json",
            {
                "stage": "ledger",
                "error_type": type(error).__name__,
                "pipeline_complete": False,
                "host_retirement_authorized": False,
            },
        )
    try:
        before_publication()
        if clock() >= frozen_job["transfer_deadline"]:
            raise InterruptedError("fixed workflow transfer deadline")
        publication = ports["publish"](
            value,
            base,
            pipeline_complete=error is None,
            api=api,
            fetch=fetch,
            deadline=frozen_job["transfer_deadline"],
        )
        if (
            publication.get("receipt", {}).get("verified") is not True
            or publication["receipt"].get("repo_id") != RESULTS_REPO
            or publication.get("pipeline_complete") is not (error is None)
        ):
            raise ValueError("fixed verified results publication required")
        atomic_json(base / "workflow-publication.json", publication)
        if stop_requested() or clock() >= frozen_job["transfer_deadline"]:
            raise InterruptedError("workflow stopped at transfer completion")
    except BaseException as caught:
        atomic_json(
            base / "workflow-failure.json",
            {
                "stage": "publication",
                "error_type": type(caught).__name__,
                "pipeline_complete": False,
                "host_retirement_authorized": False,
            },
        )
        raise
    if error is not None:
        raise error
    result = {
        "schema": "voxelshogi-research-pilot-workflow-result-v1",
        "pipeline_complete": True,
        "source_commit": frozen_job["source_commit"],
        "workflow_sha256": fingerprint(value),
        "publication": publication,
        "state_budget_final_sha256": ledger_sha,
        "scientific_pilots": 2,
        "games": 48,
        "final_holdout_evaluated": False,
        "general_strength_improvement_established": False,
        "host_retirement_authorized": False,
        "controller_ledger_collection_required": True,
    }
    atomic_json(base / "workflow-complete.json", result)
    return result


def main():
    if sys.platform != "linux":
        raise ValueError("pilot workflow requires external Linux")
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("workflow", type=Path)
    args = parser.parse_args()
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    value = json.loads(args.workflow.read_text())
    validate_workflow(value, now=time.time())
    if any(os.environ.get(k) for k in ("VAST_API_KEY", "CLOUDRIFT_API_KEY")):
        raise ValueError("provider credentials must remain on controller")
    token = os.environ.pop("HF_TOKEN")
    from httpx2 import TransportError
    from huggingface_hub import HfApi, hf_hub_download
    from huggingface_hub.utils import build_hf_headers, get_session

    from training.hub_recovery import RecoveryApi
    from training.hub_release import PublicationApi

    stop, done, rows = threading.Event(), threading.Event(), []
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    api = RecoveryApi(
        PublicationApi(
            HfApi(endpoint="https://huggingface.co", token=token),
            get_session(),
            build_hf_headers(token=token),
        ),
        deadline=value["job"]["transfer_deadline"],
        transient_errors=(TimeoutError, ConnectionError, TransportError),
    )

    def fetch(**kwargs):
        return hf_hub_download(**kwargs, token=token)

    base = Path(value["job"]["base"])
    observer = threading.Thread(
        target=job.observe_resources,
        args=(value["job"]["maximum_owned_rss_bytes"], stop, done, rows),
        daemon=True,
    )
    observer.start()
    result = None
    try:
        result = run_workflow(
            value,
            api=api,
            fetch=fetch,
            stop_requested=stop.is_set,
            before_publication=lambda: atomic_json(
                base / "resource-samples.json", list(rows)
            ),
        )
    finally:
        done.set()
        observer.join(timeout=12)
        atomic_json(base / "resource-samples-final.json", rows)
        atomic_json(
            base / "workflow-worker-finished.json",
            {
                "pipeline_complete": result is not None,
                "source_commit": value["job"]["source_commit"],
                "observer_stopped": not observer.is_alive(),
                "controller_ledger_collection_required": True,
                "host_retirement_authorized": False,
            },
        )
    print(
        json.dumps(
            {
                "pipeline_complete": True,
                "source_commit": result["source_commit"],
                "controller_collection_required": True,
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except BaseException as error:
        print(
            json.dumps(
                {"pipeline_complete": False, "error_type": type(error).__name__}
            ),
            flush=True,
        )
        sys.exit(1)
