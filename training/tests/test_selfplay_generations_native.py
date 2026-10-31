"""Real S model, Rust, soft-target learning and generation-boundary restoration."""

import json
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="external Linux only")


def test_real_s_multi_generation_loop_and_copied_run_resume_match(
    tmp_path, monkeypatch
):
    from safetensors.torch import save_file

    from export.model import make_model
    from training.feature_cache import file_hash
    from training.research_data import canonical
    from training.selfplay_actor import ActorConfig
    from training.selfplay_generations import make_protocol, run_generations
    from training.selfplay_search import SearchConfig
    from training.selfplay_training import TrainConfig

    source = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2], text=True
    ).strip()
    # The test must reach model/lineage checks under intentional source mutation.
    # Production still calls the real clean-checkout guard (covered separately).
    from training import selfplay_generations as generations

    def source_binding(commit):
        assert commit == source

    monkeypatch.setattr(generations, "_source_check", source_binding)
    model = tmp_path / "base.safetensors"
    save_file(make_model(314159).state_dict(), model)
    protected = tmp_path / "protected.json"
    provenance = {
        "m6_dataset_revision": "6e7fb29d2469b56a895042fbb089d86e7b4d074f",
        "p5_evaluation_proof_sha256": "c" * 64,
        "p51_dataset_revision": "2" * 40,
    }
    protected.write_text(
        canonical(
            {
                "schema": "voxelshogi-protected-inputs-v1",
                "provenance": provenance,
                "ids": ["f" * 64],
            }
        )
    )
    p = make_protocol(
        source,
        base_model_sha256=file_hash(model),
        protection_sha256=file_hash(protected),
        protection_count=1,
        protection_provenance=provenance,
    )
    p.update(
        generations=2,
        episodes_per_generation=2,
        replay_capacity=4,
        opening_plies=1,
        families=p["families"][:2],
    )
    p["actor"] = asdict(
        ActorConfig(
            max_plies=1,
            temperature_plies=0,
            noise_fraction=0,
            search=SearchConfig(simulations=1),
        )
    )
    p["training"] = asdict(
        TrainConfig(device="cpu", batch_size=2, save_every=1, threads=1)
    )
    full = run_generations(p, model, protected, tmp_path / "full")
    partial = run_generations(
        p, model, protected, tmp_path / "partial", max_new_generations=1
    )
    assert not partial["complete"] and partial["generations_completed"] == 1
    shutil.copytree(tmp_path / "partial", tmp_path / "other-instance")
    resumed = run_generations(p, model, protected, tmp_path / "other-instance")
    assert full["complete"] and resumed["complete"]
    assert full["generations_completed"] == resumed["generations_completed"] == 2
    assert full["next_slot"] == resumed["next_slot"] == 4
    a = json.loads((tmp_path / "full/run.json").read_text())
    b = json.loads((tmp_path / "other-instance/run.json").read_text())
    assert [g["model_sha256"] for g in a["generations"]] == [
        g["model_sha256"] for g in b["generations"]
    ]
    assert a["generations"][0]["model_sha256"] != p["base_model_sha256"]
    assert (
        a["generations"][1]["parent_model_sha256"]
        == a["generations"][0]["model_sha256"]
    )
    assert (tmp_path / "full/replay/buffer.json").read_bytes() == (
        tmp_path / "other-instance/replay/buffer.json"
    ).read_bytes()

    # Publication failure occurs after generation commit. Retry must publish the
    # same frozen generation before starting another episode or optimizer step.
    pending = tmp_path / "publication-pending"

    def failed_publication(record, folder):
        assert record["generation"] == 0
        assert folder == pending
        raise OSError("publication transport interrupted")

    with pytest.raises(OSError, match="publication transport"):
        run_generations(
            p,
            model,
            protected,
            pending,
            max_new_generations=1,
            on_generation=failed_publication,
        )
    committed = json.loads((pending / "run.json").read_text())
    assert len(committed["generations"]) == 1 and committed["publications"] == []
    frozen_generation = committed["generations"][0]
    replay_before = (pending / "replay/buffer.json").read_bytes()
    calls = []

    def publish(record, folder):
        assert record == frozen_generation and folder == pending
        calls.append(record["generation"])
        return {
            key: {
                "verified": True,
                "dry_run": False,
                "community_disabled": True,
                "repo_type": kind,
                "repo_id": "voxelshogi/fixture-" + key,
                "hub_commit": "1" * 40,
                "release_sha256": "2" * 64,
            }
            for key, kind in (("dataset", "dataset"), ("state", "model"))
        }

    retried = run_generations(
        p, model, protected, pending, stop_requested=lambda: True, on_generation=publish
    )
    assert calls == [0] and retried["reason"] == "stopped"
    assert retried["generations_completed"] == retried["published_generations"] == 1
    assert retried["externally_persisted"] and not retried["complete"]
    assert retried["next_slot"] == 2
    assert (pending / "replay/buffer.json").read_bytes() == replay_before
    published = json.loads((pending / "run.json").read_text())
    assert published["generations"] == committed["generations"]
    assert [x["generation"] for x in published["publications"]] == [0]

    # Metadata must not be trusted when the saved parent/model lineage differs.
    damaged = tmp_path / "damaged"
    shutil.copytree(tmp_path / "full", damaged)
    manifest = json.loads((damaged / "run.json").read_text())
    manifest["generations"][0]["parent_model_sha256"] = "0" * 64
    (damaged / "run.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="lineage"):
        run_generations(p, model, protected, damaged)
    manifest["generations"][0]["parent_model_sha256"] = p["base_model_sha256"]
    (damaged / "run.json").write_text(json.dumps(manifest))
    weights = damaged / manifest["generations"][0]["file"]
    with weights.open("ab") as handle:
        handle.write(b"changed bytes")
    with pytest.raises(ValueError, match="lineage"):
        run_generations(p, model, protected, damaged)
