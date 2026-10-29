"""Linux-only tensor/JSON archives; no pickle is put in a portable archive."""

import pytest


def test_tensor_tree_preserves_types_metadata_and_exact_values_without_code_objects():
    from collections import OrderedDict

    import torch

    from training.resume_archive import decode_tree, encode_tree
    from training.tests.test_checkpoint import assert_state_equal

    ordered = OrderedDict([(3, torch.tensor([1.0, -2.0]))])
    ordered._metadata = {"": {"version": 1}}
    value = {
        "model": ordered,
        "rng": (None, True, 17, 0.125, "literal"),
        "bytes": torch.tensor([1, 255], dtype=torch.uint8),
    }
    tree, tensors = encode_tree(value)
    restored = decode_tree(tree, tensors)
    assert_state_equal(value, restored)
    assert (
        type(restored["model"]) is OrderedDict
        and restored["model"]._metadata == ordered._metadata
    )
    assert tensors and all(name.startswith("t") for name in tensors)
    with pytest.raises(ValueError):
        encode_tree({"callback": lambda: None})
    with pytest.raises(ValueError):
        encode_tree({"bad": float("nan")})
    with pytest.raises(ValueError):
        decode_tree({"type": "execute-python", "value": "ignored"}, tensors)
    with pytest.raises(ValueError):
        decode_tree(tree, {**tensors, "unused": torch.zeros(1)})


def test_archive_restore_continues_identically_without_original_private_checkpoint(
    tmp_path,
):
    import json
    import shutil

    from training.fit import RunConfig, fit
    from training.resume_archive import pack_run, restore_run
    from training.tests.test_checkpoint import assert_state_equal, objects
    from training.tests.test_training_runner import SmallCache

    config = RunConfig(
        epochs=3, batch_size=2, learning_rate=0.03, threads=1, device="cpu"
    )
    model, optimizer = objects()
    full = fit(
        model,
        optimizer,
        SmallCache(),
        tmp_path / "full",
        config=config,
        source_commit="a" * 40,
    )
    partial, partial_optimizer = objects()
    source = tmp_path / "partial"
    fit(
        partial,
        partial_optimizer,
        SmallCache(),
        source,
        config=config,
        source_commit="a" * 40,
        max_new_steps=3,
    )
    binding = json.loads((source / "run.json").read_text())["binding"]
    archive = tmp_path / "archive"
    manifest = pack_run(source, archive)
    assert manifest["schema"] == "voxelshogi-resume-archive-v1"
    assert manifest["roles"]["latest"]["progress"]["step"] == 3
    assert manifest["roles"]["best"]["progress"]["step"] == 2
    assert not list(archive.rglob("*.pt"))
    assert {p.suffix for p in archive.rglob("*") if p.is_file()} <= {
        ".json",
        ".safetensors",
    }
    shutil.rmtree(source)  # Only this disposable fixture; recovery cannot rely on it.
    restored = tmp_path / "restored"
    restore_run(archive, restored, expected_binding=binding)
    resumed_model, resumed_optimizer = objects()
    resumed = fit(
        resumed_model,
        resumed_optimizer,
        SmallCache(),
        restored,
        config=config,
        source_commit="a" * 40,
        resume=True,
    )
    assert resumed["progress"] == full["progress"]
    assert_state_equal(model.state_dict(), resumed_model.state_dict())
    assert_state_equal(optimizer.state_dict(), resumed_optimizer.state_dict())


def test_archive_hash_and_expected_binding_are_checked_before_restore_writes(tmp_path):
    import json

    from training.fit import RunConfig, fit
    from training.resume_archive import pack_run, restore_run
    from training.tests.test_checkpoint import objects
    from training.tests.test_training_runner import SmallCache

    model, optimizer = objects()
    source = tmp_path / "source"
    fit(
        model,
        optimizer,
        SmallCache(),
        source,
        config=RunConfig(device="cpu", learning_rate=0.03, threads=1),
        source_commit="a" * 40,
        max_new_steps=1,
    )
    binding = json.loads((source / "run.json").read_text())["binding"]
    archive = tmp_path / "archive"
    pack_run(source, archive)
    destination = tmp_path / "wrong"
    with pytest.raises(ValueError):
        restore_run(
            archive,
            destination,
            expected_binding={**binding, "cache_sha256": "b" * 63 + "c"},
        )
    assert not destination.exists()
    path = archive / "latest/state.safetensors"
    with path.open("r+b") as stream:
        stream.seek(-1, 2)
        stream.write(b"x")
    with pytest.raises(ValueError, match="hash"):
        restore_run(archive, destination, expected_binding=binding)
    assert not destination.exists()
