"""Fake port publication checks only; no browser, model, dataset or provider run."""

import ast
import concurrent.futures
import json
import shutil
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from training.evaluation_v2 import fingerprint
from training.feature_cache import file_hash
from training.hub_release import plan_release, publish_release, verify_release
from training.tests.test_hub_release import Hub

worker = Path("infrastructure/research/browser_worker.py")
functions = [
    n
    for n in ast.parse(worker.read_text()).body
    if isinstance(n, ast.FunctionDef) and n.name == "publish_browser"
]
assert len(functions) == 1


def check(report, failure=None, *, corrupt=False):
    with tempfile.TemporaryDirectory(prefix="browser-publication-fake-") as tmp:
        base = Path(tmp)
        shutil.copyfile(worker, base / "worker.py")
        (base / "host-admission.json").write_text("{}")
        (base / "input-verification.json").write_text("{}")
        (base / "cc-by-4.0.txt").write_text("CC-BY-4.0 opaque unit fixture")
        observed = []

        class FakeHub(Hub):
            uploaded = False

            def repo_info(self, **kwargs):
                return SimpleNamespace(
                    private=False,
                    gated="manual",
                    sha=("c" if self.uploaded else "b") * 40,
                )

            def upload_folder(self, **kwargs):
                self.uploaded = True
                return super().upload_folder(**kwargs)

        api = FakeHub()

        def write_rows(path, rows):
            # Opaque scalar test fixture, deliberately not a real Parquet writer.
            observed.extend(rows)
            path.write_bytes(json.dumps(rows).encode())

        def fetch(**kwargs):
            assert kwargs["repo_id"] == "voxelshogi/voxelshogi-research-browser-v1"
            assert kwargs["repo_type"] == "dataset" and kwargs["revision"] == "c" * 40
            target = base / "publication" / kwargs["filename"]
            if corrupt and target.name == "measurements.parquet":
                target.write_bytes(b"corrupt")
            return target

        scope = {
            "Path": Path,
            "json": json,
            "time": time,
            "shutil": shutil,
            "concurrent": concurrent,
            "BASE": base,
            "TRANSFER_END": time.time() + 60,
            "INPUT_PLAN": {"files": []},
            "INPUT_RECEIPT": {
                "repo_id": "voxelshogi/voxelshogi-research-operator-probe-v1",
                "hub_commit": "d" * 40,
            },
            "W": {"stage": "fake-port-only"},
            "SOURCE": "a" * 40,
            "TOKEN": "fake-unit-not-a-credential",
            "REPO": "voxelshogi/voxelshogi-research-browser-v1",
            "TIMINGS": {},
            "RESOURCE_ROWS": [],
            "API": api,
            "fingerprint": fingerprint,
            "file_hash": file_hash,
            "write_measurement_rows": write_rows,
            "atomic_json": lambda p, v: Path(p).write_text(json.dumps(v)),
            "plan_release": plan_release,
            "publish_release": lambda *a, **kw: publish_release(
                *a, **kw, system="linux"
            ),
            "verify_release": lambda *a, **kw: verify_release(*a, **kw, system="linux"),
            "hf_hub_download": fetch,
        }
        exec(
            compile(ast.Module(body=functions, type_ignores=[]), str(worker), "exec"),
            scope,
        )
        if corrupt:
            try:
                scope["publish_browser"](report, failure)
            except AssertionError:
                pass
            else:
                raise AssertionError("corrupt fixed-revision bytes were accepted")
        else:
            receipt = scope["publish_browser"](report, failure)
            assert receipt["verified"] and receipt["community_disabled"]
            assert receipt["hub_commit"] == "c" * 40
            saved = json.loads((base / "publication/manifest.json").read_text())
            assert (
                saved["case_rows"] == len(report.get("rows", []))
                if report
                else saved["case_rows"] == 0
            )
            assert saved["parquet_rows"] == max(
                1, len(report.get("rows", [])) if report else 0
            )
            assert observed and observed[0]["status"] == (
                report["rows"][0]["status"]
                if report and report.get("rows")
                else "worker-failed"
            )
            try:
                scope["publish_browser"](report, failure)
            except AssertionError:
                pass
            else:
                raise AssertionError("duplicate publication attempt was resent")


complete = {
    "matrix_complete": True,
    "complete": True,
    "wasm_supported": ["full", "axial", "geometry", "cnn"],
    "webgpu_supported": ["full", "axial", "geometry", "cnn"],
    "rows": [
        {"name": n, "backend": b, "status": "success"}
        for n in ("full", "axial", "geometry", "cnn")
        for b in ("wasm", "webgpu")
    ],
}
check(complete)
partial = {
    **complete,
    "complete": False,
    "rows": [
        {"name": "full", "backend": "wasm", "status": "success"},
        {
            "name": "full",
            "backend": "webgpu",
            "status": "failed",
            "error_message": "unsupported operator",
        },
    ],
}
check(partial)
check(None, {"error_type": "FakeBeforeMeasurement"})
check(complete, corrupt=True)
print(
    "Fake complete/partial/pre-measurement failure, fixed hash corruption and duplicate-send checks passed"
)
