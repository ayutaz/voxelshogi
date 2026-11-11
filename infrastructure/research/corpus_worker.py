"""One fixed P6 real-corpus admission audit with Linux-direct, hash-pinned HF evidence."""

# ruff: noqa: E402
import concurrent.futures
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

assert sys.platform == "linux"
assert not any(os.environ.get(k) for k in ("VAST_API_KEY", "CLOUDRIFT_API_KEY"))

import runpy

from httpx2 import TransportError
from huggingface_hub import HfApi, hf_hub_download
from huggingface_hub.utils import build_hf_headers, get_session

from training.checkpoint import atomic_json
from training.evaluation_v2 import fingerprint
from training.feature_cache import file_hash
from training.hub_recovery import RecoveryApi
from training.hub_release import (
    PublicationApi,
    create_release_repository,
    plan_release,
    publish_release,
    verify_release,
)

BASE = Path("runs/p6/research-browser/corpus")
W = json.loads((BASE / "workload.json").read_text())
SOURCE = W["source_commit"]
INPUTS = {}
END = json.loads((BASE / "deadline.json").read_text())["maximum_end_at"]
COMPUTE_END, TRANSFER_END = END - 2160, END - 1260
REPO = "voxelshogi/voxelshogi-research-pilot-admission-v1"
TOKEN = os.environ.pop("HF_TOKEN")
STOP, OBSERVER_DONE = threading.Event(), threading.Event()
START = time.monotonic()
CURRENT = "preflight"
TIMINGS, RESOURCE_ROWS = {}, []
API = REPORT = RECEIPT = None
signal.signal(signal.SIGTERM, lambda *_: STOP.set())
signal.signal(signal.SIGINT, lambda *_: STOP.set())


def stopping():
    return STOP.is_set() or time.time() >= COMPUTE_END


def stage(name):
    global CURRENT
    CURRENT = name
    atomic_json(
        BASE / "job-status.json",
        {
            "stage": name,
            "complete": False,
            "source_commit": SOURCE,
            "elapsed_seconds": time.monotonic() - START,
        },
    )
    print(json.dumps({"stage": name}), flush=True)
    return time.monotonic()


def observe():
    import psutil

    process = psutil.Process()
    while not OBSERVER_DONE.is_set():
        row = {"elapsed_seconds": time.monotonic() - START, "stage": CURRENT}
        try:
            processes = [process, *process.children(recursive=True)]
            row["summed_owned_rss_bytes"] = sum(
                p.memory_info().rss for p in processes if p.is_running()
            )
            row["owned_cpu_seconds"] = sum(
                sum(p.cpu_times()[:2]) for p in processes if p.is_running()
            )
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=memory.used,utilization.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
            values = [int(v.strip()) for v in result.stdout.strip().split(",")]
            assert len(values) == 2
            row.update(
                gpu_device_memory_used_mib=values[0], gpu_utilization_percent=values[1]
            )
            if row["summed_owned_rss_bytes"] > W["maximum_owned_rss_bytes"]:
                row["stop_reason"] = "owned-rss-limit"
                STOP.set()
            if time.time() >= COMPUTE_END:
                row["stop_reason"] = "fixed-compute-deadline"
                STOP.set()
        except Exception as error:
            row["observer_error_type"] = type(error).__name__
        RESOURCE_ROWS.append(row)
        OBSERVER_DONE.wait(10)


def describe(folder, path):
    return {
        "path": str(path.relative_to(folder)),
        "bytes": path.stat().st_size,
        "sha256": file_hash(path),
    }


# This fragment is embedded into the external worker, never executed on Mac.
def acquire_release(label):
    plan = json.loads((BASE / f"{label}-plan.json").read_text())
    receipt = json.loads((BASE / f"{label}-receipt.json").read_text())
    assert fingerprint(plan) == receipt["release_sha256"]
    assert receipt["verified"] and receipt["community_disabled"]
    source = BASE / f"input-{label}"
    source.mkdir(exist_ok=False)

    def fetch_file(entry):
        if stopping():
            raise InterruptedError("fixed corpus acquisition boundary")
        name = Path(entry["path"])
        assert not name.is_absolute() and ".." not in name.parts
        path = Path(
            hf_hub_download(
                repo_id=receipt["repo_id"],
                repo_type="dataset",
                revision=receipt["hub_commit"],
                filename=entry["path"],
                token=TOKEN,
            )
        )
        assert (
            path.stat().st_size == entry["bytes"] and file_hash(path) == entry["sha256"]
        )
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        assert (
            target.stat().st_size == entry["bytes"]
            and file_hash(target) == entry["sha256"]
        )
        return entry["path"], target

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        paths = dict(pool.map(fetch_file, plan["files"]))
    receipt = verify_release(plan, receipt, API, lambda **kw: paths[kw["filename"]])
    INPUTS[label] = {"plan": plan, "receipt": receipt}
    atomic_json(BASE / f"{label}-verified.json", receipt)
    return source


# This fragment is embedded into the external worker, never executed on Mac.
def publish_corpus(report, failure):
    if time.time() >= TRANSFER_END:
        raise InterruptedError("fixed corpus transfer boundary")
    assert not (BASE / "publication-attempt.json").exists(), (
        "audit an existing request instead of resending"
    )
    folder = BASE / "publication"
    folder.mkdir(exist_ok=False)
    import pyarrow as pa
    import pyarrow.parquet as pq

    diagnosis = BASE / "diagnosis"
    admission_path = diagnosis / "admission.json"
    admission = (
        json.loads(admission_path.read_text()) if admission_path.is_file() else None
    )
    selected = (
        {i: s for s, ids in admission["admission"]["selected_ids"].items() for i in ids}
        if admission
        else {}
    )
    rows = (
        [
            {**r, "split": selected.get(r["id"]), "selected": r["id"] in selected}
            for r in admission["metadata"]
        ]
        if admission
        else []
    )
    schema = pa.schema(
        [
            ("id", pa.string()),
            ("family", pa.string()),
            ("input", pa.string()),
            ("value_kind", pa.string()),
            ("ply", pa.int64()),
            ("split", pa.string()),
            ("selected", pa.bool_()),
        ],
        metadata={b"schema_id": b"voxelshogi-research-pilot-admission-rows-v1"},
    )
    table = pa.Table.from_pylist(rows, schema=schema)
    pq.write_table(
        table, folder / "admission.parquet", compression="zstd", version="2.6"
    )
    assert pq.read_table(folder / "admission.parquet").equals(
        table, check_metadata=True
    )
    records = {}
    for name in (
        "admission.json",
        "development-protection.json",
        "target-diagnosis.json",
        "result.json",
    ):
        path = diagnosis / name
        if path.is_file():
            assert path.stat().st_size < 32 * 1024**2
            records[name] = json.loads(path.read_text())
    manifest = {
        "schema": "voxelshogi-research-pilot-admission-release-v1",
        "source_commit": SOURCE,
        "report": report,
        "failure": failure,
        "inputs": INPUTS,
        "diagnosis_records": records,
        "raw_rows": len(rows),
        "selected_rows": sum(r["selected"] for r in rows),
        "workload": W,
        "timings_seconds": dict(TIMINGS),
        "resource_samples_before_publication": list(RESOURCE_ROWS),
        "execution_source": {
            name: (BASE / name).read_text()
            for name in ("worker.py", "inspect-corpus.py")
        },
        "scope": "Candidate metadata admission, full development-input protection and target diagnosis only. Not teacher-quality adoption, features, training or playing-strength evidence.",
    }
    assert TOKEN not in json.dumps(manifest)
    atomic_json(folder / "manifest.json", manifest)
    atomic_json(
        folder / "config.json",
        {"source_commit": SOURCE, "inputs": INPUTS, "workload": W},
    )
    atomic_json(
        folder / "validation.json",
        {
            "source_all_files_verified": len(INPUTS) == 3,
            "diagnosis_complete": report is not None and failure is None,
            "usable_counts": report.get("usable_counts", False) if report else False,
            "teacher_quality_accepted": False,
            "training_executed": False,
            "raw_rows": len(rows),
            "failure": failure,
        },
    )
    shutil.copyfile(BASE / "cc-by-4.0.txt", folder / "LICENSE")
    shutil.copyfile("LICENSE", folder / "NOTICE")
    counts = admission["admission"]["rows_by_split"] if admission else {}
    (folder / "README.md").write_text(
        "---\nlicense: cc-by-4.0\nconfigs:\n- config_name: candidate-admission\n  data_files:\n  - split: audit\n    path: admission.parquet\n---\n# VoxelShogi research pilot admission diagnosis\n\n"
        "## Generation and provenance\n"
        f"Audit source `{SOURCE}`. The three original gated input repositories and immutable revisions, full release plans/hashes and settings verification are in config.json. No new games or models were generated. Actual source metadata rows {len(rows)}, selected rows {sum(r['selected'] for r in rows)}, selected role counts {json.dumps(counts, sort_keys=True)}. Partial failures retain their failure type and available rows; do not infer a completed diagnosis from row existence.\n\n"
        "## Usage and schema\n"
        "Read admission.parquet: id, family (canonical opening input), input (canonical sample input), value_kind (terminal-v1/bootstrap-v1), absolute ply, selected and nullable split (train/val/test for selected IDs). The HF audit split is a file-layout label, not model training data. The exact indices/selection hash, all counts and duplicate/protected exclusions are in manifest.json diagnosis_records admission entry. Only a complete result record and failure-free manifest prove completed diagnosis. Counts alone do not admit teachers for training.\n\n"
        "## Verification\n"
        "A completed diagnosis requires all fixed input release files to be verified on external Linux, all source episodes and labels replay/schema-checked through Rust, frozen24 roots checked, and all24579 actual development queries and48 scored games replayed to protect the full18121-input development set. Partial/failure releases do not prove completion of those steps; inspect validation.json and manifest.report/failure. Legacy protection is not reduced. All source hashes are checked again after diagnosis. Whole opening families are assigned with seed67011 before train/val/test selection; duplicates follow the recorded test>val>train policy. Target entropy/support/visits and terminal/bootstrap origins are counted without converting cutoff into draw. Validation/test derived from data already used by S are not an unseen S test. No final-holdout model queries, feature cache or training. Fixed output revision and every output byte hash are verified before host retirement.\n\n"
        "## Access and license\n"
        "CC-BY-4.0 candidate metadata and diagnosis, VoxelShogi contributors, derived from the attributed fixed input datasets listed in config.json. Embedded execution source is Apache-2.0 (NOTICE). Public/manual download approval, Community disabled. Preserve source revisions and all hashes with attribution. No model weights, optimizer payloads, provider keys or HF credentials are included.\n"
    )
    plan = plan_release(
        folder,
        repo_id=REPO,
        repo_type="dataset",
        license_id="cc-by-4.0",
        license_approved=True,
        source_commit=SOURCE,
    )
    atomic_json(BASE / "publication-plan.json", plan)
    atomic_json(
        BASE / "publication-attempt.json",
        {"at": time.time(), "files": len(plan["files"])},
    )
    receipt = publish_release(folder, plan, API, execute=True)
    atomic_json(BASE / "publication-receipt.json", receipt)

    def fetch_file(entry):
        if time.time() >= TRANSFER_END:
            raise InterruptedError("fixed corpus output all-hash boundary")
        path = Path(
            hf_hub_download(
                repo_id=REPO,
                repo_type="dataset",
                revision=receipt["hub_commit"],
                filename=entry["path"],
                token=TOKEN,
            )
        )
        assert (
            path.stat().st_size == entry["bytes"] and file_hash(path) == entry["sha256"]
        )
        return entry["path"], path

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        paths = dict(pool.map(fetch_file, plan["files"]))
    receipt = verify_release(plan, receipt, API, lambda **kw: paths[kw["filename"]])
    atomic_json(BASE / "publication-receipt.json", receipt)
    return receipt


observer = threading.Thread(target=observe, daemon=True)
observer.start()
error_record = None
try:
    assert (
        subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        == SOURCE
    )
    assert not subprocess.check_output(["git", "status", "--porcelain"], text=True)
    assert W["stage"] == "research-corpus" and W["admitted"] is True
    assert W["parent_run_label"] == json.loads((BASE / "owner.json").read_text())["tag"]
    for name, digest in W["files"].items():
        assert file_hash(BASE / name) == digest
    raw_api = HfApi(endpoint="https://huggingface.co", token=TOKEN)
    candidate = RecoveryApi(
        PublicationApi(raw_api, get_session(), build_hf_headers(token=TOKEN)),
        deadline=TRANSFER_END,
        transient_errors=(TimeoutError, ConnectionError, TransportError),
        wait=STOP.wait,
        stop_requested=STOP.is_set,
        observe=lambda event: stage("hf-" + event["operation"]),
    )
    who = candidate.whoami()
    assert who["name"] == "ayousanz" and any(
        o.get("name") == "voxelshogi" for o in who.get("orgs", [])
    )
    API = candidate
    create_release_repository(
        {
            "schema": 1,
            "repo_id": REPO,
            "repo_type": "dataset",
            "private": False,
            "gated": "manual",
            "license": "cc-by-4.0",
            "license_approved": True,
            "source_commit": SOURCE,
        },
        API,
        execute=True,
    )
    atomic_json(
        BASE / "hf-preflight.json",
        {
            "auth_user": who["name"],
            "repo_id": REPO,
            "public_manual_community_off": True,
        },
    )
    begin = stage("fixed-three-HF-releases")
    for label in ("selfplay", "protection", "screen"):
        acquire_release(label)
    TIMINGS[CURRENT] = time.monotonic() - begin
    if stopping():
        raise InterruptedError("fixed corpus preparation boundary")
    begin = stage("full-corpus-and-development-replay-diagnosis")
    module = runpy.run_path(str(BASE / "inspect-corpus.py"))
    REPORT = module["inspect"](
        BASE / "input-selfplay",
        BASE / "selfplay-protocol.json",
        BASE / "input-protection/config.json",
        BASE / "input-screen",
        BASE / "diagnosis",
        stop_requested=stopping,
    )
    actual_admission = json.loads((BASE / "diagnosis/admission.json").read_text())
    assert actual_admission["source_generations"] == W["expected_source_generations"]
    assert len(actual_admission["metadata"]) == W["expected_source_samples"]
    atomic_json(
        BASE / "admission-summary.json",
        {
            "source_commit": SOURCE,
            "admission_sha256": REPORT["admission_sha256"],
            "source_generations": actual_admission["source_generations"],
            "source_episodes": actual_admission["source_episodes"],
            **{
                key: actual_admission["admission"][key]
                for key in (
                    "counts",
                    "rows_by_split",
                    "retained_families_by_split",
                    "assigned_families_by_split",
                    "value_origins",
                    "absolute_ply_bins",
                    "overlaps_by_protection_role",
                    "selection_sha256",
                    "minimum_rows",
                    "usable_for_pilot",
                )
            },
            "scope": "Small metadata only; no raw samples, IDs, features or model payloads relayed to controller.",
        },
    )
    atomic_json(BASE / "audit-result.json", REPORT)
    TIMINGS[CURRENT] = time.monotonic() - begin
except BaseException as error:
    error_record = {
        "complete": False,
        "stage": CURRENT,
        "error_type": type(error).__name__,
        "elapsed_seconds": time.monotonic() - START,
    }
    atomic_json(BASE / "failure.json", error_record)

finally:
    try:
        if API is not None and time.time() < TRANSFER_END:
            begin = stage("publish-corpus-diagnosis-and-all-hash")
            RECEIPT = publish_corpus(REPORT, error_record)
            TIMINGS[CURRENT] = time.monotonic() - begin
        if (
            error_record is None
            and REPORT is not None
            and REPORT["teacher_quality_accepted"] is False
            and REPORT["training_executed"] is False
            and RECEIPT
            and RECEIPT["verified"]
        ):
            atomic_json(
                BASE / "complete.json",
                {
                    "complete": True,
                    "usable_counts": REPORT["usable_counts"],
                    "admission_sha256": REPORT["admission_sha256"],
                    "teacher_quality_accepted": False,
                    "training_executed": False,
                    "source_commit": SOURCE,
                    "publication_receipt": RECEIPT,
                    "timings_seconds": TIMINGS,
                    "elapsed_seconds": time.monotonic() - START,
                    "resource_release_pending_controller": True,
                },
            )
        elif error_record is None:
            atomic_json(
                BASE / "failure.json",
                {
                    "complete": False,
                    "stage": CURRENT,
                    "error_type": "CorpusAuditOrPublicationIncomplete",
                    "elapsed_seconds": time.monotonic() - START,
                },
            )
    except BaseException as error:
        atomic_json(
            BASE / "partial-publication-failure.json",
            {"complete": False, "error_type": type(error).__name__, "stage": CURRENT},
        )
    OBSERVER_DONE.set()
    observer.join(timeout=12)
    atomic_json(BASE / "resource-samples.json", RESOURCE_ROWS)
    atomic_json(
        BASE / "resource-summary.json",
        {
            "samples": len(RESOURCE_ROWS),
            "peak_summed_owned_rss_bytes": max(
                (r.get("summed_owned_rss_bytes", 0) for r in RESOURCE_ROWS), default=0
            ),
            "elapsed_seconds": time.monotonic() - START,
        },
    )
    atomic_json(
        BASE / "worker-finished.json",
        {"at": time.time(), "complete": (BASE / "complete.json").exists()},
    )
