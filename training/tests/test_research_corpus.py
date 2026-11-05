"""Independent family/split and exclusion oracles; no engine/model execution."""

import copy

import pytest


def identity(i):
    return f"{i:064x}"


def fixture():
    families = {
        identity(i): split
        for i, split in enumerate(("train", "train", "val", "val", "test", "test"))
    }
    definitions = [
        ("train-cross", 0, 100),
        ("val-owner", 2, 100),
        ("test-owner", 4, 101),
        ("val-cross", 3, 101),
        ("train-old", 0, 102),
        ("train-final", 0, 5000),
        ("train-dev", 0, 103),
        ("z-duplicate", 0, 104),
        ("a-duplicate", 0, 104),
        ("train-other", 1, 105),
        ("val-other", 3, 106),
        ("test-other", 5, 107),
    ]
    rows = [
        {
            "id": name,
            "family": identity(family),
            "input": identity(input_id),
            "value_kind": "terminal-v1" if name == "test-owner" else "bootstrap-v1",
            "ply": 32,
        }
        for name, family, input_id in definitions
    ]
    return (
        rows,
        families,
        {identity(102)},
        {identity(5000 + i) for i in range(12)},
        {identity(103)},
    )


def admit(*, rows=None, minimum_rows=None):
    from training.research_corpus import admit_metadata

    actual, families, old, final, dev = fixture()
    return admit_metadata(
        actual if rows is None else rows,
        families,
        protected_inputs=old,
        final_roots=final,
        development_inputs=dev,
        minimum_rows=minimum_rows or {"train": 1, "val": 1, "test": 1},
    )


def test_fixed_hash_ranking_groups_all_generations_by_opening_family():
    from training.research_corpus import family_partition

    # SHA-256 ordering independently computed with Node crypto, not this module.
    actual = family_partition([identity(i) for i in range(16)], seed=67011)
    assert {i for i in range(16) if actual[identity(i)] == "val"} == {7, 13}
    assert {i for i in range(16) if actual[identity(i)] == "test"} == {14, 15}
    assert {i for i in range(16) if actual[identity(i)] == "train"} == {
        0,
        1,
        2,
        3,
        4,
        5,
        6,
        8,
        9,
        10,
        11,
        12,
    }
    assert (
        family_partition(list(reversed([identity(i) for i in range(16)])), seed=67011)
        == actual
    )
    assert family_partition([identity(i) for i in range(16)], seed=67012) != actual


def test_protection_cross_split_and_duplicates_have_independent_exact_counts():
    result = admit()
    assert result["selected_ids"] == {
        "train": ["a-duplicate", "train-other"],
        "val": ["val-other", "val-owner"],
        "test": ["test-other", "test-owner"],
    }
    assert result["indices_by_split"] == {
        "train": [8, 9],
        "val": [10, 1],
        "test": [11, 2],
    }
    assert result["counts"] == {
        "raw_samples": 12,
        "retained": 6,
        "excluded_protected": 3,
        "excluded_cross_split": 2,
        "excluded_repeated_inputs": 1,
    }
    assert result["rows_by_split"] == {"train": 2, "val": 2, "test": 2}
    assert result["retained_families_by_split"] == {"train": 2, "val": 2, "test": 2}
    assert result["overlaps_by_protection_role"] == {
        "legacy": 1,
        "final_roots": 1,
        "development": 1,
    }
    assert result["value_origins"]["test"] == {"bootstrap-v1": 1, "terminal-v1": 1}
    assert result["usable_for_pilot"] is True
    assert result["verification_scope"].startswith("metadata admission")
    rows = fixture()[0]
    reversed_result = admit(rows=list(reversed(rows)))
    assert reversed_result["selected_ids"] == result["selected_ids"]
    assert reversed_result["selection_sha256"] == result["selection_sha256"]
    assert (
        admit(minimum_rows={"train": 256, "val": 64, "test": 64})["usable_for_pilot"]
        is False
    )


def test_no_remaining_rows_is_a_negative_readiness_result_and_keeps_counts():
    from training.research_corpus import admit_metadata

    rows, families, old, final, dev = fixture()
    result = admit_metadata(
        rows,
        families,
        protected_inputs={r["input"] for r in rows},
        final_roots=final,
        development_inputs=dev,
    )
    assert result["usable_for_pilot"] is False
    assert (
        result["counts"]["excluded_protected"] == 12
        and result["counts"]["retained"] == 0
    )
    assert result["selected_ids"] == {"train": [], "val": [], "test": []}


@pytest.mark.parametrize(
    "change",
    ["id", "input", "unknown-family", "value-kind", "ply", "missing", "foreign"],
)
def test_invalid_or_incomplete_sample_metadata_is_rejected(change):
    rows = copy.deepcopy(fixture()[0])
    if change == "id":
        rows[1]["id"] = rows[0]["id"]
    elif change == "input":
        rows[0]["input"] = "bad"
    elif change == "unknown-family":
        rows[0]["family"] = identity(999)
    elif change == "value-kind":
        rows[0]["value_kind"] = "cutoff-is-draw"
    elif change == "ply":
        rows[0]["ply"] = True
    elif change == "missing":
        del rows[0]["input"]
    else:
        rows[0]["score"] = 1
    with pytest.raises(ValueError):
        admit(rows=rows)


def test_split_and_protection_contracts_cannot_be_empty_or_weakened():
    from training.research_corpus import admit_metadata, family_partition

    ids = [identity(i) for i in range(16)]
    for families in ([], ids + [ids[0]], ["not-a-sha"] * 16, ids[:5]):
        with pytest.raises(ValueError):
            family_partition(families, seed=67011)
    for seed in (True, -1, "67011"):
        with pytest.raises(ValueError):
            family_partition(ids, seed=seed)
    rows, families, old, final, dev = fixture()
    for changes in (
        {"protected_inputs": set()},
        {"final_roots": set(list(final)[:11])},
        {"development_inputs": {"bad"}},
        {"minimum_rows": {"train": 0, "val": 1, "test": 1}},
    ):
        kwargs = {
            "protected_inputs": old,
            "final_roots": final,
            "development_inputs": dev,
        } | changes
        with pytest.raises(ValueError):
            admit_metadata(rows, families, **kwargs)


def test_actual_dataset_entrypoint_refuses_mac_before_importing_engine(
    monkeypatch, tmp_path
):
    from training import research_corpus as module

    monkeypatch.setattr(module.sys, "platform", "darwin")
    with pytest.raises(ValueError, match="Linux"):
        module.audit_selfplay_corpus(
            tmp_path, {}, tmp_path, tmp_path, screen_sha256="a" * 64
        )


def test_linux_enumerator_uses_all_generations_and_replayed_sample_identities(
    tmp_path, monkeypatch
):
    result = enumerate_fixture(tmp_path, monkeypatch)
    assert result["source_episodes"] == 12 and result["source_generations"] == 2
    assert result["admission"]["counts"] == {
        "raw_samples": 24,
        "retained": 12,
        "excluded_protected": 0,
        "excluded_cross_split": 0,
        "excluded_repeated_inputs": 12,
    }
    assert result["admission"]["rows_by_split"] == {"train": 4, "val": 4, "test": 4}
    assert result["labels_adopted"] == 0
    assert result["admission"]["usable_for_pilot"] is False


def enumerate_fixture(tmp_path, monkeypatch, *, tamper=False):
    import json
    import sys
    from types import SimpleNamespace

    from training import research_corpus as module
    from training import selfplay_dataset, selfplay_generations
    from training.feature_cache import file_hash

    class Game:
        def __init__(self, record):
            self.family = record["family"]
            self.moves = []

        @classmethod
        def from_record(cls, record):
            return cls(record)

        def snapshot(self):
            return {
                "input": identity(self.family + 1000 * len(self.moves)),
                "vsfen": f"family{self.family}-ply{len(self.moves)}",
                "side": "b" if not self.moves else "w",
            }

        def record(self):
            return {"moves": list(self.moves)}

        def play(self, move):
            self.moves.append(move)

    episodes = [
        {
            "episode_id": f"g{generation}-family{family}",
            "opening": {"family": family},
            "samples": [
                {
                    "position": f"family{family}-ply{ply}",
                    "side": "b" if ply == 0 else "w",
                    "ply": ply,
                    "move": "fixture-move",
                    "value": {"kind": "bootstrap-v1"},
                }
                for ply in range(2)
            ],
        }
        for generation in range(2)
        for family in range(6)
    ]
    folder = tmp_path / "dataset"
    folder.mkdir()
    manifest = folder / "manifest.json"
    manifest.write_text("{}")
    (folder / "episodes.parquet").write_bytes(b"fake opaque fixture")
    protected = tmp_path / "protected.json"
    protected.write_text("{}")
    screen = tmp_path / "screen.json"
    screen.write_text("{}")
    screen_sha256 = file_hash(screen)
    protocol = {"source": "fixture"}

    def load(actual_folder, actual_protocol):
        assert actual_folder == folder and actual_protocol == protocol
        if tamper:
            manifest.write_text(json.dumps({"changed": True}))
        return {
            "run": {"complete": True, "generations": [0, 1]},
            "file": {"sha256": file_hash(folder / "episodes.parquet")},
        }, episodes

    def protection(actual_path, actual_protocol):
        assert actual_path == protected and actual_protocol == protocol
        return {identity(999)}

    def roots(actual_path, digest):
        assert actual_path == screen and digest == screen_sha256
        return {
            "holdout": {identity(5000 + i) for i in range(12)},
            "development": {identity(6000 + i) for i in range(12)},
        }

    monkeypatch.setattr(module.sys, "platform", "linux")
    monkeypatch.setitem(sys.modules, "voxelshogi", SimpleNamespace(Game=Game))
    monkeypatch.setattr(selfplay_dataset, "_load", load)
    monkeypatch.setattr(selfplay_generations, "_protection", protection)
    monkeypatch.setattr(module, "_screen_protection", roots)
    monkeypatch.setattr(
        __import__("training.research_data", fromlist=["input_identity"]),
        "input_identity",
        lambda snapshot: snapshot["input"],
    )
    return module.audit_selfplay_corpus(
        folder, protocol, protected, screen, screen_sha256=screen_sha256
    )


def test_changed_source_manifest_during_enumeration_cannot_gain_a_fresh_hash(
    tmp_path, monkeypatch
):
    with pytest.raises(ValueError, match="changed"):
        enumerate_fixture(tmp_path, monkeypatch, tamper=True)
