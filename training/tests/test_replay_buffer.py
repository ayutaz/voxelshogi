"""Fake completed episodes exercise durability and cursors; no native games."""

import json
from dataclasses import replace

import pytest

from training.selfplay_actor import play_episode
from training.tests.test_replay_metadata import from_record
from training.tests.test_selfplay_actor import config, root
from training.tests.test_selfplay_search import evaluator


def buffer(folder, capacity=2):
    from training.replay import ReplayBuffer

    return ReplayBuffer(
        folder,
        source_commit="1" * 40,
        run_id="b" * 64,
        capacity=capacity,
        game_from_record=from_record,
    )


def item(seed=0):
    cfg = replace(config(1, bootstrap_discount=0.5), seed=seed)
    e = play_episode(
        root(), evaluator([]), cfg, model_sha256="a" * 64, source_commit="1" * 40
    )
    return e, cfg


def append(b, slot, seed):
    e, cfg = item(seed)
    return b.append(slot, e, model_sha256="a" * 64, config=cfg)


def test_cursor_is_committed_with_complete_episode_and_window_keeps_latest(tmp_path):
    b = buffer(tmp_path / "buffer")
    assert b.next_slot == 0 and b.episodes() == []
    descriptors = [append(b, i, i) for i in range(3)]
    assert b.next_slot == 3
    assert [e["config"]["seed"] for e in b.episodes()] == [1, 2]
    assert [e["config"]["seed"] for e in b.episodes(window=False)] == [0, 1, 2]
    restored = buffer(tmp_path / "buffer")
    assert restored.next_slot == 3 and restored.episodes() == b.episodes()
    for descriptor in descriptors:
        assert (tmp_path / "buffer" / descriptor["path"]).is_file()


def test_identical_retry_is_idempotent_but_gap_and_conflicting_slot_are_rejected(
    tmp_path,
):
    b = buffer(tmp_path / "buffer")
    first = append(b, 0, 0)
    assert append(b, 0, 0) == first and b.next_slot == 1
    for slot, seed in ((0, 1), (2, 2), (True, 1), (1, 0)):
        with pytest.raises(ValueError):
            append(b, slot, seed)
    assert b.next_slot == 1


def test_partial_episode_never_advances_the_cursor(tmp_path):
    b = buffer(tmp_path / "buffer")
    e, cfg = item()
    e["complete"] = False
    with pytest.raises(ValueError):
        b.append(0, e, model_sha256="a" * 64, config=cfg)
    assert b.next_slot == 0
    assert not list((tmp_path / "buffer" / "episodes").glob("*.json"))


def test_crash_before_index_commit_leaves_recoverable_orphan_not_a_new_slot(
    tmp_path, monkeypatch
):
    from training import replay

    b = buffer(tmp_path / "buffer")
    real_atomic = replay.atomic_json

    def fail_index(path, data):
        if path.name == "buffer.json":
            raise OSError("simulated index commit interruption")
        return real_atomic(path, data)

    monkeypatch.setattr(replay, "atomic_json", fail_index)
    with pytest.raises(OSError):
        append(b, 0, 0)
    monkeypatch.setattr(replay, "atomic_json", real_atomic)
    assert b.next_slot == 0
    assert len(list((tmp_path / "buffer" / "episodes").glob("*.json"))) == 1
    descriptor = append(buffer(tmp_path / "buffer"), 0, 0)
    assert descriptor["slot"] == 0 and b.next_slot == 1


def test_corrupt_episode_or_rewritten_inventory_cannot_bypass_replay(tmp_path):
    import hashlib

    b = buffer(tmp_path / "buffer")
    descriptor = append(b, 0, 0)
    path = tmp_path / "buffer" / descriptor["path"]
    episode = json.loads(path.read_text())
    episode["samples"][0]["value"]["value"] = 0
    path.write_text(json.dumps(episode))
    with pytest.raises(ValueError, match="hash"):
        b.episodes()
    manifest_path = tmp_path / "buffer" / "buffer.json"
    manifest = json.loads(manifest_path.read_text())
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    new_path = path.with_name(sha + ".json")
    path.rename(new_path)
    manifest["entries"][0].update(
        sha256=sha, bytes=len(raw), path="episodes/" + new_path.name
    )
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="value target"):
        buffer(tmp_path / "buffer")


def test_source_run_or_capacity_mismatch_is_rejected_without_changing_data(tmp_path):
    from training.replay import ReplayBuffer

    folder = tmp_path / "buffer"
    b = buffer(folder)
    append(b, 0, 0)
    original = (folder / "buffer.json").read_bytes()
    for field, value in (
        ("source_commit", "2" * 40),
        ("run_id", "c" * 64),
        ("capacity", 3),
    ):
        args = {"source_commit": "1" * 40, "run_id": "b" * 64, "capacity": 2}
        args[field] = value
        with pytest.raises(ValueError, match="binding"):
            ReplayBuffer(folder, **args, game_from_record=from_record)
        assert (folder / "buffer.json").read_bytes() == original


def test_semantically_identical_byte_change_still_fails_hash_verification(tmp_path):
    b = buffer(tmp_path / "buffer")
    descriptor = append(b, 0, 0)
    path = tmp_path / "buffer" / descriptor["path"]
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="hash"):
        b.episodes()


def test_repeated_episode_in_rewritten_index_is_rejected(tmp_path):
    b = buffer(tmp_path / "buffer")
    append(b, 0, 0)
    path = tmp_path / "buffer" / "buffer.json"
    manifest = json.loads(path.read_text())
    manifest["entries"].append({**manifest["entries"][0], "slot": 1})
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="inventory"):
        b.episodes()


def test_unowned_and_symlink_paths_are_refused(tmp_path):
    folder = tmp_path / "existing"
    folder.mkdir()
    (folder / "keep.txt").write_text("unrelated")
    with pytest.raises(ValueError):
        buffer(folder)
    link = tmp_path / "link"
    link.symlink_to(folder, target_is_directory=True)
    with pytest.raises(ValueError):
        buffer(link)
    assert (folder / "keep.txt").read_text() == "unrelated"
