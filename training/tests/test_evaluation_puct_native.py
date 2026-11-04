"""Real Rust replay and CPU Torch/PUCT boundary; external Linux/CI only."""

import json
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="external Linux only")


def weighted_mate(tmp_path, monkeypatch):
    import torch
    from safetensors.torch import save_file
    from voxelshogi import Game

    import export.model
    from training.feature_cache import file_hash
    from training.tests.test_evaluation_v2_native import native_protocol
    from training.tests.test_students import model

    spec = native_protocol()
    spec["cases"] = spec["cases"][:1]
    game = Game.from_record(spec["cases"][0]["opening"])
    # This checkmating move comes from the hand-authored fixture, not from PUCT.
    action = next(a for a, move in game.legal_actions().items() if move == "232222")
    network = model()
    with torch.no_grad():
        network.logits.fill_(-20)
        network.logits[0, action] = 20
    path = tmp_path / "model.safetensors"
    save_file(network.state_dict(), path)
    spec["participants"]["model"] = {
        "artifact_sha256": file_hash(path),
        "policy": "puct32-v1",
        "backend": "torch-cpu",
    }
    monkeypatch.setattr(export.model, "make_model", lambda seed: model())
    return spec, {"model": path}


def test_real_puct_weight_loading_mate_color_swap_and_replay(tmp_path, monkeypatch):
    from training.evaluation_v2_runner import run_protocol, verify_run

    spec, artifacts = weighted_mate(tmp_path, monkeypatch)
    folder = tmp_path / "sequential"
    observed = []
    summary = run_protocol(
        spec,
        artifacts,
        folder,
        observe_input=lambda role, game: observed.append((role, game.record())),
    )
    assert [
        summary["overall"][k] for k in ("games", "wins", "losses", "draws", "cutoffs")
    ] == [2, 1, 1, 0, 0]
    assert verify_run(folder) == summary
    black = json.loads((folder / "hand-mate-b.json").read_text())
    assert black["record"]["moves"][-1] == "232222"
    assert black["record"]["result"] == {
        "Win": {"winner": "Black", "reason": "Checkmate"}
    }
    receipt = json.loads((folder / "run.json").read_text())
    assert receipt["runtime"]["torch"] and receipt["games"] == 2
    assert observed == [("model", spec["cases"][0]["opening"])]
    from copy import deepcopy

    argmax = deepcopy(spec)
    argmax["participants"]["model"]["policy"] = "legal-argmax-v1"
    observed.clear()
    control = run_protocol(
        argmax,
        artifacts,
        tmp_path / "argmax",
        observe_input=lambda role, game: observed.append((role, game.record())),
    )
    assert [
        control["overall"][k] for k in ("games", "wins", "losses", "draws", "cutoffs")
    ] == [2, 1, 1, 0, 0]
    assert observed == [("model", spec["cases"][0]["opening"])]


def test_real_puct_assigned_case_resume_preserves_committed_color_bytes(
    tmp_path, monkeypatch
):
    from training.evaluation_jobs import aggregate_case_jobs, run_case_assignment
    from training.evaluation_v2_runner import verify_run
    from training.feature_cache import file_hash

    spec, artifacts = weighted_mate(tmp_path, monkeypatch)
    folder = tmp_path / "assigned"
    first = folder / "hand-mate-b.json"
    with pytest.raises(InterruptedError):
        run_case_assignment(
            spec, artifacts, folder, case_id="hand-mate", stop_requested=first.exists
        )
    original = file_hash(first)
    receipt = run_case_assignment(
        spec, artifacts, folder, case_id="hand-mate", resume=True
    )
    assert (
        receipt["complete"] and receipt["games"] == 2 and file_hash(first) == original
    )
    combined = tmp_path / "cohort"
    result = aggregate_case_jobs(spec, {"hand-mate": folder}, combined)
    assert verify_run(combined) == result
    assert result["overall"]["wins"] == result["overall"]["losses"] == 1
    assert file_hash(combined / "hand-mate-b.json") == original
