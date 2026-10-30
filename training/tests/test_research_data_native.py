"""Small actual Rust/Parquet integration, executed only on Linux CI."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="external Linux only")


def protocol():
    from training.research_data import pilot_protocol

    root = Path(__file__).resolve().parents[2]
    sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    p = pilot_protocol(sha)
    p.update(opening_plies=1, max_plies=2, sample_plies=[1])
    p["games"] = p["games"][:3]
    for game, split in zip(p["games"], ["train", "val", "test"], strict=True):
        game["split"] = split
    p["trajectory"] = {"max_depth": 1, "max_nodes": 1, "table_capacity": 0}
    for teacher in p["teachers"].values():
        teacher.update(max_depth=1, minimum_depth=1, max_nodes=1, table_capacity=0)
    return p


def test_native_pilot_resume_and_regeneration_have_identical_parquet(tmp_path):
    from training.research_data_runner import generate_pilot, verify_pilot

    p = protocol()
    first, second = tmp_path / "first", tmp_path / "second"
    partial = generate_pilot(first, p, max_games=1)
    assert partial["complete"] is False
    assert len(partial["games"]) == 1
    generate_pilot(first, p)
    generate_pilot(second, p)
    assert (first / "manifest.json").read_bytes() == (
        second / "manifest.json"
    ).read_bytes()
    report = verify_pilot(first)
    assert report["complete"] and report["games"] == 3 and report["rows"] == 3
    for descriptor in report["files"]:
        a, b = first / descriptor["path"], second / descriptor["path"]
        assert a.read_bytes() == b.read_bytes()
        assert hashlib.sha256(a.read_bytes()).hexdigest() == descriptor["sha256"]
    # A valid node-limited result at depth0 must have no teacher target.
    assert report["teacher_depths"] == {"deep": {"0": 3}, "shallow": {"0": 3}}


def test_native_pilot_rejects_corruption_even_if_inventory_hash_is_rewritten(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    from training.research_data_runner import generate_pilot, verify_pilot

    p = protocol()
    out = tmp_path / "out"
    generate_pilot(out, p)
    manifest = json.loads((out / "manifest.json").read_text())
    shard = manifest["games"][0]["file"]
    path = out / shard["path"]
    table = pq.read_table(path)
    rows = table.to_pylist()
    rows[0]["input_id"] = "f" * 64
    pq.write_table(pa.Table.from_pylist(rows, schema=table.schema), path)
    with pytest.raises(ValueError, match="file"):
        verify_pilot(out)
    shard.update(
        bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest()
    )
    (out / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="replay"):
        verify_pilot(out)


def test_native_interruption_keeps_only_committed_games_and_changed_seed_cannot_resume(
    tmp_path,
):
    from copy import deepcopy

    from training.research_data_runner import generate_pilot

    p, out = protocol(), tmp_path / "out"
    generate_pilot(out, p, max_games=1)
    before = (out / "manifest.json").read_bytes()
    with pytest.raises(InterruptedError):
        generate_pilot(out, p, stop_requested=lambda: True)
    assert (out / "manifest.json").read_bytes() == before
    assert not (out / "game-000001.parquet").exists()
    changed = deepcopy(p)
    changed["games"][0]["seed"] += 100
    with pytest.raises(ValueError, match="protocol"):
        generate_pilot(out, changed)


def test_canonical_integer_ids_agree_with_actual_tensor_equivalence():
    import numpy as np
    from voxelshogi import Game

    from training.evaluation_cases import handmade_cases
    from training.research_data import input_identity

    black = Game.from_record(handmade_cases()[0]["case"]["opening"])
    white = Game.from_record(handmade_cases()[1]["case"]["opening"])
    assert np.array_equal(black.features(), white.features())
    assert input_identity(black.snapshot()) == input_identity(white.snapshot())
    black.play("232222")
    assert input_identity(black.snapshot()) != input_identity(white.snapshot())
