"""Release assembly uses small byte fixtures, never real search on Mac."""

import hashlib
import json
from pathlib import Path

import pytest


def put(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n")


def completed(tmp_path):
    from training.production_release import production_job

    job = production_job("a" * 40, hourly_usd=1)
    job["config"]["games"] = 3  # Three tiny files exercise assembly, not generation.
    output = tmp_path / "output"
    first = output / "first"
    first.mkdir(parents=True)
    shards = []
    for i in range(3):
        file = first / f"game-{i:06d}.parquet"
        file.write_bytes(b"abc")
        shards.append(
            {
                "file": file.name,
                "sha256": hashlib.sha256(b"abc").hexdigest(),
                "rows": 33334,
            }
        )
    manifest = {
        "schema": "voxelshogi-dataset-v1",
        "complete": True,
        "config": job["config"],
        "shards": shards,
        "ruleset_id": "voxelshogi-standard-v1",
    }
    put(first / "manifest.json", manifest)
    (first / ".voxelshogi-dataset-v1").touch()
    validation = {
        "games": 3,
        "rows": 100002,
        "duplicates": 1,
        "eligible_rows": 100001,
        "eligible_teachers": 33333,
        "eligible_sources": {"random": 33334, "rules": 33334, "search": 33333},
        "eligible_splits": {"train": 33334, "val": 33334, "test": 33333},
    }
    report = {
        "complete": True,
        "regenerated_bytes_match": True,
        "source_commit": "a" * 40,
        "context": {"source_commit": "a" * 40},
        "validation": validation,
        "supervisor": {"reason": "completed"},
        "files": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in first.iterdir()
        },
    }
    put(output / "job.json", job)
    put(output / "report.json", report)
    return output, report


def test_job_fixes_the_approved_generation_and_budget():
    from training.production_release import production_job

    job = production_job("a" * 40, hourly_usd=1)
    assert job["approved_seconds"] == 38700 and job["max_cost_usd"] == 12
    assert job["minimum_eligible_rows"] == 100000 and job["workers"] == 4
    assert job["config"]["games"] == 1800 and job["config"]["max_plies"] == 64
    assert (
        job["config"]["search_opening_plies"] == 16 and job["config"]["max_depth"] == 2
    )
    for rate in (1.01, 0, float("nan")):
        with pytest.raises(ValueError):
            production_job("a" * 40, hourly_usd=rate)


def test_smaller_cpu_job_keeps_data_quality_and_leaves_transfer_time():
    from training.production_release import production_job

    job = production_job("a" * 40, hourly_usd=1, sku="rtx59-3-24-750-xam.1")
    assert job["approved_seconds"] == 81900 and job["max_cost_usd"] == 24
    assert job["minimum_eligible_rows"] == 100000
    assert job["config"]["games"] == 1800 and job["workers"] == 4
    with pytest.raises(ValueError):
        production_job("a" * 40, hourly_usd=1, sku="unquoted")


@pytest.mark.parametrize(
    "change",
    [
        {"complete": False},
        {"regenerated_bytes_match": False},
        {"source_commit": "b" * 40},
        {"validation": {"eligible_rows": 99999}},
        {"supervisor": {"reason": "memory"}},
    ],
)
def test_incomplete_wrong_source_or_insufficient_data_cannot_be_published(
    tmp_path, change
):
    from training.production_release import validate_completed

    output, report = completed(tmp_path)
    if "validation" in change:
        change = {"validation": {**report["validation"], **change["validation"]}}
    put(output / "report.json", {**report, **change})
    with pytest.raises(ValueError):
        validate_completed(output)


def test_changed_bytes_and_unlisted_files_are_not_approved_artifacts(tmp_path):
    from training.production_release import validate_completed

    output, _ = completed(tmp_path)
    assert validate_completed(output)[1]["validation"]["eligible_rows"] == 100001
    first = output / "first"
    (first / "game-000000.parquet").write_bytes(b"abd")
    with pytest.raises(ValueError):
        validate_completed(output)
    (first / "game-000000.parquet").write_bytes(b"abc")
    (first / "worker.log").write_text("private log")
    with pytest.raises(ValueError):
        validate_completed(output)


def test_staging_preserves_pilots_and_card_reports_actual_counts_and_splits(tmp_path):
    from training.hub_release import plan_release
    from training.production_release import stage_release

    output, report = completed(tmp_path)
    previous = tmp_path / "previous"
    previous.mkdir()
    (previous / "LICENSE").write_text("CC-BY-4.0 license fixture\n")
    (previous / "README.md").write_text(
        "---\nlicense: cc-by-4.0\n---\n"
        + "\n".join(
            "## " + s + "\nPilot fixture."
            for s in (
                "Generation and provenance",
                "Usage and schema",
                "Verification",
                "Access and license",
            )
        )
    )
    pilot = previous / "pilot-16"
    pilot.mkdir()
    (pilot / "game-000000.parquet").write_bytes(b"old")
    put(
        pilot / "manifest.json",
        {
            "config": {"engine_commit": "b" * 40, "seed": 17},
            "shards": [{"file": "game-000000.parquet"}],
            "complete": True,
        },
    )
    put(pilot / "generation.json", {"config": {"engine_commit": "b" * 40, "seed": 17}})
    old = {
        "complete": True,
        "validation": {
            "games": 1,
            "rows": 2,
            "eligible_rows": 1,
            "eligible_teachers": 1,
        },
    }
    put(pilot / "validation.json", old)
    put(
        previous / "manifest.json",
        {"configurations": {"pilot-16": {"manifest": "pilot-16/manifest.json"}}},
    )
    put(previous / "validation.json", {"reports": {"pilot-16": old}})
    old_plan = plan_release(
        previous,
        repo_id="voxelshogi/voxelshogi-synthetic-v1",
        repo_type="dataset",
        license_id="cc-by-4.0",
        license_approved=True,
        source_commit="b" * 40,
    )
    target = tmp_path / "release"

    def split(path):
        return {
            "game-000000.parquet": "train",
            "game-000001.parquet": "val",
            "game-000002.parquet": "test",
        }[Path(path).name]

    plan = stage_release(output, previous, target, old_plan, split_for_file=split)
    assert (target / "pilot-16/game-000000.parquet").read_bytes() == b"old"
    assert (target / "production-64/game-000000.parquet").read_bytes() == b"abc"
    card = (target / "README.md").read_text()
    assert "| production-64 | 3 | 100002 | 1 | 100001 | 33333 |" in card
    assert 'nonduplicate sources {"random":33334,"rules":33334,"search":33333}' in card
    assert "100001" in card and "33333" in card and "config_name: production-64" in card
    assert (
        "split: validation" in card
        and "split: test" in card
        and "config_name: pilot-16" in card
    )
    assert all(not f["path"].startswith(".") for f in plan["files"])
    assert len(plan["files"]) == 14  # 4 root + 4 pilot + 6 production.


def test_raw_rows_cannot_replace_a_consistent_but_insufficient_eligible_count(tmp_path):
    from training.production_release import validate_completed

    output, report = completed(tmp_path)
    counts = report["validation"]
    counts.update(
        eligible_rows=99999,
        duplicates=3,
        eligible_teachers=33330,
        eligible_sources={"random": 33334, "rules": 33334, "search": 33331},
        eligible_splits={"train": 33334, "val": 33334, "test": 33331},
    )
    put(output / "report.json", report)
    with pytest.raises(ValueError, match="insufficient"):
        validate_completed(output)


def test_hub_parent_is_pinned_even_if_it_changes_during_preflight():
    from types import SimpleNamespace

    from training.production_release import PinnedParentApi

    class Hub:
        sha = "a" * 40

        def repo_info(self, **kwargs):
            return SimpleNamespace(sha=self.sha)

    hub = Hub()
    api = PinnedParentApi(hub, "a" * 40)
    assert api.repo_info(repo_id="voxelshogi/voxelshogi-synthetic-v1").sha == "a" * 40
    hub.sha = "b" * 40
    with pytest.raises(ValueError, match="parent"):
        api.repo_info(repo_id="voxelshogi/voxelshogi-synthetic-v1")


def test_preflight_confirms_gate_community_and_parent_before_generation():
    from training.production_release import preflight_repository
    from training.tests.test_hub_release import Hub

    plan = {
        "repo_id": "voxelshogi/voxelshogi-synthetic-v1",
        "repo_type": "dataset",
        "private": False,
        "gated": "manual",
        "license": "cc-by-4.0",
        "license_approved": True,
        "source_commit": "a" * 40,
    }
    api = Hub()
    assert preflight_repository(api, plan, "b" * 40)["community_disabled"] is True
    assert not any(name == "upload" for name, _ in api.calls)
    wrong = Hub()
    with pytest.raises(ValueError, match="parent"):
        preflight_repository(wrong, plan, "c" * 40)
    assert not any(name == "settings" for name, _ in wrong.calls)


def test_download_verification_pins_revision_and_fetches_every_approved_file(tmp_path):
    from types import SimpleNamespace

    from training.hub_release import publish_release
    from training.production_release import verify_downloaded
    from training.tests.test_hub_release import Hub, release

    source = tmp_path / "source"
    source.mkdir()
    plan = release(source)
    receipt = publish_release(source, plan, Hub(), execute=True, system="linux")

    class Uploaded(Hub):
        def repo_info(self, **kw):
            assert kw["revision"] == "c" * 40
            return SimpleNamespace(private=False, gated="manual", sha="c" * 40)

    calls = []

    def download(**kw):
        import shutil

        calls.append(kw)
        cache = Path(kw["local_dir"])
        cache.mkdir()
        for item in plan["files"]:
            shutil.copyfile(source / item["path"], cache / item["path"])
        return cache

    result = verify_downloaded(plan, receipt, Uploaded(), download, tmp_path / "cache")
    assert result["verified"] is True
    assert calls[0]["revision"] == "c" * 40 and calls[0]["max_workers"] == 8
    assert set(calls[0]["allow_patterns"]) == {"README.md", "LICENSE", "model.onnx"}


@pytest.mark.parametrize(
    "key,value", [("schema", "other-data-v1"), ("ruleset_id", "nine-kings")]
)
def test_other_row_or_rule_contract_is_rejected_even_with_updated_hashes(
    tmp_path, key, value
):
    from training.production_release import validate_completed

    output, report = completed(tmp_path)
    path = output / "first/manifest.json"
    manifest = json.loads(path.read_text())
    manifest[key] = value
    put(path, manifest)
    report["files"]["manifest.json"] = hashlib.sha256(path.read_bytes()).hexdigest()
    put(output / "report.json", report)
    with pytest.raises(ValueError, match="schema|ruleset"):
        validate_completed(output)
