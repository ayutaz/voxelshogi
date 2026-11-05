"""Actual four-model gradients and safe-archive continuation on Linux CI."""

import json
from dataclasses import replace

import pytest

from export.research_contract import ARCHITECTURES
from training.tests.test_research_model_native import tiny


class TinyResearchCache:
    sha256 = "b" * 64
    manifest = {
        "audit": {"counts": {"teacher_splits": {"train": 3, "val": 1, "test": 1}}}
    }

    def __init__(self):
        self.read_splits = []

    def batches(self, split, *, batch_size, seed, epoch=0, start_batch=0):
        import torch

        from training.learning import Batch, epoch_batches

        self.read_splits.append(split)
        parts = (
            epoch_batches(
                3, batch_size, seed=seed, epoch=epoch, start_batch=start_batch
            )
            if split == "train"
            else [[0]]
        )
        for part in parts:
            features = (
                torch.arange(len(part) * 8 * 43, dtype=torch.float32).reshape(
                    len(part), 8, 43
                )
                / 1000
            )
            yield Batch(
                features,
                torch.tensor([i % 2 for i in part]),
                torch.tensor([[0.2, -0.3, 0.4][i] for i in part]),
                [[0, 1] for i in part],
                tuple(f"{split}:{i}" for i in part),
                split,
            )


def payload(folder):
    import torch

    from training.checkpoint import checkpoint_receipt

    binding = json.loads((folder / "run.json").read_text())["binding"]
    path, _ = checkpoint_receipt(folder / "checkpoints", binding=binding)
    return torch.load(path, map_location="cpu", weights_only=True)


@pytest.mark.parametrize("architecture", ARCHITECTURES)
def test_all_four_model_runs_match_exactly_after_mid_epoch_safe_archive_resume(
    tmp_path, architecture
):
    from training.research_fit import ResearchRunConfig, fit_research
    from training.resume_archive import pack_run, restore_run
    from training.tests.test_checkpoint import assert_state_equal

    config = ResearchRunConfig(
        architecture=tiny(architecture),
        seed=67003,
        epochs=3,
        batch_size=2,
        learning_rate=0.003,
        save_every=2,
        threads=1,
        device="cpu",
    )
    full_cache, partial_cache = TinyResearchCache(), TinyResearchCache()
    full_folder, partial_folder = tmp_path / "full", tmp_path / "partial"
    full = fit_research(full_cache, full_folder, config=config, source_commit="a" * 40)
    partial = fit_research(
        partial_cache,
        partial_folder,
        config=config,
        source_commit="a" * 40,
        max_new_steps=3,
    )
    assert partial["reason"] == "max_steps"
    assert (
        partial["progress"]["epoch"],
        partial["progress"]["next_batch"],
        partial["progress"]["examples"],
    ) == (1, 1, 5)
    before = payload(partial_folder)
    archive, restored = tmp_path / "archive", tmp_path / "restored"
    manifest = pack_run(partial_folder, archive, profile="research")
    assert set(manifest["roles"]) == {"latest", "best"}
    restore_run(
        archive, restored, expected_binding=before["binding"], profile="research"
    )
    assert_state_equal(before, payload(restored))
    resumed = fit_research(
        partial_cache, restored, config=config, source_commit="a" * 40, resume=True
    )
    assert full["reason"] == resumed["reason"] == "complete"
    assert full["progress"] == resumed["progress"]
    assert (full["progress"]["step"], full["progress"]["examples"]) == (6, 9)
    actual, expected = payload(restored), payload(full_folder)
    assert_state_equal(expected, actual)
    # An optimizer that never steps would otherwise trivially match after resume.
    assert len(actual["optimizer"]["state"]) > 0
    assert {
        int(state["step"].item()) for state in actual["optimizer"]["state"].values()
    } == {6}
    assert "test" not in full_cache.read_splits + partial_cache.read_splits
    assert (
        full_cache.read_splits.count("val")
        == partial_cache.read_splits.count("val")
        == 3
    )

    def train_ids(folder):
        return [
            entry["ids"]
            for entry in map(
                json.loads, (folder / "events.jsonl").read_text().splitlines()
            )
            if entry["event"] == "train"
        ]

    assert train_ids(full_folder) == train_ids(restored)
    before = (restored / "checkpoints/latest.json").read_bytes()
    for changed in (
        replace(config, seed=67004),
        replace(config, architecture=replace(config.architecture, layers=2)),
    ):
        with pytest.raises(ValueError, match="binding"):
            fit_research(
                partial_cache,
                restored,
                config=changed,
                source_commit="a" * 40,
                resume=True,
            )
        assert (restored / "checkpoints/latest.json").read_bytes() == before


@pytest.mark.parametrize("architecture", ARCHITECTURES)
def test_selected_seed_initializes_the_requested_model_and_stop_preserves_it(
    tmp_path, architecture
):
    from export.research_model import make_research_model
    from training.research_fit import ResearchRunConfig, fit_research
    from training.tests.test_checkpoint import assert_state_equal

    config = ResearchRunConfig(
        architecture=tiny(architecture), seed=17, device="cpu", threads=1
    )
    cache = TinyResearchCache()
    folder = tmp_path / "stopped"
    result = fit_research(
        cache,
        folder,
        config=config,
        source_commit="a" * 40,
        stop_requested=lambda: True,
    )
    assert result["reason"] == "stopped" and result["progress"]["step"] == 0
    assert not cache.read_splits
    state = payload(folder)
    assert_state_equal(
        make_research_model(config.architecture, seed=17).state_dict(), state["model"]
    )
    assert state["optimizer"]["state"] == {}
    assert state["binding"]["config"]["architecture"]["architecture"] == architecture
