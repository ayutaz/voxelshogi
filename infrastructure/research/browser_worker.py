"""One fixed P6 real-browser operator probe with Linux-direct, hash-pinned HF evidence."""

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
from training.research_browser_inputs import prepare_inputs

BASE = Path("runs/p6/research-browser")
W = json.loads((BASE / "workload.json").read_text())
SOURCE = W["source_commit"]
INPUT_PLAN = json.loads((BASE / "input-model-plan.json").read_text())
INPUT_RECEIPT = json.loads((BASE / "input-model-receipt.json").read_text())
END = json.loads((BASE / "deadline.json").read_text())["maximum_end_at"]
COMPUTE_END, TRANSFER_END = END - 2160, END - 1260
REPO = "voxelshogi/voxelshogi-research-browser-v1"
TOKEN = os.environ.pop("HF_TOKEN")
STOP, OBSERVER_DONE = threading.Event(), threading.Event()
START = time.monotonic()
CURRENT = "preflight"
TIMINGS, RESOURCE_ROWS = {}, []
API = REPORT = RECEIPT = CORPUS_RESULT = None
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


def observe_hf(event):
    # Operation names and attempt numbers only: never exception strings, URLs,
    # authentication headers, account payloads or credential values.
    stage("hf-" + event["operation"])
    atomic_json(BASE / "hf-operation.json", event)


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


def acquire_models():
    """Verify all 17 frozen release files, directly from HF to external Linux."""
    assert fingerprint(INPUT_PLAN) == INPUT_RECEIPT["release_sha256"]
    assert INPUT_RECEIPT["verified"] and INPUT_RECEIPT["community_disabled"]
    assert INPUT_RECEIPT["hub_commit"] == W["input_model_revision"]
    source = BASE / "input-release"
    source.mkdir(exist_ok=False)
    paths = {}

    def fetch_file(entry):
        if stopping():
            raise InterruptedError("fixed model acquisition boundary")
        name = Path(entry["path"])
        assert not name.is_absolute() and ".." not in name.parts
        path = Path(
            hf_hub_download(
                repo_id=INPUT_RECEIPT["repo_id"],
                repo_type="model",
                revision=INPUT_RECEIPT["hub_commit"],
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
        for name, path in pool.map(fetch_file, INPUT_PLAN["files"]):
            paths[name] = path
    receipt = verify_release(
        INPUT_PLAN, INPUT_RECEIPT, API, lambda **kw: paths[kw["filename"]]
    )
    atomic_json(
        BASE / "input-verification.json",
        {
            **receipt,
            "verified_files": len(paths),
            "downloaded_bytes": sum(f["bytes"] for f in INPUT_PLAN["files"]),
        },
    )
    return source, receipt


def measure_browser(inputs):
    import psutil

    env = dict(os.environ)
    assert not any(
        env.get(k) for k in ("HF_TOKEN", "VAST_API_KEY", "CLOUDRIFT_API_KEY")
    )
    env["PATH"] = (
        "/root/.local/share/voxelshogi-node/bin:/root/.local/bin:" + env["PATH"]
    )
    env["PW_CHANNEL"] = ""
    target = BASE / "browser-output/result.json"
    target.parent.mkdir(exist_ok=False)
    with (BASE / "browser.log").open("xb") as log:
        child = subprocess.Popen(
            ["node", "scripts/research-browser-probe.mjs", str(inputs), str(target)],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        atomic_json(
            BASE / "browser-launch.json",
            {
                "pid": child.pid,
                "create_time": psutil.Process(child.pid).create_time(),
                "at": time.time(),
            },
        )
        while child.poll() is None:
            if stopping():
                # Terminate only this owned process group. The independent host
                # deadline remains armed if any descendant cannot be observed.
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=10)
                raise InterruptedError("fixed browser compute/RSS boundary")
            STOP.wait(10)
    if not target.is_file():
        raise RuntimeError("browser did not produce a measurement record")
    assert target.stat().st_size < 4 * 1024**2
    report = json.loads(target.read_text())
    assert report["application_commit"] == SOURCE
    assert report["origin"]["revision"] == INPUT_RECEIPT["hub_commit"]
    report["controller_exit_code"] = child.returncode
    return report


# Embedded into the admitted external browser worker.
def run_corpus_child():
    """Reuse this owned, deadline-bound host; never reserve another resource."""
    import psutil

    base = BASE / "corpus"
    w = json.loads((base / "workload.json").read_text())
    assert w["parent_run_label"] == W["run_label"]
    assert w["source_commit"] == SOURCE and w["stage"] == "research-corpus"
    for name, digest in w["files"].items():
        assert file_hash(base / name) == digest
    for name in ("deadline.json", "owner.json", "host-admission.json"):
        shutil.copyfile(BASE / name, base / name)
    assert not (base / "job-launch-request.json").exists()
    atomic_json(
        base / "job-launch-request.json", {"at": time.time(), "source_commit": SOURCE}
    )
    env = {**os.environ, "HF_TOKEN": TOKEN}
    assert not any(env.get(k) for k in ("VAST_API_KEY", "CLOUDRIFT_API_KEY"))
    with (base / "job.log").open("xb") as log:
        child = subprocess.Popen(
            [sys.executable, "-u", str(base / "worker.py")],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        atomic_json(
            base / "job-launch.json",
            {
                "pid": child.pid,
                "create_time": psutil.Process(child.pid).create_time(),
                "at": time.time(),
            },
        )
        while child.poll() is None:
            if stopping():
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=10)
                raise InterruptedError("shared-host corpus compute/RSS boundary")
            STOP.wait(10)
    assert child.returncode == 0 and (base / "worker-finished.json").is_file()
    assert (base / "complete.json").is_file(), (
        "inspect retained corpus failure; never restart"
    )
    result = json.loads((base / "complete.json").read_text())
    assert result["complete"] and result["source_commit"] == SOURCE
    assert (
        result["teacher_quality_accepted"] is False
        and result["training_executed"] is False
    )
    plan = json.loads((base / "publication-plan.json").read_text())
    receipt = result["publication_receipt"]
    assert fingerprint(plan) == receipt["release_sha256"]
    assert receipt["repo_id"] == "voxelshogi/voxelshogi-research-pilot-admission-v1"

    def fetch(**kwargs):
        if time.time() >= TRANSFER_END:
            raise InterruptedError("shared-host corpus verification boundary")
        return hf_hub_download(**kwargs, token=TOKEN)

    result["publication_receipt"] = verify_release(plan, receipt, API, fetch)
    result["shared_parent_run_label"] = W["run_label"]
    result["new_resource_or_budget_reservation"] = False
    atomic_json(BASE / "corpus-audit-complete.json", result)
    return result


def write_measurement_rows(path, rows):
    import pyarrow as pa
    import pyarrow.parquet as pq

    schema = pa.schema(
        [
            ("architecture", pa.string()),
            ("backend", pa.string()),
            ("status", pa.string()),
            ("measurement_json", pa.string()),
        ],
        metadata={b"schema_id": b"voxelshogi-research-browser-rows-v1"},
    )
    pq.write_table(
        pa.Table.from_pylist(rows, schema=schema),
        path,
        version="2.6",
        compression="zstd",
    )
    actual = pq.read_table(path)
    assert actual.schema.equals(schema, check_metadata=True)
    assert actual.to_pylist() == rows


def review_report(report):
    """Independent matrix/output/provider checks before accepting a unit."""
    import math

    names = {"full", "axial", "geometry", "cnn"}
    rows = report["rows"]
    expected = {(n, b) for n in names for b in ("wasm", "webgpu")}
    actual = [(r["name"], r["backend"]) for r in rows]
    if (
        len(actual) != 8
        or set(actual) != expected
        or report.get("matrix_complete") is not True
    ):
        raise ValueError("browser matrix incomplete or repeated")
    if report["method"]["numeric"] != {
        "policy_atol": 1e-4,
        "policy_rtol": 1e-4,
        "value_atol": 1e-5,
        "value_rtol": 1e-5,
    }:
        raise ValueError("browser numeric contract differs")
    passed = {"wasm": set(), "webgpu": set()}
    for row in rows:
        if row["status"] == "failed":
            continue
        if row["status"] != "success" or row.get("session_released") is not True:
            raise ValueError("browser case is not terminal/released")
        backend = row["backend"]
        profile = row["profile"]
        provider = (
            "CPUExecutionProvider" if backend == "wasm" else "WebGpuExecutionProvider"
        )
        if (
            set(profile["providers"]) != {provider}
            or any(type(n) is not int or n <= 0 for n in profile["providers"].values())
            or not profile["operators"]
            or any(type(n) is not int or n <= 0 for n in profile["operators"].values())
        ):
            raise ValueError("browser provider placement not verified")
        if row["information"]["backend"] != backend:
            raise ValueError("browser backend differs")
        if backend == "webgpu":
            adapter = row["information"]["adapter"]
            text = (
                " ".join(str(v) for v in adapter.values())
                if type(adapter) is dict
                else ""
            )
            if not text.strip() or any(
                name in text.lower()
                for name in ("swiftshader", "llvmpipe", "lavapipe", "software")
            ):
                raise ValueError("browser hardware identity not verified")
        if [f["id"] for f in row["fixtures"]] != [0, 3]:
            raise ValueError("browser frozen fixtures differ")
        for fixture in row["fixtures"]:
            if (
                fixture["warmup_steps"] != 8
                or len(fixture["samples_ms"]) != 32
                or fixture.get("legal_argmax_equal") is not True
                or any(
                    type(v) not in (int, float) or not math.isfinite(v) or v < 0
                    for v in fixture["samples_ms"]
                )
            ):
                raise ValueError("browser measured work/argmax differs")
            for name, elements in (("policy", 1067985), ("value", 1)):
                c = fixture["comparisons"][name]
                if (
                    c["elements"] != elements
                    or c["exceeded"] != 0
                    or type(c["max_abs"]) not in (int, float)
                    or not math.isfinite(c["max_abs"])
                    or c["max_abs"] < 0
                ):
                    raise ValueError("browser full-vector comparison failed")
        passed[backend].add(row["name"])
    for backend in passed:
        reported = report[backend + "_supported"]
        if len(reported) != len(passed[backend]) or set(reported) != passed[backend]:
            raise ValueError("browser support list differs from measured rows")
    if report.get("complete") is not all(r["status"] == "success" for r in rows):
        raise ValueError("browser completion contradicts rows")
    return {
        "matrix_complete": True,
        "wasm_verified": len(passed["wasm"]),
        "webgpu_verified": len(passed["webgpu"]),
        "all_backends_passed": report["complete"],
    }


def publish_browser(report, failure):
    if time.time() >= TRANSFER_END:
        raise InterruptedError("fixed browser transfer boundary")
    assert not (BASE / "publication-attempt.json").exists(), (
        "inspect an existing attempt instead of resending"
    )
    folder = BASE / "publication"
    folder.mkdir(exist_ok=False)
    observations = report.get("rows", []) if report else []
    rows = [
        {
            "architecture": r.get("name"),
            "backend": r.get("backend"),
            "status": r.get("status"),
            "measurement_json": json.dumps(r, sort_keys=True, allow_nan=False),
        }
        for r in observations
    ]
    if not rows:
        rows = [
            {
                "architecture": None,
                "backend": None,
                "status": "worker-failed",
                "measurement_json": json.dumps(
                    failure or {"error_type": "NoMeasuredCases"}, sort_keys=True
                ),
            }
        ]
    write_measurement_rows(folder / "measurements.parquet", rows)
    manifest = {
        "schema": "voxelshogi-research-browser-release-v1",
        "source_commit": SOURCE,
        "trained": False,
        "input_release": INPUT_RECEIPT,
        "input_plan_sha256": fingerprint(INPUT_PLAN),
        "report": report,
        "failure": failure,
        "case_rows": len(observations),
        "parquet_rows": len(rows),
        "workload": W,
        "timings_seconds": dict(TIMINGS),
        "resource_samples_before_publication": list(RESOURCE_ROWS),
        "host_admission": json.loads((BASE / "host-admission.json").read_text()),
        "execution_source": (BASE / "worker.py").read_text(),
        "scope": "Untrained real-M operator browser measurements, all negatives retained; not teacher training, game strength, arena rendering, physical mobile or Phase7 evidence.",
    }
    assert TOKEN not in json.dumps(manifest)
    atomic_json(folder / "manifest.json", manifest)
    atomic_json(
        folder / "config.json",
        {
            "input_plan": INPUT_PLAN,
            "input_receipt": INPUT_RECEIPT,
            "source_commit": SOURCE,
            "warmup_steps": 8,
            "measured_steps": 32,
        },
    )
    atomic_json(
        folder / "validation.json",
        {
            "input_all_files_hash_verified": (
                BASE / "input-verification.json"
            ).exists(),
            "matrix_complete": bool(report and report.get("matrix_complete")),
            "all_backends_passed": bool(report and report.get("complete")),
            "wasm_supported": report.get("wasm_supported", []) if report else [],
            "webgpu_supported": report.get("webgpu_supported", []) if report else [],
            "case_rows": len(observations),
            "parquet_rows": len(rows),
            "failure": failure,
        },
    )
    shutil.copyfile(BASE / "cc-by-4.0.txt", folder / "LICENSE")
    shutil.copyfile("LICENSE", folder / "NOTICE")
    (folder / "README.md").write_text(
        "---\nlicense: cc-by-4.0\nconfigs:\n- config_name: browser-operators\n  data_files:\n  - split: train\n    path: measurements.parquet\n---\n# VoxelShogi real-M browser operator measurements\n\n"
        "## Generation and provenance\n"
        f"Browser source `{SOURCE}`; original untrained seed66001 models from `{INPUT_RECEIPT['repo_id']}` at fixed revision `{INPUT_RECEIPT['hub_commit']}`. Full/Axial/Geometry/3D-CNN, WASM/WebGPU, frozen fixtures0/3,8 warmup+32 measured forward passes each. Actual observed case rows: {len(observations)}. A pre-measurement failure is one explicitly typed failure row, never eight observations. No data generation or model learning.\n\n"
        "## Usage and schema\n"
        "Read measurements.parquet (architecture,backend,status,measurement_json). The HF train split is a file-layout label for measurement records, not a position-training corpus. Decode measurement_json for per-fixture full-vector errors, legal argmax, samples_ms, actual provider/operator profile, adapter identity, session release and before/after browser RSS. Failed/running rows are not supported backends. Raw success labels require report.controller_validation and absence of manifest.failure before use as supported cases. manifest.json preserves the complete report and source/input provenance. Original model/reference bytes remain in the gated model repository.\n\n"
        "## Verification\n"
        "Successful cases require all17 original release files to be read at the fixed Hub revision and checked for bytes/SHA-256/public-manual/CommunityOFF, plus input replay checks against frozen Rust fixtures. A partial/failure release does not prove those stages completed; inspect validation.json and manifest.report/failure. Every browser read checks exact bytes/SHA-256; all1067985 Policy and1 Value outputs use policy atol/rtol1e-4 and value1e-5. Hardware WebGPU requires an actual unmixed provider profile and non-software adapter. Each case gets a fresh context/Worker; OS/driver caches are uncontrolled. Timings include readback/GPU completion. RSS observations are not peaks; tracked GPU buffers are not total device memory. Full renderer interaction, learned strength, physical mobile and60min supported-device checks are not covered. This published release is checked at its own fixed revision before host retirement.\n\n"
        "## Access and license\n"
        "CC-BY-4.0 measurement data, VoxelShogi contributors; embedded execution source is Apache-2.0 (NOTICE). Public/manual download approval, Community disabled. Retain attribution and source/input hashes when comparing results. No model weights, optimizer states, provider keys or HF credentials are included.\n"
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
    paths = {}

    def fetch_file(entry):
        if time.time() >= TRANSFER_END:
            raise InterruptedError("fixed browser all-hash boundary")
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
        paths.update(pool.map(fetch_file, plan["files"]))
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
    assert W["stage"] == "research-browser" and W["admitted"] is True
    assert len(INPUT_PLAN["files"]) == 17
    raw_api = HfApi(endpoint="https://huggingface.co", token=TOKEN)
    candidate = RecoveryApi(
        PublicationApi(raw_api, get_session(), build_hf_headers(token=TOKEN)),
        deadline=TRANSFER_END,
        transient_errors=(TimeoutError, ConnectionError, TransportError),
        wait=STOP.wait,
        stop_requested=STOP.is_set,
        observe=observe_hf,
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
    begin = stage("verify-original-17-HF-files")
    source, input_receipt = acquire_models()
    TIMINGS[CURRENT] = time.monotonic() - begin
    if stopping():
        raise InterruptedError("fixed browser preparation boundary")
    begin = stage("prepare-exact-browser-inputs")
    inputs = BASE / "browser-inputs"
    prepared = prepare_inputs(source, inputs, plan=INPUT_PLAN, receipt=input_receipt)
    atomic_json(
        BASE / "feature-preparation.json",
        {
            "models": len(prepared["models"]),
            "input_sha256": file_hash(inputs / "browser-inputs.json"),
            "scope": "Frozen numerical fixture references only; no train/val/test feature cache",
        },
    )
    TIMINGS[CURRENT] = time.monotonic() - begin
    if stopping():
        raise InterruptedError("fixed browser start boundary")
    begin = stage("actual-browser-WASM-WebGPU")
    REPORT = measure_browser(inputs)
    REPORT["controller_validation"] = review_report(REPORT)
    atomic_json(BASE / "browser-validation.json", REPORT["controller_validation"])
    TIMINGS[CURRENT] = time.monotonic() - begin
except BaseException as error:
    error_record = {
        "complete": False,
        "stage": CURRENT,
        "error_type": type(error).__name__,
        "elapsed_seconds": time.monotonic() - START,
    }
    atomic_json(BASE / "failure.json", error_record)
    target = BASE / "browser-output/result.json"
    if target.is_file() and target.stat().st_size < 4 * 1024**2:
        REPORT = json.loads(target.read_text())
finally:
    if API is not None and not stopping():
        try:
            begin = stage("shared-host-full-corpus-admission-diagnosis")
            CORPUS_RESULT = run_corpus_child()
            TIMINGS[CURRENT] = time.monotonic() - begin
        except BaseException as error:
            corpus_error = {
                "complete": False,
                "stage": CURRENT,
                "error_type": type(error).__name__,
            }
            atomic_json(BASE / "corpus-audit-failure.json", corpus_error)
            if error_record is None:
                error_record = corpus_error
    try:
        if API is not None and time.time() < TRANSFER_END:
            begin = stage("publish-browser-report-and-all-hash")
            RECEIPT = publish_browser(REPORT, error_record)
            TIMINGS[CURRENT] = time.monotonic() - begin
        if (
            error_record is None
            and REPORT is not None
            and REPORT.get("matrix_complete")
            and REPORT.get("controller_validation", {}).get("wasm_verified") == 4
            and REPORT.get("controller_exit_code") == 0
            and CORPUS_RESULT is not None
            and CORPUS_RESULT["complete"]
            and RECEIPT
            and RECEIPT["verified"]
        ):
            atomic_json(
                BASE / "complete.json",
                {
                    "complete": True,
                    "all_backends_passed": REPORT["complete"],
                    "browser_validation": REPORT["controller_validation"],
                    "corpus_audit_complete": CORPUS_RESULT,
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
                    "error_type": "BrowserOrPublicationIncomplete",
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
