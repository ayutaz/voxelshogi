"""Small interrupted learning runs on Linux CI; never real data/GPU on Mac."""

import json

import pytest


class SmallCache:
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
        if split == "train":
            parts = epoch_batches(
                3, batch_size, seed=seed, epoch=epoch, start_batch=start_batch
            )
        else:
            parts = [[0]]
        for part in parts:
            part = list(part)
            yield Batch(
                torch.zeros(len(part), 1),
                torch.tensor([i % 2 for i in part]),
                torch.tensor([[0.2, -0.3, 0.4][i] for i in part]),
                [[0, 1] for i in part],
                tuple(f"{split}:{i}" for i in part),
                split,
            )


def test_full_and_mid_epoch_resumed_training_match_exactly_and_never_read_test(
    tmp_path,
):
    from training.fit import RunConfig, fit
    from training.tests.test_checkpoint import assert_state_equal, objects

    config = RunConfig(
        epochs=3,
        batch_size=2,
        learning_rate=0.03,
        save_every=2,
        threads=1,
        device="cpu",
    )
    full_cache, resumed_cache = SmallCache(), SmallCache()
    model, optimizer = objects()
    full = fit(
        model,
        optimizer,
        full_cache,
        tmp_path / "full",
        config=config,
        source_commit="a" * 40,
    )
    second, second_optimizer = objects()
    partial = fit(
        second,
        second_optimizer,
        resumed_cache,
        tmp_path / "paused",
        config=config,
        source_commit="a" * 40,
        max_new_steps=3,
    )
    assert partial["reason"] == "max_steps"
    assert partial["progress"] == {
        "epoch": 1,
        "next_batch": 1,
        "step": 3,
        "examples": 5,
        "best_val_loss": partial["progress"]["best_val_loss"],
    }
    second, second_optimizer = objects()
    resumed = fit(
        second,
        second_optimizer,
        resumed_cache,
        tmp_path / "paused",
        config=config,
        source_commit="a" * 40,
        resume=True,
    )
    assert full["reason"] == resumed["reason"] == "complete"
    assert full["progress"] == resumed["progress"]
    assert full["progress"]["step"] == 6 and full["progress"]["examples"] == 9
    assert (
        full_cache.read_splits.count("val")
        == resumed_cache.read_splits.count("val")
        == 3
    )
    assert "test" not in full_cache.read_splits + resumed_cache.read_splits
    assert_state_equal(model.state_dict(), second.state_dict())
    assert_state_equal(optimizer.state_dict(), second_optimizer.state_dict())
    events = [
        json.loads(line)
        for line in (tmp_path / "paused" / "events.jsonl").read_text().splitlines()
    ]
    assert {item["step"] for item in events if item["event"] == "train"} == set(
        range(1, 7)
    )


def test_stop_before_first_step_and_wrong_resume_never_update(tmp_path):
    from training.fit import RunConfig, fit
    from training.tests.test_checkpoint import assert_state_equal, objects

    model, optimizer = objects()
    before = {key: value.detach().clone() for key, value in model.state_dict().items()}
    cache = SmallCache()
    config = RunConfig(device="cpu", learning_rate=0.03, threads=1)
    result = fit(
        model,
        optimizer,
        cache,
        tmp_path / "stopped",
        config=config,
        source_commit="a" * 40,
        stop_requested=lambda: True,
    )
    assert result["reason"] == "stopped" and result["progress"]["step"] == 0
    assert not cache.read_splits
    assert_state_equal(before, model.state_dict())
    with pytest.raises(ValueError, match="binding"):
        fit(
            model,
            optimizer,
            cache,
            tmp_path / "stopped",
            config=RunConfig(device="cpu", learning_rate=0.03, threads=1, batch_size=2),
            source_commit="a" * 40,
            resume=True,
        )
    with pytest.raises(FileExistsError):
        fit(
            model,
            optimizer,
            cache,
            tmp_path / "stopped",
            config=config,
            source_commit="a" * 40,
        )
    assert_state_equal(before, model.state_dict())


def test_stopping_during_validation_saves_pending_epoch_and_resumes_it(tmp_path):
    from training.fit import RunConfig, fit
    from training.tests.test_checkpoint import objects

    model, optimizer = objects()
    cache = SmallCache()

    def stop():
        return "val" in cache.read_splits

    config = RunConfig(device="cpu", learning_rate=0.03, threads=1)
    partial = fit(
        model,
        optimizer,
        cache,
        tmp_path / "paused",
        config=config,
        source_commit="a" * 40,
        stop_requested=stop,
    )
    assert partial["reason"] == "stopped"
    assert partial["progress"]["step"] == 3 and partial["progress"]["epoch"] == 0
    assert (
        partial["progress"]["next_batch"] == 3
        and partial["progress"]["best_val_loss"] is None
    )
    resumed = fit(
        model,
        optimizer,
        cache,
        tmp_path / "paused",
        config=config,
        source_commit="a" * 40,
        resume=True,
    )
    assert resumed["reason"] == "complete" and resumed["progress"]["step"] == 3
    assert resumed["progress"]["best_val_loss"] is not None


def test_best_model_uses_lowest_validation_loss_even_when_last_epoch_regresses(
    tmp_path, monkeypatch
):
    from training import fit as learning_run
    from training.checkpoint import load_checkpoint
    from training.tests.test_checkpoint import objects

    losses = iter([3.0, 1.0, 2.0])  # Independent selection oracle: epoch 2 must win.

    def validation(model, batches, *, split):
        assert split == "val" and list(batches)
        return {"examples": 1, "loss": next(losses)}

    monkeypatch.setattr(learning_run, "evaluate_model", validation)
    model, optimizer = objects()
    folder = tmp_path / "selection"
    config = learning_run.RunConfig(
        epochs=3, batch_size=2, learning_rate=0.03, threads=1, device="cpu"
    )
    report = learning_run.fit(
        model, optimizer, SmallCache(), folder, config=config, source_commit="a" * 40
    )
    assert report["progress"]["best_val_loss"] == 1.0
    binding = json.loads((folder / "run.json").read_text())["binding"]
    best = load_checkpoint(
        folder / "checkpoints", model, optimizer, binding=binding, which="best"
    )
    assert best["epoch"] == 2 and best["step"] == 4 and best["best_val_loss"] == 1.0
