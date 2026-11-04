"""Stopped-pool metadata and byte preservation; fake replay ports only."""

import json
from copy import deepcopy

import pytest

from training.evaluation_jobs import plan_case_jobs
from training.tests.test_evaluation_jobs import case_folder
from training.tests.test_evaluation_v2 import protocol


def pool(folder):
    folder.mkdir()
    for name in ("jobs", "protocols", "launches", "logs", "cohorts"):
        (folder / name).mkdir()
    plan = plan_case_jobs({"m6": protocol()}, max_workers=2)
    (folder / "plan.json").write_text(json.dumps(plan))
    (folder / "artifacts.json").write_text(
        json.dumps({"m6": {"model": "/remote/model.safetensors"}})
    )
    (folder / "protocols/m6.json").write_text(json.dumps(protocol()))
    case_folder(folder / "jobs/m6--ending", complete=False)
    (folder / "launches/m6--ending.json").write_text(
        json.dumps({"state": "terminal", "exit_code": 1})
    )
    return plan


def test_stopped_snapshot_keeps_nonprefix_case_first_color_bytes_and_full_target(
    tmp_path,
):
    from training.evaluation_pool_archive import collect_pool

    folder = tmp_path / "pool"
    plan = pool(folder)
    calls = []
    result = collect_pool(
        folder,
        plan,
        replay=lambda row, case: calls.append((row["case_id"], case["id"])),
    )
    assert calls == [("ending", "ending")]
    assert result["games"] == 1 and result["target_games"] == 4
    assert result["jobs_present"] == ["m6--ending"]
    assert result["games_by_cohort"] == {"m6": 1}
    assert result["completed_jobs"] == 0
    assert result["runtime_by_cohort"] == {"m6": {"source_commit": "d" * 40}}
    assert set(result["files"]) == {
        "plan.json",
        "artifacts.json",
        "protocols/m6.json",
        "jobs/m6--ending/protocol.json",
        "jobs/m6--ending/job.json",
        "jobs/m6--ending/ending-b.json",
    }
    for name, data in result["files"].items():
        assert data == (folder / name).read_bytes()
    assert result["launch_observations"]["m6--ending"]["state"] == "terminal"


@pytest.mark.parametrize(
    "change",
    ["plan", "protocol", "foreign-job", "hash", "unknown-launch", "live-launch"],
)
def test_snapshot_refuses_changed_or_uncertain_pool_before_publishing(tmp_path, change):
    from training.evaluation_pool_archive import collect_pool

    folder = tmp_path / "pool"
    plan = pool(folder)
    if change == "plan":
        value = deepcopy(plan)
        value["max_workers"] = 3
        (folder / "plan.json").write_text(json.dumps(value))
    elif change == "protocol":
        (folder / "protocols/m6.json").write_text("{}")
    elif change == "foreign-job":
        (folder / "jobs/alien").mkdir()
    elif change == "hash":
        (folder / "jobs/m6--ending/ending-b.json").write_text("{}")
    elif change == "unknown-launch":
        (folder / "launches/m6--ending.json").write_text('{"state":"requested"}')
    else:
        (folder / "launches/m6--ending.json").write_text(
            '{"state":"running","pid":123,"create_time":456.0}'
        )
    with pytest.raises(ValueError):
        collect_pool(folder, plan, replay=lambda *_: None, is_live=lambda _: True)


def test_fake_replay_failure_is_not_accepted_as_a_saved_game(tmp_path):
    from training.evaluation_pool_archive import collect_pool

    folder = tmp_path / "pool"
    plan = pool(folder)

    def invalid(*_):
        raise ValueError("independent replay disagrees")

    with pytest.raises(ValueError, match="replay"):
        collect_pool(folder, plan, replay=invalid)


def test_empty_committed_pool_is_not_a_successful_dataset(tmp_path):
    from training.evaluation_pool_archive import collect_pool

    folder = tmp_path / "pool"
    plan = pool(folder)
    import shutil

    shutil.rmtree(folder / "jobs/m6--ending")
    with pytest.raises(ValueError, match="empty"):
        collect_pool(folder, plan, replay=lambda *_: None)


def test_two_saved_cases_must_keep_the_same_cohort_runtime(tmp_path):
    from training.evaluation_pool_archive import collect_pool

    folder = tmp_path / "pool"
    plan = pool(folder)
    _, saved, _ = case_folder(folder / "jobs/m6--tactic", case_index=0)
    saved["runtime"]["python"] = "changed"
    (folder / "jobs/m6--tactic/job.json").write_text(json.dumps(saved))
    with pytest.raises(ValueError, match="runtime"):
        collect_pool(folder, plan, replay=lambda *_: None)


def test_actual_parquet_packing_and_restore_are_linux_only(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from training import evaluation_pool_archive as archive

    monkeypatch.setattr(archive, "sys", SimpleNamespace(platform="darwin"))
    with pytest.raises(ValueError, match="Linux"):
        archive.pack_pool(tmp_path, tmp_path / "archive", expected_plan={}, owner={})
    with pytest.raises(ValueError, match="Linux"):
        archive.restore_pool(
            tmp_path,
            tmp_path / "restored",
            expected_plan={},
            artifacts={},
            parent_release={},
            current_owner={},
        )


def test_dangling_known_job_is_not_silently_treated_as_unstarted(tmp_path):
    from training.evaluation_pool_archive import collect_pool

    folder = tmp_path / "pool"
    plan = pool(folder)
    (folder / "jobs/m6--tactic").symlink_to(tmp_path / "missing")
    with pytest.raises(ValueError):
        collect_pool(folder, plan, replay=lambda *_: None)


def test_metadata_cannot_change_between_validation_and_snapshot_bytes(tmp_path):
    from training.evaluation_pool_archive import collect_pool

    folder = tmp_path / "pool"
    plan = pool(folder)

    def changed(*_):
        (folder / "jobs/m6--ending/job.json").write_text("{}")

    with pytest.raises(ValueError, match="changed"):
        collect_pool(folder, plan, replay=changed)


def restoration_ports(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from training import evaluation_pool_archive as archive

    source = tmp_path / "source"
    plan = pool(source)
    snapshot = archive.collect_pool(source, plan, replay=lambda *_: None)
    old = {"provider": "vast.ai", "instance_id": 101, "tag": "voxelshogi-phase5-old"}
    current = {
        "provider": "vast.ai",
        "instance_id": 102,
        "tag": "voxelshogi-phase5-new",
    }
    release = {
        "owner": old,
        "destruction_acknowledged": True,
        "inventory_absent": True,
        "evidence_sha256": "e" * 64,
    }
    files = snapshot.pop("files")
    manifest = {**snapshot, "owner": old}
    folder = tmp_path / "archive"
    folder.mkdir()
    (folder / "manifest.json").write_text(json.dumps(manifest))
    calls = []
    monkeypatch.setattr(archive, "sys", SimpleNamespace(platform="linux"))

    def read(path, *, expected_plan):
        assert path == folder and expected_plan == plan
        calls.append("read")
        return manifest, files

    def checked(spec, artifacts):
        calls.append(("artifacts", artifacts))
        return None, {"model"}, spec["source_commit"]

    monkeypatch.setattr(archive, "read_pool_archive", read)
    monkeypatch.setattr(archive, "checked_execution", checked)
    monkeypatch.setattr(
        archive, "execution_runtime", lambda *_: {"source_commit": "d" * 40}
    )
    return archive, folder, plan, release, current, calls, files


def test_metadata_restore_preserves_bytes_changes_only_artifact_location_and_keeps_old_pids_historical(
    tmp_path, monkeypatch
):
    archive, folder, plan, release, current, calls, files = restoration_ports(
        tmp_path, monkeypatch
    )
    output = tmp_path / "restored"
    artifacts = {"m6": {"model": "/different/model.safetensors"}}
    result = archive.restore_pool(
        folder,
        output,
        expected_plan=plan,
        artifacts=artifacts,
        parent_release=release,
        current_owner=current,
    )
    assert calls == ["read", ("artifacts", artifacts["m6"])]
    assert result["games_restored"] == 1 and result["target_games"] == 4
    assert result["parent_launch_observations"]["m6--ending"]["state"] == "terminal"
    assert list((output / "launches").iterdir()) == []
    assert json.loads((output / "artifacts.json").read_text()) == artifacts
    for name, raw in files.items():
        if name != "artifacts.json":
            assert (output / name).read_bytes() == raw
    assert (
        result["parent_owner"] == release["owner"]
        and result["current_owner"] == current
    )


@pytest.mark.parametrize(
    "change", ["ack", "absent", "owner", "same-instance", "runtime", "proof-hash"]
)
def test_restore_refuses_missing_release_proof_or_current_runtime(
    tmp_path, monkeypatch, change
):
    archive, folder, plan, release, current, calls, _ = restoration_ports(
        tmp_path, monkeypatch
    )
    if change == "ack":
        release["destruction_acknowledged"] = False
    elif change == "absent":
        release["inventory_absent"] = False
    elif change == "owner":
        release["owner"] = current
    elif change == "same-instance":
        current = release["owner"]
    elif change == "proof-hash":
        release["evidence_sha256"] = "not-a-hash"
    else:
        monkeypatch.setattr(
            archive, "execution_runtime", lambda *_: {"source_commit": "changed"}
        )
    output = tmp_path / "restored"
    with pytest.raises(ValueError):
        archive.restore_pool(
            folder,
            output,
            expected_plan=plan,
            artifacts={"m6": {"model": "/different/model.safetensors"}},
            parent_release=release,
            current_owner=current,
        )
    assert not output.exists()
    if change != "runtime":
        assert not calls
