"""Small complete datasets; corruption checks do not trust regenerated hashes."""

import hashlib
import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from training.tests.test_engine import corner_position


def config(**kwargs):
    from training.data import GenerationConfig

    return GenerationConfig(
        engine_commit="a" * 40,
        seed=17,
        games=3,
        max_plies=2,
        initial=corner_position(),
        max_depth=1,
        max_nodes=100,
        **kwargs,
    )


def files(directory):
    return {
        p.name: p.read_bytes()
        for p in directory.iterdir()
        if not p.name.endswith(".tmp")
    }


def test_three_sources_rule_facts_and_reproducible_parquet(tmp_path):
    from training.data import generate_dataset, validate_dataset

    a, b = tmp_path / "a", tmp_path / "b"
    generate_dataset(a, config())
    generate_dataset(b, config())
    assert files(a) == files(b)
    report = validate_dataset(a)
    assert report["games"] == 3 and report["rows"] == 9
    assert report["sources"] == {"random": 3, "rules": 3, "search": 3}
    assert report["duplicates"] >= 2  # Shared initial position retained but excluded.
    # SHA-256 split buckets for seed 17: a7d80244->8, 043fbc14->0, fef1eceb->1.
    assert [
        pq.read_table(a / f"game-{i:06d}.parquet")["split"][0].as_py() for i in range(3)
    ] == ["val", "train", "train"]
    rows = [
        r for p in sorted(a.glob("*.parquet")) for r in pq.read_table(p).to_pylist()
    ]
    for row in rows:
        assert row["ruleset_id"] == "voxelshogi-standard-v1"
        assert row["in_check"] is False and row["result"] is None
        assert row["side"] == ("b" if row["ply"] % 2 == 0 else "w")
        if row["ply"] == 0:
            assert len(row["legal_actions"]) == 7
        if row["source"] == "search" and row["played_move"] is not None:
            teacher = json.loads(row["teacher"])
            assert row["teacher_valid"] and teacher["completed_depth"] == 1
            assert teacher["score"] == 0 and teacher["nodes"] == 8
            assert row["played_move"] == teacher["best_move"]
        else:
            assert row["teacher"] is None and not row["teacher_valid"]


def test_pause_resume_matches_continuous_and_rejects_changed_config(tmp_path):
    from dataclasses import replace

    from training.data import generate_dataset, validate_dataset

    resumed, fresh = tmp_path / "resumed", tmp_path / "fresh"
    paused = generate_dataset(resumed, config(), max_games=1)
    assert not paused["complete"] and len(paused["shards"]) == 1
    with pytest.raises(ValueError, match="incomplete"):
        validate_dataset(resumed)
    with pytest.raises(ValueError, match="config"):
        generate_dataset(resumed, replace(config(), seed=18))
    generate_dataset(resumed, config())
    generate_dataset(fresh, config())
    assert files(resumed) == files(fresh)
    assert validate_dataset(resumed)["games"] == 3


def test_crash_between_shard_and_manifest_never_exposes_partial_game(
    tmp_path, monkeypatch
):
    import training.data as data

    original = data._write_manifest
    out, fresh = tmp_path / "crash", tmp_path / "fresh"

    def crash(path, manifest):
        if len(manifest["shards"]) == 1:
            raise RuntimeError("injected crash")
        original(path, manifest)

    monkeypatch.setattr(data, "_write_manifest", crash)
    with pytest.raises(RuntimeError, match="injected crash"):
        data.generate_dataset(out, config())
    assert json.loads((out / "manifest.json").read_text())["shards"] == []
    monkeypatch.setattr(data, "_write_manifest", original)
    data.generate_dataset(out, config())
    data.generate_dataset(fresh, config())
    assert files(out) == files(fresh)


def test_interruption_during_initial_manifest_can_resume(tmp_path, monkeypatch):
    import training.data as data

    atomic = data._atomic_bytes
    out, fresh = tmp_path / "interrupted-init", tmp_path / "fresh"

    def interrupt(path, content):
        path.with_name(path.name + ".tmp").write_bytes(content[:12])
        raise RuntimeError("interrupted initial write")

    monkeypatch.setattr(data, "_atomic_bytes", interrupt)
    with pytest.raises(RuntimeError):
        data.generate_dataset(out, config())
    monkeypatch.setattr(data, "_atomic_bytes", atomic)
    data.generate_dataset(out, config())
    data.generate_dataset(fresh, config())
    assert files(out) == files(fresh)


def rewrite_first(directory, change):
    """Rehash edited data so the validator must inspect semantic content."""
    path = directory / "game-000000.parquet"
    table = pq.read_table(path)
    rows = table.to_pylist()
    change(rows)
    pq.write_table(pa.Table.from_pylist(rows, schema=table.schema), path)
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["shards"][0]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))


@pytest.mark.parametrize(
    "field,value",
    [
        ("played_move", "555554"),
        ("hash", "0" * 16),
        ("side", "w"),
        ("in_check", True),
        ("legal_actions", []),
        ("split", "test"),
        ("history", ["555554"]),
        ("duplicate_of", "made-up"),
        ("teacher_valid", True),
        ("source", "search"),
    ],
)
def test_validator_rejects_semantic_corruption_even_after_rehash(
    tmp_path, field, value
):
    from training.data import generate_dataset, validate_dataset

    generate_dataset(tmp_path, config())
    rewrite_first(tmp_path, lambda rows: rows[0].__setitem__(field, value))
    with pytest.raises(ValueError):
        validate_dataset(tmp_path)


def test_manifest_checksum_missing_shards_and_path_traversal_are_rejected(tmp_path):
    from training.data import generate_dataset, validate_dataset

    generate_dataset(tmp_path, config())
    mpath = tmp_path / "manifest.json"
    original = mpath.read_text()
    m = json.loads(original)
    m["shards"][0]["file"] = "../escaped.parquet"
    mpath.write_text(json.dumps(m))
    with pytest.raises(ValueError):
        validate_dataset(tmp_path)
    mpath.write_text(original)
    m = json.loads(original)
    m["shards"][0]["sha256"] = "0" * 64
    mpath.write_text(json.dumps(m))
    with pytest.raises(ValueError, match="hash"):
        validate_dataset(tmp_path)
    mpath.write_text(original)
    p = tmp_path / "game-000000.parquet"
    p.write_bytes(p.read_bytes() + b"corrupt")
    with pytest.raises(ValueError, match="hash"):
        validate_dataset(tmp_path)


def test_no_completed_iteration_is_not_a_teacher_label(tmp_path):
    from dataclasses import replace

    from training.data import generate_dataset, validate_dataset

    c = replace(config(), games=1, sources=("search",), max_nodes=1)
    generate_dataset(tmp_path, c)
    assert validate_dataset(tmp_path)["rows"] == 3
    rows = pq.read_table(tmp_path / "game-000000.parquet").to_pylist()
    assert rows[0]["played_move"] in rows[0]["legal_moves"]
    assert json.loads(rows[0]["teacher"])["score"] is None
    assert not rows[0]["teacher_valid"]


def test_validator_rechecks_teacher_score_and_config(tmp_path):
    from dataclasses import replace

    from training.data import generate_dataset, validate_dataset

    generate_dataset(tmp_path, replace(config(), games=1, sources=("search",)))

    def corrupt(rows):
        teacher = json.loads(rows[0]["teacher"])
        teacher["score"] = 12345
        rows[0]["teacher"] = json.dumps(teacher)

    rewrite_first(tmp_path, corrupt)
    with pytest.raises(ValueError, match="teacher"):
        validate_dataset(tmp_path)


def test_natural_terminal_row_is_preserved(tmp_path):
    from dataclasses import replace
    from pathlib import Path

    from training.data import generate_dataset, validate_dataset

    fixture = json.loads(Path("export/fixtures/positions.json").read_text())[2]
    c = replace(
        config(),
        initial=fixture["record"]["initial"],
        games=1,
        sources=("search",),
        max_nodes=10000,
    )
    generate_dataset(tmp_path, c)
    assert validate_dataset(tmp_path)["rows"] == 2
    last = pq.read_table(tmp_path / "game-000000.parquet").to_pylist()[-1]
    assert last["finished"] and last["legal_actions"] == []
    assert last["in_check"]
    assert json.loads(last["result"])["Win"]["reason"] == "Checkmate"
    assert last["termination"] == "natural" and last["played_move"] is None


def test_refuse_unowned_directory_and_empty_or_invalid_configuration(tmp_path):
    from dataclasses import replace

    from training.data import generate_dataset

    (tmp_path / "keep.txt").write_text("unrelated")
    with pytest.raises(ValueError, match="unowned"):
        generate_dataset(tmp_path, config())
    assert (tmp_path / "keep.txt").read_text() == "unrelated"
    for changes in (
        {"games": 0},
        {"sources": ()},
        {"max_nodes": -1},
        {"seed": True},
        {"engine_commit": "invalid"},
    ):
        with pytest.raises(ValueError):
            replace(config(), **changes)
