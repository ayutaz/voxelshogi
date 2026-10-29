"""Linux CI only in this workflow: real Rust boundary and Parquet plumbing.

The corpus fixture is deliberately opaque metadata, not evidence of game legality.
Actual production legality comes from M4 replay and immutable release hashes.
"""

import hashlib
import json

import pytest


@pytest.mark.parametrize("side", ["b", "w"])
def test_real_rust_teacher_uses_the_same_canonical_label(side):
    from voxelshogi import Game

    from training.supervision import select_target
    from training.tests.test_engine import corner_position
    from training.tests.test_supervision import row

    game = Game(corner_position(side))
    snapshot = game.snapshot()
    example = row(side=side)
    example.update(
        {key: snapshot[key] for key in ("vsfen", "side", "finished", "evaluation")}
    )
    example.update(
        initial=game.record()["initial"],
        history=game.record()["moves"],
        legal_moves=sorted(game.legal_actions().values()),
        legal_actions=sorted(game.legal_actions()),
        teacher=json.dumps(game.search(max_depth=1, max_nodes=1000)),
    )
    example["played_move"] = example["legal_moves"][0]
    target = select_target(example)
    destinations = {
        z * 81 + y * 9 + x for z in (7, 8) for y in (7, 8) for x in (7, 8)
    } - {728}
    assert target.action in {2 * (728 * 729 + to) for to in destinations}
    assert target.value == 0 and target.completed_depth == 1  # Two kings: material 0.


def test_audit_reads_only_hash_verified_parquet_and_preserves_fixed_contract(
    tmp_path, monkeypatch
):
    import pyarrow as pa
    import pyarrow.parquet as pq

    from training import supervision
    from training.data import SCHEMA
    from training.tests.test_supervision import row

    folder = tmp_path / "data"
    folder.mkdir()
    examples = [row(), row("g000044", "val"), row("g000050", "test")]
    shards = []
    for i, example in enumerate(examples):
        example["in_check"] = False
        path = folder / f"game-{i:06d}.parquet"
        pq.write_table(pa.Table.from_pylist([example], schema=SCHEMA), path)
        shards.append(
            {
                "file": path.name,
                "rows": 1,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    config = {"games": 3, "max_plies": 64}
    manifest = {
        "schema": "voxelshogi-dataset-v1",
        "ruleset_id": "voxelshogi-standard-v1",
        "config": config,
        "complete": True,
        "shards": shards,
    }
    for name, value in (
        ("manifest.json", manifest),
        ("generation.json", {}),
        ("validation.json", {}),
    ):
        (folder / name).write_text(json.dumps(value))
    plan = {
        "repo_id": "voxelshogi/voxelshogi-synthetic-v1",
        "repo_type": "dataset",
        "private": False,
        "gated": "manual",
        "files": [
            {
                "path": "production-64/" + p.name,
                "bytes": p.stat().st_size,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            }
            for p in sorted(folder.iterdir())
        ],
    }
    proof = {
        "production_job": {"config": config},
        "production_report": {"validation": {"rows": 3, "eligible_teachers": 3}},
        "publication": {
            "complete": True,
            "plan": plan,
            "receipt": {
                "hub_commit": "6e7fb29d2469b56a895042fbb089d86e7b4d074f",
                "verified": True,
                "release_sha256": hashlib.sha256(
                    json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
            },
        },
    }
    root = tmp_path / "repo"
    document = root / "docs/experiments/m4-production-release-2026-10-29.json"
    document.parent.mkdir(parents=True)
    document.write_text(json.dumps(proof))
    monkeypatch.setattr(supervision, "ROOT", root)
    result = supervision.audit_corpus(folder)
    assert result["counts"]["eligible_teachers"] == 3
    assert result["counts"]["teacher_splits"] == {"train": 1, "val": 1, "test": 1}
    assert result["contract"]["value_scale"] == 1000
    proof["publication"]["plan"]["private"] = True
    document.write_text(json.dumps(proof))
    with pytest.raises(ValueError, match="receipt"):
        supervision.audit_corpus(folder)
    proof["publication"]["plan"]["private"] = False
    document.write_text(json.dumps(proof))
    (folder / "game-000000.parquet").write_bytes(b"changed")
    with pytest.raises(ValueError, match="size"):
        supervision.audit_corpus(folder)
