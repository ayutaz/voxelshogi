"""Metadata contracts only: no model, Parquet body or game execution on Mac."""

from copy import deepcopy

import pytest

from training.tests.test_selfplay_generations import protocol


def manifest():
    from training.research_data import fingerprint

    p = protocol()
    record = {
        "generation": 0,
        "parent_model_sha256": "a" * 64,
        "model_sha256": "c" * 64,
        "file": "generation-000/model.safetensors",
        "input_sha256": "4" * 64,
        "replay_sha256": "5" * 64,
        "encoded_samples": 16,
        "training_progress": {
            "epoch": 1,
            "next_batch": 0,
            "step": 4,
            "examples": 16,
            "best_val_loss": None,
        },
        "sample_audit": {
            "buffer_sha256": "5" * 64,
            "protected_sha256": "6" * 64,
            "excluded_protected": 0,
            "repeated_train_inputs": 0,
            "duplicate_policy": "retain within-train occurrences; exclude protected inputs",
        },
    }
    entries = [{"slot": i, "model_sha256": "a" * 64} for i in range(16)]
    return {
        "schema": "voxelshogi-selfplay-dataset-v1",
        "run": {
            "schema": "voxelshogi-selfplay-generations-v1",
            "protocol": p,
            "run_id": fingerprint(p),
            "generations": [record],
            "publications": [],
            "complete": False,
        },
        "replay": {
            "schema": "voxelshogi-replay-buffer-v1",
            "binding": {
                "source_commit": "1" * 40,
                "run_id": fingerprint(p),
                "capacity": 32,
            },
            "entries": entries,
        },
        "file": {
            "path": "episodes.parquet",
            "bytes": 10,
            "sha256": "d" * 64,
            "rows": 16,
        },
    }


def test_committed_boundary_requires_full_replay_and_fixed_protocol_lineage():
    from training.selfplay_dataset import validate_manifest

    m = manifest()
    validate_manifest(m, expected_protocol=protocol())
    mutations = [
        lambda x: x["run"].update(run_id="e" * 64),
        lambda x: x["run"].update(complete=True),
        lambda x: x["run"].update(generations=[]),
        lambda x: x["run"]["protocol"].update(source_commit="2" * 40),
        lambda x: x["run"]["protocol"]["actor"].update(seed=123),
        lambda x: x["run"]["generations"][0].update(parent_model_sha256="e" * 64),
        lambda x: x["run"]["generations"][0].update(file="../model.safetensors"),
        lambda x: x["run"]["generations"][0].update(model_sha256="short"),
        lambda x: x["replay"]["entries"].pop(),
        lambda x: x["replay"]["entries"].append({"slot": 16, "model_sha256": "a" * 64}),
        lambda x: x["replay"]["entries"][0].update(model_sha256="f" * 64),
        lambda x: x["replay"]["entries"][0].update(slot=1),
        lambda x: x["replay"]["binding"].update(capacity=64),
        lambda x: x["file"].update(path="../episodes.parquet"),
        lambda x: x["file"].update(bytes=0),
        lambda x: x["file"].update(rows=17),
        lambda x: x["run"]["generations"][0].update(
            unreviewed_log="not a release artifact"
        ),
        lambda x: x["run"]["generations"][0]["sample_audit"].update(
            raw_log="not a release artifact"
        ),
        lambda x: x["run"]["generations"][0]["training_progress"].update(epoch=0),
    ]
    for change in mutations:
        bad = deepcopy(m)
        change(bad)
        with pytest.raises(ValueError):
            validate_manifest(bad, expected_protocol=protocol())


def test_dataset_transfer_and_restore_refuse_mac_before_reading_files(
    monkeypatch, tmp_path
):
    from training import selfplay_dataset as dataset

    monkeypatch.setattr(dataset.sys, "platform", "darwin")
    for call in [
        lambda: dataset.pack_dataset(
            tmp_path / "absent", tmp_path / "out", expected_protocol={}
        ),
        lambda: dataset.restore_dataset(
            tmp_path / "absent", tmp_path / "out", expected_protocol={}, models={}
        ),
    ]:
        with pytest.raises(ValueError, match="Linux"):
            call()
    assert not (tmp_path / "out").exists()


def test_card_records_real_counts_and_separates_bootstrap_from_outcomes():
    from training.selfplay_dataset import dataset_card

    text = dataset_card(
        manifest(), {"episodes": 16, "samples": 72, "natural": 3, "cutoff": 13}
    )
    assert "license: cc-by-4.0" in text
    assert "16 episodes; 72 samples; 3 natural; 13 cutoff" in text
    assert "1 committed generations" in text and "3 planned" in text
    assert "bootstrap" in text and "not natural draws" in text
    assert "1" * 40 in text and "a" * 64 in text
    for heading in [
        "Generation and provenance",
        "Usage and schema",
        "Verification",
        "Access and license",
    ]:
        assert "## " + heading in text
