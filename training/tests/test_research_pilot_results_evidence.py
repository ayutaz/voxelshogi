"""Hand-built complete metadata cohorts; no engines, tensors or remote work."""

import pytest

from infrastructure.research.pilot.validation import development_protocol
from training.checkpoint import atomic_json
from training.evaluation_v2 import fingerprint
from training.feature_cache import file_hash
from training.tests.test_research_pilot_results import fixture


def complete_fixture(tmp_path, monkeypatch):
    value, base = fixture(tmp_path, monkeypatch)
    source = value["job"]["source_commit"]
    cycles, diagnostics, cohort_results, audited = [], {}, {}, {}
    for inputs in value["job"]["inputs"]:
        name = inputs["config"]["architecture"]["architecture"]
        folder = base / name
        folder.mkdir(exist_ok=True)
        proof = {
            "schema": "voxelshogi-research-pilot-cuda-resume-proof-v1",
            "verified": True,
            "source_commit": source,
            "total_updates": inputs["config"]["total_updates"],
        }
        atomic_json(folder / "resume-proof.json", proof)
        transfers = {}
        for stage, step in (
            ("intermediate", value["job"]["split_step"]),
            ("final", inputs["config"]["total_updates"]),
        ):
            target = folder / (stage + "-transfer")
            target.mkdir()
            plan = {
                "schema": 1,
                "repo_id": "voxelshogi/voxelshogi-research-training-state-v1",
                "repo_type": "model",
                "private": False,
                "gated": "manual",
                "license": "apache-2.0",
                "license_approved": True,
                "source_commit": source,
                "artifact_role": "research-training-state",
                "state_publication_approved": True,
                "expected_binding": {
                    "source_commit": source,
                    "config": inputs["config"],
                },
                "files": [
                    {"path": "latest/state.safetensors", "bytes": 1, "sha256": "e" * 64}
                ],
            }
            receipt = {
                "repo_id": plan["repo_id"],
                "repo_type": "model",
                "hub_commit": "c" * 40,
                "verified": True,
                "community_disabled": True,
                "dry_run": False,
                "release_sha256": fingerprint(plan),
            }
            transfer = {
                "receipt": receipt,
                "restored": True,
                "progress": {"step": step},
            }
            for filename, data in (
                ("publication-plan.json", plan),
                ("publication-receipt.json", receipt),
                ("complete.json", transfer),
            ):
                atomic_json(target / filename, data)
            transfers[stage] = transfer
        cycle = {
            "source_commit": source,
            "architecture": name,
            "inputs_sha256": fingerprint(inputs),
            "scientific_pilots": 1,
            "additional_independent_seeds": 0,
            "resume_proof": proof,
            "intermediate_transfer": transfers["intermediate"],
            "final_transfer": transfers["final"],
        }
        atomic_json(folder / "complete.json", cycle)
        cycles.append(cycle)
        selected = folder / "diagnostics/selected"
        selected.mkdir(parents=True)
        (selected / "model.safetensors").write_bytes(
            b"opaque unexecuted weights fixture"
        )
        weights_sha = file_hash(selected / "model.safetensors")
        selection = {"weights": {"sha256": weights_sha}}
        atomic_json(selected / "selection.json", selection)
        diagnostic = {
            "source_commit": source,
            "architecture": name,
            "weights_sha256": weights_sha,
            "selection": {
                "folder": str(selected),
                "selection_sha256": file_hash(selected / "selection.json"),
            },
        }
        atomic_json(folder / "diagnostics/complete.json", diagnostic)
        diagnostics[name] = diagnostic
        cohort = base / "development" / name
        cohort.mkdir(parents=True)
        p = development_protocol(
            value["development"],
            expected_sha256=value["development_sha256"],
            source_commit=source,
            weights_sha256=weights_sha,
        )
        atomic_json(cohort / "protocol.json", p)
        rows = []
        for case in p["cases"]:
            for side in ("b", "w"):
                path = cohort / f"{case['id']}-{side}.json"
                atomic_json(path, {"case_id": case["id"], "model_side": side})
                rows.append(
                    {
                        "path": path.name,
                        "bytes": path.stat().st_size,
                        "sha256": file_hash(path),
                    }
                )
        summary = {
            "overall": {"games": 24},
            "opaque": "already replay-verified before export",
        }
        atomic_json(cohort / "summary.json", summary)
        run = {
            "complete": True,
            "protocol_sha256": fingerprint(p),
            "games": 24,
            "summary_sha256": file_hash(cohort / "summary.json"),
            "files": rows,
        }
        atomic_json(cohort / "run.json", run)
        audited[name] = {
            "protocol_sha256": fingerprint(p),
            "run_sha256": file_hash(cohort / "run.json"),
        }
        cohort_results[name] = {"summary": summary}
    learning = {"learning_complete": True, "scientific_pilots": 2, "cycles": cycles}
    atomic_json(base / "training-complete.json", learning)
    trace = base / "development/queries.jsonl"
    trace.write_text('{"architecture":"full"}\n{"architecture":"geometry"}\n')
    audit = {
        "schema": "voxelshogi-generation-input-audit-v1",
        "passed": True,
        "runs": audited,
    }
    atomic_json(base / "development/input-audit.json", audit)
    development = {
        "games": 48,
        "source_commit": source,
        "queries": 2,
        "query_trace_sha256": file_hash(trace),
        "input_audit_sha256": file_hash(base / "development/input-audit.json"),
        "by_architecture": cohort_results,
        "leakage_free": True,
        "final_holdout_evaluated": False,
    }
    atomic_json(base / "development/complete.json", development)
    compute = {
        "pipeline_complete": True,
        "source_commit": source,
        "learning": learning,
        "diagnostics": diagnostics,
        "development": development,
    }
    atomic_json(base / "workflow-compute.json", compute)
    return value, base, compute


@pytest.mark.parametrize(
    "mode",
    [
        "complete",
        "trace",
        "match",
        "receipt",
        "resume",
        "selected",
        "diagnostic",
        "summary",
        "protocol",
        "audit",
        "cycle",
    ],
)
def test_complete_result_publication_is_tied_to_actual_verified_files(
    tmp_path, monkeypatch, mode
):
    from infrastructure.research.pilot.results_evidence import verify_complete_evidence

    value, base, compute = complete_fixture(tmp_path, monkeypatch)
    target = {
        "trace": "development/queries.jsonl",
        "match": f"development/full/{value['development']['protocol']['cases'][0]['id']}-b.json",
        "receipt": "full/final-transfer/publication-receipt.json",
        "resume": "full/resume-proof.json",
        "selected": "full/diagnostics/selected/model.safetensors",
        "diagnostic": "geometry/diagnostics/complete.json",
        "summary": "development/full/summary.json",
        "protocol": "development/full/protocol.json",
        "audit": "development/input-audit.json",
        "cycle": "full/complete.json",
    }
    if mode != "complete":
        (base / target[mode]).write_text('{"changed":true}\n')
        with pytest.raises((ValueError, KeyError)):
            verify_complete_evidence(value, base, compute)
    else:
        verify_complete_evidence(value, base, compute)


def test_complete_dataset_requires_all_cohorts_and_packs_metadata_without_weights(
    tmp_path, monkeypatch
):
    from unittest.mock import patch

    from infrastructure.research.pilot.results import build_results
    from training.tests.test_research_pilot_results import opaque_writer

    value, base, _ = complete_fixture(tmp_path, monkeypatch)
    for name in ("full", "geometry"):
        for run in ("continuous", "interrupted", "restored"):
            folder = base / name / run
            folder.mkdir(exist_ok=True)
            atomic_json(folder / "run.json", {"opaque": "verified binding fixture"})
            (folder / "events.jsonl").write_text('{"step":1}\n')
    with patch("sys.platform", "linux"):
        result = build_results(
            value,
            base,
            base / "publication",
            pipeline_complete=True,
            writer=opaque_writer,
        )
    assert (
        result["pipeline_complete"] is True
        and result["scientific_pilots_completed"] == 2
    )
    assert (
        len(
            [
                f
                for f in result["files"]
                if f["path"].startswith("development/full/dev-")
            ]
        )
        == 24
    )
    assert (
        len(
            [
                f
                for f in result["files"]
                if f["path"].startswith("development/geometry/dev-")
            ]
        )
        == 24
    )
    assert not any(f["path"].endswith("safetensors") for f in result["files"])


def test_complete_publication_keeps_resume_history_even_when_proof_metadata_exists(
    tmp_path, monkeypatch
):
    from unittest.mock import patch

    from infrastructure.research.pilot.results import build_results
    from training.tests.test_research_pilot_results import opaque_writer

    value, base, _ = complete_fixture(tmp_path, monkeypatch)
    for name in ("full", "geometry"):
        for run in ("continuous", "interrupted", "restored"):
            folder = base / name / run
            folder.mkdir(exist_ok=True)
            atomic_json(folder / "run.json", {"opaque": "verified binding fixture"})
            if (name, run) != ("geometry", "restored"):
                (folder / "events.jsonl").write_text('{"step":1}\n')
    with (
        patch("sys.platform", "linux"),
        pytest.raises(ValueError, match="missing mandatory"),
    ):
        build_results(
            value,
            base,
            base / "publication",
            pipeline_complete=True,
            writer=opaque_writer,
        )
