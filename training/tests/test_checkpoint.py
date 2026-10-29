"""Checkpoint round trips and interrupted updates; Linux tensor execution only."""

import random

import pytest


def assert_state_equal(left, right):
    import torch

    if isinstance(left, torch.Tensor):
        torch.testing.assert_close(left, right, rtol=0, atol=0)
    elif isinstance(left, dict):
        assert left.keys() == right.keys()
        for key in left:
            assert_state_equal(left[key], right[key])
    elif isinstance(left, (list, tuple)):
        assert len(left) == len(right)
        for a, b in zip(left, right, strict=True):
            assert_state_equal(a, b)
    else:
        assert left == right


def objects():
    import torch

    from training.tests.test_learning import toy_model

    model = toy_model()
    return model, torch.optim.AdamW(
        model.parameters(), lr=0.03, foreach=False, fused=False
    )


def binding():
    return {
        "source_commit": "a" * 40,
        "cache_sha256": "b" * 64,
        "config": {"seed": 314159},
        "environment": {"device": "cpu"},
    }


def test_checkpoint_restores_optimizer_rng_and_exact_continuation(
    tmp_path, monkeypatch
):
    import numpy as np
    import torch

    from training.checkpoint import load_checkpoint, save_checkpoint, seed_all
    from training.learning import train_step
    from training.tests.test_learning import batch

    seed_all(314159)
    model, optimizer = objects()
    for _ in range(2):
        train_step(model, optimizer, batch(values=[random.random() * 0.1]))
    progress = {
        "epoch": 1,
        "next_batch": 2,
        "step": 2,
        "examples": 2,
        "best_val_loss": None,
    }
    receipt = save_checkpoint(
        tmp_path, model, optimizer, progress=progress, binding=binding()
    )
    assert receipt["step"] == 2 and receipt["verified"] is True

    def continue_training():
        for _ in range(3):
            value = random.random() + np.random.random() + torch.rand(()).item()
            train_step(model, optimizer, batch(values=[value / 3]))
        return random.random(), np.random.random(), torch.rand(2)

    samples = continue_training()
    expected_model = {k: v.detach().clone() for k, v in model.state_dict().items()}
    import copy

    expected_optimizer = copy.deepcopy(optimizer.state_dict())
    model, optimizer = objects()  # Construction must not replace saved RNG state.
    original = torch.load
    calls = []

    def checked_load(*args, **kwargs):
        calls.append(kwargs.get("weights_only"))
        return original(*args, **kwargs)

    monkeypatch.setattr(torch, "load", checked_load)
    restored = load_checkpoint(tmp_path, model, optimizer, binding=binding())
    assert restored == progress and calls == [True]
    actual_samples = continue_training()
    assert_state_equal(expected_model, model.state_dict())
    assert_state_equal(expected_optimizer, optimizer.state_dict())
    assert_state_equal(samples, actual_samples)


def test_wrong_binding_and_torn_or_changed_checkpoint_are_rejected(
    tmp_path, monkeypatch
):
    import json

    import torch

    from training.checkpoint import load_checkpoint, save_checkpoint, seed_all

    seed_all(314159)
    model, optimizer = objects()
    progress = {
        "epoch": 0,
        "next_batch": 0,
        "step": 0,
        "examples": 0,
        "best_val_loss": None,
    }
    save_checkpoint(tmp_path, model, optimizer, progress=progress, binding=binding())
    before = {k: v.detach().clone() for k, v in model.state_dict().items()}

    def forbidden_load(*args, **kwargs):
        raise AssertionError(
            "wrong binding/hash must be rejected before deserialization"
        )

    monkeypatch.setattr(torch, "load", forbidden_load)
    for key, value in (
        ("source_commit", "c" * 40),
        ("cache_sha256", "c" * 64),
        ("config", {"seed": 1}),
        ("environment", {"device": "cuda"}),
    ):
        with pytest.raises(ValueError, match="binding"):
            load_checkpoint(
                tmp_path, model, optimizer, binding={**binding(), key: value}
            )
        assert_state_equal(before, model.state_dict())
    pointer = json.loads((tmp_path / "latest.json").read_text())
    state = tmp_path / pointer["directory"] / "state.pt"
    original = state.read_bytes()
    state.write_bytes(b"bad" + original[3:])
    with pytest.raises(ValueError, match="hash"):
        load_checkpoint(tmp_path, model, optimizer, binding=binding())
    state.write_bytes(original)
    (tmp_path / pointer["directory"] / "receipt.json").unlink()
    with pytest.raises(ValueError, match="incomplete"):
        load_checkpoint(tmp_path, model, optimizer, binding=binding())


def test_failed_pointer_commit_preserves_previous_checkpoint(tmp_path, monkeypatch):
    from training import checkpoint

    model, optimizer = objects()
    first = {
        "epoch": 0,
        "next_batch": 0,
        "step": 0,
        "examples": 0,
        "best_val_loss": None,
    }
    checkpoint.save_checkpoint(
        tmp_path, model, optimizer, progress=first, binding=binding()
    )
    replace = checkpoint.os.replace

    def fail_pointer(source, destination):
        if destination.name == "latest.json":
            raise OSError("simulated interruption")
        return replace(source, destination)

    monkeypatch.setattr(checkpoint.os, "replace", fail_pointer)
    with pytest.raises(OSError):
        checkpoint.save_checkpoint(
            tmp_path, model, optimizer, progress={**first, "step": 1}, binding=binding()
        )
    assert (
        checkpoint.load_checkpoint(tmp_path, model, optimizer, binding=binding())
        == first
    )


def test_best_pointer_changes_only_on_validation_selection(tmp_path):
    from training.checkpoint import load_checkpoint, save_checkpoint

    model, optimizer = objects()
    selected = {
        "epoch": 1,
        "next_batch": 0,
        "step": 3,
        "examples": 3,
        "best_val_loss": 0.5,
    }
    save_checkpoint(
        tmp_path, model, optimizer, progress=selected, binding=binding(), best=True
    )
    later = {**selected, "next_batch": 1, "step": 4, "examples": 4}
    save_checkpoint(tmp_path, model, optimizer, progress=later, binding=binding())
    assert load_checkpoint(tmp_path, model, optimizer, binding=binding()) == later
    assert (
        load_checkpoint(tmp_path, model, optimizer, binding=binding(), which="best")
        == selected
    )


def test_retention_keeps_only_latest_best_and_leaves_unrelated_files(tmp_path):
    from training.checkpoint import load_checkpoint, save_checkpoint

    model, optimizer = objects()
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    (unrelated / "keep.txt").write_text("owned by somebody else")
    for step in range(4):
        progress = {
            "epoch": 1,
            "next_batch": step,
            "step": step,
            "examples": step,
            "best_val_loss": 0.5,
        }
        save_checkpoint(
            tmp_path,
            model,
            optimizer,
            progress=progress,
            binding=binding(),
            best=step == 1,
        )
    assert len(list(tmp_path.glob("step-*"))) == 2
    assert load_checkpoint(tmp_path, model, optimizer, binding=binding())["step"] == 3
    assert (
        load_checkpoint(tmp_path, model, optimizer, binding=binding(), which="best")[
            "step"
        ]
        == 1
    )
    assert (unrelated / "keep.txt").read_text() == "owned by somebody else"
