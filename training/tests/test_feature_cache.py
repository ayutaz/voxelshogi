"""Real Rust/Parquet/NumPy/Torch plumbing, executed on Linux CI only."""

import json

import pytest


def examples():
    from voxelshogi import Game

    from training.tests.test_engine import corner_position
    from training.tests.test_supervision import row

    for game_id, split in (
        ("g000002", "train"),
        ("g000044", "val"),
        ("g000050", "test"),
    ):
        game = Game(corner_position())
        for ply in range(2 if split == "train" else 1):
            snapshot = game.snapshot()
            legal = game.legal_actions()
            example = row(game_id, split)
            example.update(
                {
                    key: snapshot[key]
                    for key in ("vsfen", "side", "hash", "finished", "evaluation")
                }
            )
            example.update(
                initial=game.record()["initial"],
                history=game.record()["moves"],
                ply=ply,
                legal_moves=sorted(legal.values()),
                legal_actions=sorted(legal),
                played_move=legal[min(legal)],
                teacher=json.dumps(
                    {
                        "best_move": legal[min(legal)],
                        "score": 0,
                        "completed_depth": 1,
                        "nodes": 8,
                        "stop_reason": "depth",
                    }
                ),
            )
            yield example
            game.play(example["played_move"])


def make_cache(tmp_path):
    from training.feature_cache import write_cache
    from training.supervision import label_contract

    audit = {
        "contract": label_contract(),
        "counts": {
            "eligible_teachers": 4,
            "teacher_splits": {"train": 2, "val": 1, "test": 1},
        },
    }
    folder = tmp_path / "cache"
    write_cache(examples(), folder, audit=audit, source_commit="a" * 40)
    return folder


def test_cache_replays_history_and_streams_only_requested_split(tmp_path):
    import numpy as np

    from training.feature_cache import FeatureCache

    folder = make_cache(tmp_path)
    cache = FeatureCache(folder)
    assert cache.manifest["count"] == 4
    assert isinstance(cache.features, np.memmap) and cache.features.shape == (
        4,
        729,
        43,
    )
    # Corner kings in Black's canonical frame; all remaining squares are empty.
    first = np.zeros((729, 43), dtype=np.float32)
    first[:, 0] = 1
    first[728, 0], first[728, 8] = 0, 1
    first[0, 0], first[0, 22] = 0, 1
    np.testing.assert_array_equal(cache.features[0], first)
    batches = list(cache.batches("train", batch_size=3, seed=314159, epoch=0))
    assert len(batches) == 1 and set(batches[0].ids) == {"g000002:0", "g000002:1"}
    assert batches[0].features.shape == (2, 729, 43)
    assert batches[0].values.tolist() == [0, 0]
    assert all(
        action in legal
        for action, legal in zip(
            batches[0].actions.tolist(), batches[0].legal_actions, strict=True
        )
    )
    assert [
        b.ids for b in cache.batches("test", batch_size=1, seed=314159, epoch=0)
    ] == [("g000050:0",)]
    assert (
        list(cache.batches("train", batch_size=3, seed=314159, epoch=0, start_batch=1))
        == []
    )
    with pytest.raises(ValueError):
        list(cache.batches("unknown", batch_size=1, seed=314159, epoch=0))


def test_cache_requires_complete_files_hashes_and_pinned_provenance(tmp_path):
    from training.feature_cache import FeatureCache

    folder = make_cache(tmp_path)
    manifest = folder / "manifest.json"
    original = manifest.read_text()
    value = json.loads(original)
    value["audit"]["contract"]["revision"] = "b" * 40
    manifest.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="contract"):
        FeatureCache(folder)
    manifest.write_text(original)
    path = folder / "features.npy"
    with path.open("r+b") as stream:
        stream.seek(-1, 2)
        stream.write(b"x")
    with pytest.raises(ValueError, match="hash"):
        FeatureCache(folder)
    manifest.unlink()
    with pytest.raises(ValueError, match="incomplete"):
        FeatureCache(folder)


def test_cache_refuses_wrong_replay_and_never_commits_incomplete_output(tmp_path):
    from training.feature_cache import write_cache
    from training.supervision import label_contract

    rows = list(examples())
    rows[1]["hash"] = "0" * 16
    audit = {
        "contract": label_contract(),
        "counts": {
            "eligible_teachers": 4,
            "teacher_splits": {"train": 2, "val": 1, "test": 1},
        },
    }
    folder = tmp_path / "bad"
    with pytest.raises(ValueError, match="replay"):
        write_cache(rows, folder, audit=audit, source_commit="a" * 40)
    assert not (folder / "manifest.json").exists()
    with pytest.raises(FileExistsError):
        write_cache(rows, folder, audit=audit, source_commit="a" * 40)
