"""Real Parquet/Rust and cross-owner continuation, exclusively on Linux."""

import sys
from copy import deepcopy

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="external Linux only")

OLD = {"provider": "vast.ai", "instance_id": 101, "tag": "voxelshogi-phase5-test-old"}
NEW = {"provider": "vast.ai", "instance_id": 102, "tag": "voxelshogi-phase5-test-new"}
RELEASE = {
    "owner": OLD,
    "destruction_acknowledged": True,
    "inventory_absent": True,
    "evidence_sha256": "e" * 64,
}


def partial(tmp_path):
    import json

    from training.checkpoint import atomic_json
    from training.evaluation_jobs import plan_case_jobs, run_case_assignment
    from training.feature_cache import file_hash
    from training.tests.test_evaluation_v2_native import native_protocol

    spec = native_protocol()
    plan = plan_case_jobs({"control": spec}, max_workers=2)
    folder = tmp_path / "pool"
    folder.mkdir()
    for name in ("jobs", "launches", "protocols", "logs", "cohorts"):
        (folder / name).mkdir()
    atomic_json(folder / "plan.json", plan)
    atomic_json(folder / "artifacts.json", {"control": {}})
    atomic_json(folder / "protocols/control.json", spec)
    job = plan["jobs"][1]
    target = folder / "jobs" / job["job_id"]
    first = target / (job["case_id"] + "-b.json")
    with pytest.raises(InterruptedError):
        run_case_assignment(
            spec, {}, target, case_id=job["case_id"], stop_requested=first.exists
        )
    # Independent whitespace makes rerunning/re-encoding this color detectable
    # without relying on a new measured elapsed time being different.
    first.write_text(json.dumps(json.loads(first.read_text()), indent=2) + "\n")
    saved = json.loads((target / "job.json").read_text())
    saved["files"][0].update(bytes=first.stat().st_size, sha256=file_hash(first))
    atomic_json(target / "job.json", saved)
    return folder, plan, first


def test_real_partial_parquet_restore_finishes_only_missing_colors(tmp_path):
    from training.evaluation_jobs import run_case_plan
    from training.evaluation_pool_archive import (
        pack_pool,
        read_pool_archive,
        restore_pool,
    )
    from training.feature_cache import file_hash
    from training.hub_release import plan_release

    source, plan, first = partial(tmp_path)
    original, raw = file_hash(first), first.read_bytes()
    archive = tmp_path / "archive"
    packed = pack_pool(source, archive, expected_plan=plan, owner=OLD)
    assert packed["games"] == 1 and packed["target_games"] == 4
    assert packed["source_commit"] == plan["jobs"][0]["protocol"]["source_commit"]
    assert (
        packed["pipeline_complete"] is False
        and packed["rust_replayed_all_committed_games"]
    )
    checked, members = read_pool_archive(archive, expected_plan=plan)
    assert checked == packed
    key = first.relative_to(source).as_posix()
    assert members[key] == raw
    (archive / "LICENSE").write_text("CC-BY-4.0 test data; not a live publication.\n")
    (archive / "README.md").write_text(
        "---\nlicense: cc-by-4.0\n---\n# Test archive\n\n"
        "## Generation and provenance\nOne committed color of four planned fixture games; not a complete experiment.\n\n"
        "## Usage and schema\npool.parquet contains path:string and data:binary, preserving original JSON bytes.\n\n"
        "## Verification\nActual Rust replay and Parquet byte roundtrip; no corpus leakage claim.\n\n"
        "## Access and license\nCC-BY-4.0 fixture; public/manual, Community OFF only if actually published.\n"
    )
    publication = plan_release(
        archive,
        repo_id="voxelshogi/voxelshogi-generation-evaluation-resume-v1",
        repo_type="dataset",
        license_id="cc-by-4.0",
        license_approved=True,
        source_commit=plan["jobs"][0]["protocol"]["source_commit"],
    )
    assert "pool.parquet" in {entry["path"] for entry in publication["files"]}
    destination = tmp_path / "restored"
    result = restore_pool(
        archive,
        destination,
        expected_plan=plan,
        artifacts={"control": {}},
        parent_release=RELEASE,
        current_owner=NEW,
    )
    assert result["games_restored"] == 1 and result["target_games"] == 4
    assert list((destination / "launches").iterdir()) == []
    restored_first = destination / key
    assert restored_first.read_bytes() == raw
    completed = run_case_plan(plan, {"control": {}}, destination, resume=True)
    assert [
        completed["control"]["overall"][k]
        for k in ("games", "wins", "losses", "draws", "cutoffs")
    ] == [4, 1, 1, 0, 2]
    assert file_hash(restored_first) == original
    assert run_case_plan(plan, {"control": {}}, destination, resume=True) == completed


@pytest.mark.parametrize(
    "change", ["parquet-hash", "member-path", "duplicate", "coverage", "expected-plan"]
)
def test_tampered_archive_cannot_be_restored_as_a_valid_prefix(tmp_path, change):
    import pyarrow as pa
    import pyarrow.parquet as pq

    from training.checkpoint import atomic_json
    from training.evaluation_pool_archive import pack_pool, read_pool_archive
    from training.feature_cache import file_hash

    source, plan, _ = partial(tmp_path)
    archive = tmp_path / "archive"
    manifest = pack_pool(source, archive, expected_plan=plan, owner=OLD)
    data = archive / "pool.parquet"
    if change == "parquet-hash":
        data.write_bytes(data.read_bytes() + b"changed")
    elif change in ("member-path", "duplicate"):
        rows = pq.read_table(data).to_pylist()
        if change == "member-path":
            rows[0]["path"] = "../escape.json"
        else:
            rows.append(dict(rows[0]))
        pq.write_table(pa.Table.from_pylist(rows), data)
        manifest["files"][0].update(bytes=data.stat().st_size, sha256=file_hash(data))
    elif change == "coverage":
        manifest["games"] = 4
    else:
        plan = deepcopy(plan)
        plan["max_workers"] = 3
    atomic_json(archive / "manifest.json", manifest)
    with pytest.raises(ValueError):
        read_pool_archive(archive, expected_plan=plan)
    assert not (tmp_path / "escape.json").exists()


@pytest.mark.parametrize(
    "change", ["ack", "absent", "owner", "same-instance", "runtime"]
)
def test_release_and_current_runtime_are_checked_before_resuming(
    tmp_path, change, monkeypatch
):
    from training import evaluation_pool_archive as archive

    source, plan, _ = partial(tmp_path)
    folder = tmp_path / "archive"
    archive.pack_pool(source, folder, expected_plan=plan, owner=OLD)
    release, current = deepcopy(RELEASE), dict(NEW)
    if change == "ack":
        release["destruction_acknowledged"] = False
    elif change == "absent":
        release["inventory_absent"] = False
    elif change == "owner":
        release["owner"] = NEW
    elif change == "same-instance":
        current = OLD
    else:
        monkeypatch.setattr(
            archive, "execution_runtime", lambda *_: {"different": True}
        )
    destination = tmp_path / "restored"
    with pytest.raises(ValueError):
        archive.restore_pool(
            folder,
            destination,
            expected_plan=plan,
            artifacts={"control": {}},
            parent_release=release,
            current_owner=current,
        )
    assert not destination.exists()


def test_snapshot_refuses_a_running_pool_lease(tmp_path):
    from training.evaluation_jobs import _lease
    from training.evaluation_pool_archive import pack_pool

    source, plan, _ = partial(tmp_path)
    with _lease(source), pytest.raises(ValueError, match="running owner"):
        pack_pool(source, tmp_path / "archive", expected_plan=plan, owner=OLD)


def test_snapshot_also_refuses_a_case_lease_without_a_coordinator(tmp_path):
    from training.evaluation_jobs import _lease
    from training.evaluation_pool_archive import pack_pool

    source, plan, _ = partial(tmp_path)
    active = source / "jobs" / plan["jobs"][1]["job_id"]
    with _lease(active), pytest.raises(ValueError, match="running owner"):
        pack_pool(source, tmp_path / "archive", expected_plan=plan, owner=OLD)
    assert not (tmp_path / "archive").exists()
