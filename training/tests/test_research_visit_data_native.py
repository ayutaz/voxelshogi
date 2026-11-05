"""Actual Rust feature handoff with synthetic visits/auditor port, Linux only.

This is not a real dataset admission or teacher-quality result.
"""

from copy import deepcopy

import pytest


def source(tmp_path, monkeypatch, *, tamper=False):
    from voxelshogi import Game

    from training import research_visit_data as module
    from training import selfplay_dataset
    from training.evaluation import opening_record
    from training.evaluation_v2 import fingerprint
    from training.feature_cache import file_hash
    from training.research_corpus import admit_metadata
    from training.research_data import input_identity
    from training.research_targets import visit_policy

    folder = tmp_path / "source"
    folder.mkdir()
    (folder / "manifest.json").write_text("{}")
    (folder / "episodes.parquet").write_bytes(b"opaque synthetic fixture")
    protection, screen = tmp_path / "protection.json", tmp_path / "screen.json"
    protection.write_text("{}")
    screen.write_text("{}")
    protocol = {"synthetic_fixture": True}
    episodes, metadata, partition, expected_features = [], [], {}, {}
    for i in range(6):
        opening = opening_record(68000 + i, plies=2)
        game = Game.from_record(opening)
        family = input_identity(game.snapshot())
        assert family not in partition
        partition[family] = ("train", "val", "test")[i // 2]
        episode = {"episode_id": f"episode{i}", "opening": opening, "samples": []}
        for _ in range(2):
            s = game.snapshot()
            legal = sorted(game.legal_actions())
            ply = len(game.record()["moves"])
            sample = {
                "ply": ply,
                "position": s["vsfen"],
                "side": s["side"],
                "legal_actions": legal,
                "policy": visit_policy(legal, {legal[0]: 3, legal[1]: 1}),
                "value": {"kind": "bootstrap-v1", "value": -0.125},
                "move": game.legal_actions()[legal[0]],
            }
            sample_id = f"episode{i}:{ply}"
            metadata.append(
                {
                    "id": sample_id,
                    "family": family,
                    "input": input_identity(s),
                    "value_kind": "bootstrap-v1",
                    "ply": ply,
                }
            )
            expected_features[sample_id] = game.features().copy()
            episode["samples"].append(sample)
            game.play(sample["move"])
        episodes.append(episode)
    admission = admit_metadata(
        metadata,
        partition,
        protected_inputs={"f" * 64},
        final_roots={f"{i:064x}" for i in range(12)},
        minimum_rows={"train": 1, "val": 1, "test": 1},
    )
    assert admission["usable_for_pilot"]
    audit = {
        "schema": "voxelshogi-research-selfplay-corpus-audit-v1",
        "source_manifest_sha256": file_hash(folder / "manifest.json"),
        "source_protocol_sha256": fingerprint(protocol),
        "source_protection_sha256": file_hash(protection),
        "screen_config_sha256": file_hash(screen),
        "metadata": metadata,
        "family_partition": partition,
        "admission": admission,
    }
    m = {"file": {"sha256": file_hash(folder / "episodes.parquet")}}

    def load(*args):
        if tamper:
            (folder / "manifest.json").write_text('{"changed":true}')
        return m, deepcopy(episodes)

    monkeypatch.setattr(
        module, "audit_selfplay_corpus", lambda *args, **kwargs: deepcopy(audit)
    )
    monkeypatch.setattr(selfplay_dataset, "_load", load)
    return folder, protocol, protection, screen, audit, expected_features, episodes


def test_actual_rust_features_match_selected_ids_and_preserve_soft_targets(
    tmp_path, monkeypatch
):
    import numpy as np

    from training.evaluation_v2 import fingerprint
    from training.feature_cache import file_hash
    from training.research_visit_data import encode_corpus
    from training.research_visit_fit import VisitRunConfig

    folder, protocol, protection, screen, audit, expected, episodes = source(
        tmp_path, monkeypatch
    )
    data, evidence = encode_corpus(
        folder,
        protocol,
        protection,
        screen,
        screen_sha256=file_hash(screen),
        expected_audit_sha256=fingerprint(audit),
    )
    assert data.admission_sha256 == fingerprint(audit)
    assert evidence["encoded_rows"] == {"train": 4, "val": 4}
    assert evidence["test_features_encoded"] == 0
    assert evidence["feature_bytes"] == 8 * 729 * 43 * 4
    assert evidence["feature_content_sha256"] == data.digest(
        VisitRunConfig(device="cpu")
    )
    original = {
        e["episode_id"] + ":" + str(s["ply"]): s for e in episodes for s in e["samples"]
    }
    for split in ("train", "val"):
        part = getattr(data, split)
        assert [r["id"] for r in part.rows] == audit["admission"]["selected_ids"][split]
        for row, feature in zip(part.rows, part.features, strict=True):
            np.testing.assert_array_equal(feature, expected[row["id"]])
            assert row["policy"] == original[row["id"]]["policy"]
            assert row["policy"]["probabilities"] == [0.75, 0.25]
            assert row["value"] == {"kind": "bootstrap-v1", "value": -0.125}
    assert not set(audit["admission"]["selected_ids"]["test"]) & {
        r["id"] for r in data.train.rows + data.val.rows
    }


def test_source_change_during_feature_pass_never_returns_an_admitted_corpus(
    tmp_path, monkeypatch
):
    from training.evaluation_v2 import fingerprint
    from training.feature_cache import file_hash
    from training.research_visit_data import encode_corpus

    folder, protocol, protection, screen, audit, *_ = source(
        tmp_path, monkeypatch, tamper=True
    )
    with pytest.raises(ValueError, match="source changed"):
        encode_corpus(
            folder,
            protocol,
            protection,
            screen,
            screen_sha256=file_hash(screen),
            expected_audit_sha256=fingerprint(audit),
        )
