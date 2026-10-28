"""Actual native/Parquet production paths run on Linux CI, not on Mac."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from training.tests.test_data import config, files


def test_parallel_generation_and_cross_worker_resume_are_byte_identical(tmp_path):
    from training.data import generate_dataset, validate_dataset

    c = replace(config(), games=6, search_opening_plies=1)
    sequential, parallel = tmp_path / "sequential", tmp_path / "parallel"
    generate_dataset(sequential, c, workers=1)
    generate_dataset(parallel, c, workers=2, max_games=3)
    generate_dataset(parallel, c, workers=4)
    assert files(sequential) == files(parallel)
    report = validate_dataset(parallel)
    assert report["games"] == 6 and report["rows"] == 18
    # Independent king-move enumeration and SHA-256 residues from the contract.
    for index, first in [(2, "999898"), (5, "999889")]:
        rows = pq.read_table(parallel / f"game-{index:06d}.parquet").to_pylist()
        assert rows[0]["played_move"] == first
        assert rows[0]["teacher_valid"]
    with pytest.raises(ValueError):
        generate_dataset(tmp_path / "invalid", c, workers=0)


def test_production_cli_uses_supervisor_and_verifies_every_file():
    if sys.platform != "linux":
        pytest.skip("native production integration is reserved for Linux CI")
    root = Path(__file__).resolve().parents[2]
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    directory = root / "runs/m4"
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="production-ci-", dir=directory
    ) as temporary:
        work = Path(temporary)
        job = {
            "schema": 1,
            "purpose": "ci-smoke",
            "provider": "ci",
            "approved": False,
            "approved_seconds": 30,
            "hourly_usd": 1,
            "max_cost_usd": 2,
            "workers": 2,
            "minimum_eligible_rows": 1,
            "gpu_model": "rtx5090",
            "config": replace(
                config(), engine_commit=commit, search_opening_plies=1
            ).value(),
        }
        request = work / "request.json"
        request.write_text(json.dumps(job))
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "training.production",
                str(request),
                str(work / "output"),
            ],
            cwd=root,
            env={**os.environ, "GITHUB_ACTIONS": "true"},
            check=False,
            capture_output=True,
            text=True,
            timeout=45,
        )
        assert process.returncode == 0, (
            process.stdout,
            process.stderr,
            (work / "output/worker.log").read_text(),
        )
        report = json.loads((work / "output/report.json").read_text())
        assert report["complete"] and report["regenerated_bytes_match"]
        assert report["validation"]["rows"] == 9
        assert report["validation"]["eligible_teachers"] > 0
        assert report["supervisor"]["reason"] == "completed"
        assert report["context"]["measurement_kind"] == "ci-correctness-only"


def test_seeded_opening_is_rechecked_even_after_attacker_rehashes_parquet(tmp_path):
    from training.data import generate_dataset, validate_dataset

    c = replace(config(), search_opening_plies=1)
    generate_dataset(tmp_path, c)
    path = tmp_path / "game-000002.parquet"
    table = pq.read_table(path)
    rows = table.to_pylist()
    rows[0]["played_move"] = "999889"  # Legal, but seed17/g000002 requires 999898.
    pq.write_table(pa.Table.from_pylist(rows, schema=table.schema), path)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    manifest["shards"][2]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="seeded move"):
        validate_dataset(tmp_path)


def test_worker_does_not_report_small_dataset_as_production_completion(tmp_path):
    from training.production import _worker

    job = {
        "config": replace(config(), search_opening_plies=1).value(),
        "workers": 1,
        "minimum_eligible_rows": 100000,
    }
    with pytest.raises(ValueError, match="eligible row target"):
        _worker(tmp_path, job)
    report = json.loads((tmp_path / "worker-result.json").read_text())
    assert report["complete"] is False and report["validation"]["rows"] == 9
    assert not (tmp_path / "second").exists()
