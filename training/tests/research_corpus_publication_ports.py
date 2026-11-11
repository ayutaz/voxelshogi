"""Opaque fake-port publication checks; no actual corpus or Parquet generation."""

import ast
import concurrent.futures
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from training.evaluation_v2 import fingerprint
from training.feature_cache import file_hash
from training.hub_release import plan_release, publish_release, verify_release
from training.tests.test_hub_release import Hub

worker = Path("infrastructure/research/corpus_worker.py")
functions = [
    n
    for n in ast.parse(worker.read_text()).body
    if isinstance(n, ast.FunctionDef) and n.name == "publish_corpus"
]
assert len(functions) == 1


def check(*, admission_exists=True, complete=True, corrupt=False):
    with tempfile.TemporaryDirectory(prefix="corpus-publication-fake-") as td:
        base = Path(td)
        for source in ("worker.py", "inspect-corpus.py"):
            shutil.copyfile(
                worker.parent
                / {
                    "worker.py": "corpus_worker.py",
                    "inspect-corpus.py": "corpus_inspect.py",
                }[source],
                base / source,
            )
        (base / "cc-by-4.0.txt").write_text("opaque CC-BY-4.0 license fixture")
        (base / "diagnosis").mkdir()
        if admission_exists:
            (base / "diagnosis/admission.json").write_text(
                json.dumps(
                    {
                        "metadata": [
                            {
                                "id": "a:0",
                                "family": "a" * 64,
                                "input": "b" * 64,
                                "value_kind": "bootstrap-v1",
                                "ply": 0,
                            }
                        ],
                        "admission": {
                            "selected_ids": {"train": ["a:0"], "val": [], "test": []},
                            "rows_by_split": {"train": 1, "val": 0, "test": 0},
                        },
                    }
                )
            )

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

        class FakeTable:
            def __init__(self, rows, schema):
                self.rows, self.schema = rows, schema

            def equals(self, other, check_metadata):
                return (
                    check_metadata
                    and self.rows == other.rows
                    and self.schema == other.schema
                )

        def write(table, path, **kwargs):
            # Explicitly opaque fixture; real PyArrow round trip is Linux only.
            path.write_bytes(json.dumps(table.rows).encode())
            tables[str(path)] = table

        tables = {}
        pq = SimpleNamespace(write_table=write, read_table=lambda p: tables[str(p)])
        pa = SimpleNamespace(
            schema=lambda fields, metadata: (fields, metadata),
            string=lambda: "string",
            int64=lambda: "int64",
            bool_=lambda: "bool",
            Table=SimpleNamespace(
                from_pylist=lambda rows, schema: FakeTable(rows, schema)
            ),
        )

        def fetch(**kwargs):
            assert (
                kwargs["repo_id"] == "voxelshogi/voxelshogi-research-pilot-admission-v1"
            )
            assert kwargs["repo_type"] == "dataset" and kwargs["revision"] == "c" * 40
            path = base / "publication" / kwargs["filename"]
            if corrupt and path.name == "admission.parquet":
                path = base / "corrupt.fake"
                path.write_bytes(b"changed output fixture")
            return path

        pa.parquet = pq
        scope = {
            "BASE": base,
            "TRANSFER_END": time.time() + 1000,
            "INPUTS": {n: {} for n in ("selfplay", "protection", "screen")},
            "W": {"frozen_source": "a" * 40},
            "SOURCE": "a" * 40,
            "TIMINGS": {},
            "RESOURCE_ROWS": [],
            "TOKEN": "opaque-test-token-no-credential",
            "API": api,
            "REPO": "voxelshogi/voxelshogi-research-pilot-admission-v1",
            "time": time,
            "json": json,
            "Path": Path,
            "shutil": shutil,
            "concurrent": concurrent,
            "fingerprint": fingerprint,
            "file_hash": file_hash,
            "atomic_json": lambda p, v: p.write_text(json.dumps(v)),
            "plan_release": plan_release,
            "publish_release": lambda *a, **kw: publish_release(
                *a, system="linux", **kw
            ),
            "verify_release": lambda *a, **kw: verify_release(*a, system="linux", **kw),
            "hf_hub_download": fetch,
        }
        exec(
            compile(ast.Module(body=functions, type_ignores=[]), str(worker), "exec"),
            scope,
        )
        report = (
            {
                "usable_counts": False,
                "teacher_quality_accepted": False,
                "training_executed": False,
            }
            if complete
            else None
        )
        failure = None if complete else {"error_type": "InterruptedError"}
        with patch.dict(sys.modules, {"pyarrow": pa, "pyarrow.parquet": pq}):
            if corrupt:
                try:
                    scope["publish_corpus"](report, failure)
                except ValueError, AssertionError:
                    return
                raise AssertionError("corrupt fixed-HF output accepted")
            receipt = scope["publish_corpus"](report, failure)
            assert receipt["verified"] and receipt["community_disabled"]
            manifest = json.loads((base / "publication/manifest.json").read_text())
            assert manifest["raw_rows"] == int(admission_exists)
            assert manifest["failure"] == failure
            validation = json.loads((base / "publication/validation.json").read_text())
            assert validation["diagnosis_complete"] is complete
            assert (
                validation["teacher_quality_accepted"] is False
                and validation["training_executed"] is False
            )
            try:
                scope["publish_corpus"](report, failure)
            except AssertionError:
                pass
            else:
                raise AssertionError("publication request was resent")


check()
check(complete=False)
check(admission_exists=False, complete=False)
check(corrupt=True)
print(
    "Fake complete/partial/empty audit publication, Card/hash checks and duplicate-send rejection passed; actual corpora0"
)
