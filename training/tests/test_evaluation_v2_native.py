"""Linux-only integration: real Rust moves, replay, and complete v2 receipts."""

import json
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from training.tests.test_evaluation_v2 import protocol

ROOT = Path(__file__).resolve().parents[2]


def native_protocol():
    from training.evaluation_v2_runner import rust_policy_identity

    fixtures = json.loads((ROOT / "export/fixtures/positions.json").read_text())
    spec = protocol()
    spec["source_commit"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    spec["search_limits"] = {"max_depth": 1, "max_nodes": 1000, "table_capacity": 16}
    spec["cases"] = [
        {
            "id": "hand-mate",
            "stratum": "tactical",
            "seed": 7,
            "max_additional_plies": 1,
            "opening": deepcopy(fixtures[2]["record"]),
        },
        {
            "id": "hand-material",
            "stratum": "endgame",
            "seed": 8,
            "max_additional_plies": 2,
            "opening": deepcopy(fixtures[3]["record"]),
        },
    ]
    participant = {
        "policy": "alphabeta-v1",
        "backend": "rust",
        "artifact_sha256": rust_policy_identity(
            "alphabeta-v1", spec["source_commit"], spec["search_limits"]
        ),
    }
    spec["participants"] = {"model": dict(participant), "opponent": dict(participant)}
    return spec


def test_real_mate_on_final_ply_cutoffs_replay_and_exact_cohort_receipts(tmp_path):
    from training.evaluation_v2_runner import run_protocol, verify_record, verify_run
    from training.feature_cache import file_hash

    spec = native_protocol()
    folder = tmp_path / "first"
    summary = run_protocol(spec, {}, folder)
    assert summary["overall"]["games"] == 4
    assert [
        summary["overall"][key] for key in ("wins", "losses", "draws", "cutoffs")
    ] == [1, 1, 0, 2]
    assert summary["by_stratum"]["tactical"]["termination_rate"] == 1.0
    assert summary["by_stratum"]["endgame"]["termination_rate"] == 0.0
    receipt = json.loads((folder / "run.json").read_text())
    assert receipt["complete"] and receipt["games"] == 4
    assert receipt["summary_sha256"] == file_hash(folder / "summary.json")
    assert len(receipt["files"]) == 4
    assert receipt["runtime"]["source_commit"] == spec["source_commit"]
    assert verify_run(folder) == summary
    second = tmp_path / "second"
    run_protocol(spec, {}, second)
    for case in spec["cases"]:
        for side in ("b", "w"):
            name = f"{case['id']}-{side}.json"
            row = json.loads((folder / name).read_text())
            assert row["record"] == json.loads((second / name).read_text())["record"]
            verify_record(row, case)
            altered = deepcopy(row)
            altered["record"]["moves"][0] = "999999"
            with pytest.raises(ValueError):
                verify_record(altered, case)
    with pytest.raises(FileExistsError):
        run_protocol(spec, {}, folder)


def test_stop_retains_incomplete_receipt_and_never_publishes_summary(tmp_path):
    from training.evaluation_v2_runner import run_protocol

    folder = tmp_path / "stopped"
    with pytest.raises(InterruptedError):
        run_protocol(native_protocol(), {}, folder, stop_requested=lambda: True)
    assert json.loads((folder / "run.json").read_text())["complete"] is False
    assert not (folder / "summary.json").exists()
    assert not (folder / "hand-mate-b.json").exists()


def test_changed_source_or_native_policy_identity_is_rejected(tmp_path):
    from training.evaluation_v2_runner import run_protocol

    spec = native_protocol()
    spec["source_commit"] = "0" * 40
    with pytest.raises(ValueError, match="clean source"):
        run_protocol(spec, {}, tmp_path / "wrong-source")
    spec = native_protocol()
    spec["participants"]["model"]["artifact_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="policy identity"):
        run_protocol(spec, {}, tmp_path / "wrong-policy")


def test_saved_run_detects_tampered_result_file_before_replay(tmp_path):
    from training.evaluation_v2_runner import run_protocol, verify_run

    folder = tmp_path / "tamper"
    run_protocol(native_protocol(), {}, folder)
    path = folder / "hand-mate-b.json"
    row = json.loads(path.read_text())
    row["outcome"] = "loss"
    path.write_text(json.dumps(row))
    with pytest.raises(ValueError, match="hash"):
        verify_run(folder)
