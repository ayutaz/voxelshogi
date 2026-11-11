"""Frozen-input, child, state and cycle contracts on fake metadata/ports only."""

import copy
import json
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


@pytest.mark.parametrize(
    "port", ["attempt", "resume-proof", "child", "state-transfer", "cycle"]
)
def test_pilot_execution_ports_without_actual_datasets_models_or_api_calls(port):
    # Boundary assertions must also run on Linux CI. Each test deliberately
    # enters Linux only around fake ports, then verifies the Mac boundary.
    with patch("sys.platform", "darwin"):
        runpy.run_path(str(Path(__file__).parent / "pilot_ports" / f"check-{port}.py"))


@pytest.mark.parametrize(
    "change",
    [
        None,
        "latest-weight",
        "best-optimizer",
        "cuda-rng",
        "partial",
        "history",
        "binding",
    ],
)
def test_resume_proof_reads_all_roles_and_full_schedule_with_fake_checkpoint_port(
    tmp_path, monkeypatch, change
):
    from infrastructure.research.pilot.resume_proof import verify_runs
    from training.evaluation_v2 import fingerprint
    from training.research_visit_fit import VisitRunConfig

    with patch("sys.platform", "darwin"):
        Tensor = runpy.run_path(
            str(Path(__file__).parent / "pilot_ports/check-resume-proof.py")
        )["Tensor"]
    config = VisitRunConfig(total_updates=7, validate_every=3, batch_size=2)
    binding = {
        "source_commit": "a" * 40,
        "cache_sha256": "b" * 64,
        "config": config.value(),
        "contract": {
            "schema": "voxelshogi-research-visit-training-v1",
            "admission_sha256": "c" * 64,
        },
        "environment": {"device": "cuda"},
    }
    events = []
    for step in range(1, 8):
        events.append({"event": "train", "step": step, "ids": ["train:0"], "loss": 1.0})
        if step in (3, 6, 7):
            events.append(
                {
                    "event": "val",
                    "step": step,
                    "policy_ce": 0.7,
                    "value_mse": 0.04,
                    "loss": 0.74,
                    "examples": 1,
                    "value_origins": {"bootstrap-v1": 1},
                }
            )
    folders = [tmp_path / "continuous", tmp_path / "restored"]
    for folder in folders:
        folder.mkdir()
        (folder / "run.json").write_text(json.dumps({"binding": binding}))
        (folder / "events.jsonl").write_text(
            "".join(json.dumps(e) + "\n" for e in events)
        )
    if change == "history":
        (folders[1] / "events.jsonl").write_text(json.dumps(events[0]) + "\n")
    if change == "binding":
        changed = copy.deepcopy(binding)
        changed["config"]["seed"] += 1
        (folders[1] / "run.json").write_text(json.dumps({"binding": changed}))
    reads = []

    def payload(folder, which):
        state = {
            "model": {"weight": Tensor([1, 2])},
            "optimizer": {"moment": Tensor([3, 4])},
            "rng": {"cuda": [Tensor([5, 6])]},
            "progress": {"step": 7 if which == "latest" else 6},
            "binding": binding,
        }
        if change == "partial" and which == "latest":
            state["progress"]["step"] = 6
        if folder == folders[1]:
            if change == "latest-weight" and which == "latest":
                state["model"]["weight"] = Tensor([2, 1])
            if change == "best-optimizer" and which == "best":
                state["optimizer"]["moment"] = Tensor([4, 3])
            if change == "cuda-rng":
                state["rng"]["cuda"] = []
        return state

    def receipt(path, *, binding, which):
        folder = path.parent
        reads.append((folder.name, which))
        return path / which, {
            "progress": payload(folder, which)["progress"],
            "sha256": ("d" if folder == folders[0] else "e") * 64,
        }

    def load(path, **kwargs):
        assert kwargs == {"map_location": "cpu", "weights_only": True}
        return payload(path.parent.parent, path.name)

    monkeypatch.setattr("training.checkpoint.checkpoint_receipt", receipt)
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(Tensor=Tensor, load=load))
    with patch("sys.platform", "linux"):
        if change is None:
            proof = verify_runs(*folders, total_updates=7)
            assert proof["verified"] and proof["binding_sha256"] == fingerprint(binding)
            assert reads == [
                ("continuous", "latest"),
                ("restored", "latest"),
                ("continuous", "best"),
                ("restored", "best"),
            ]
            assert proof["history_events"] == 10
            assert all(
                p["exact_equal"] and p["compared"]["tensors"] == 3
                for p in proof["checkpoints"].values()
            )
        else:
            with pytest.raises(ValueError):
                verify_runs(*folders, total_updates=7)
