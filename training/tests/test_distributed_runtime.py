"""Pure configuration boundaries; actual tensors and DDP are Linux-only."""

import pytest

from training.distributed_training import DistributedConfig


def test_benchmark_config_fixes_precision_optimizer_and_equal_global_work():
    config = DistributedConfig()
    value = config.value()
    assert value["global_batch"] == 16 and value["updates"] == 128
    assert value["warmup_updates"] == 16 and value["resume_at"] == 64
    assert value["precision"] == "float32" and value["tf32"] is False
    assert value["learning_rate"] == 0.0001
    assert value["optimizer"] == {
        "name": "AdamW",
        "betas": [0.9, 0.999],
        "eps": 1e-8,
        "foreach": False,
        "fused": False,
    }
    assert "world_size" not in value


@pytest.mark.parametrize(
    "changes",
    [
        {"global_batch": 6},
        {"global_batch": True},
        {"updates": 0},
        {"warmup_updates": 128},
        {"warmup_updates": -1},
        {"resume_at": 128},
        {"resume_at": 0},
        {"seed": -1},
        {"learning_rate": 0},
        {"device": "mps"},
    ],
)
def test_non_comparable_or_unsupported_configuration_is_rejected(changes):
    with pytest.raises(ValueError):
        DistributedConfig(**changes)


def archive_fixture(folder):
    import json

    from training.feature_cache import file_hash
    from training.tests.test_resume_archive_policy import manifest_fixture

    binding = manifest_fixture(folder)
    binding["config"] = DistributedConfig(device="cpu").value()
    binding["contract"] = {
        "schema": "voxelshogi-distributed-training-v1",
        "source_commit": binding["source_commit"],
        "initial_model_sha256": "d" * 64,
        "architecture": "voxelshogi-transformer-s-v1",
        "world_size": 2,
        "schedule_sha256": "e" * 64,
    }
    path = folder / "config.json"
    path.write_text(
        json.dumps({"schema": "voxelshogi-training-run-v1", "binding": binding})
    )
    path = folder / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["schema"] = "voxelshogi-distributed-resume-archive-v1"
    manifest["binding"] = binding
    first = manifest["files"][0]
    first.update(
        bytes=(folder / "config.json").stat().st_size,
        sha256=file_hash(folder / "config.json"),
    )
    path.write_text(json.dumps(manifest))
    return binding


def test_distributed_safe_archive_binds_world_size_and_common_update_conditions(
    tmp_path,
):
    from training.resume_archive import _binding, verify_archive

    folder = tmp_path / "archive"
    binding = archive_fixture(folder)
    manifest = verify_archive(folder, expected_binding=binding, profile="distributed")
    assert manifest["schema"] == "voxelshogi-distributed-resume-archive-v1"
    assert set(manifest["roles"]) == {"latest"}
    binding["contract"]["world_size"] = 3
    with pytest.raises(ValueError, match="distributed"):
        _binding(binding, profile="distributed")


def test_distributed_state_requires_separate_role_repo_and_approval():
    from training.hub_release import _policy

    plan = {
        "artifact_role": "distributed-training-state",
        "state_publication_approved": True,
        "repo_id": "voxelshogi/voxelshogi-transformer-s-distributed-training-state-v1",
        "repo_type": "model",
        "private": False,
        "gated": "manual",
        "license_approved": True,
        "license": "apache-2.0",
        "source_commit": "a" * 40,
        "expected_binding": {"source_commit": "a" * 40},
    }
    _policy(plan)
    for changes in (
        {"state_publication_approved": False},
        {"repo_type": "dataset"},
        {"repo_id": "voxelshogi/voxelshogi-transformer-s"},
    ):
        with pytest.raises(ValueError):
            _policy({**plan, **changes})


@pytest.mark.parametrize(
    "changes",
    [
        {"world_size": 3},
        {"source_commit": "b" * 40},
        {"schedule_sha256": "bad"},
        {"initial_model_sha256": "bad"},
        {"architecture": ""},
    ],
)
def test_distributed_contract_rejects_changed_conditions(tmp_path, changes):
    from training.resume_archive import _binding

    binding = archive_fixture(tmp_path / "archive")
    binding["contract"].update(changes)
    with pytest.raises(ValueError, match="distributed"):
        _binding(binding, profile="distributed")


def test_declared_low_precision_or_changed_optimizer_cannot_resume(tmp_path):
    from training.resume_archive import _binding

    binding = archive_fixture(tmp_path / "archive")
    binding["config"]["precision"] = "float16"
    with pytest.raises(ValueError, match="configuration"):
        _binding(binding, profile="distributed")


def test_actual_state_role_inventory_and_normal_model_rejection(tmp_path):
    from training.hub_release import plan_release, publish_release

    folder = tmp_path / "archive"
    binding = archive_fixture(folder)
    (folder / "README.md").write_text(
        "---\nlicense: apache-2.0\n---\n# Opaque fixture\n\n"
        "## Training and provenance\nMetadata fixture only.\n\n"
        "## Resume contents\nOne model/optimizer and all rank RNGs.\n\n"
        "## Verification\nNo tensor decoding in this test.\n\n"
        "## Access and license\nFixture only.\n"
    )
    (folder / "LICENSE").write_text("Opaque fixture")
    arguments = dict(
        repo_id="voxelshogi/voxelshogi-transformer-s-distributed-training-state-v1",
        repo_type="model",
        license_id="apache-2.0",
        license_approved=True,
        source_commit="a" * 40,
    )
    plan = plan_release(
        folder,
        **arguments,
        artifact_role="distributed-training-state",
        state_publication_approved=True,
        expected_binding=binding,
    )
    assert len(plan["files"]) == 7
    assert publish_release(folder, plan, None)["dry_run"] is True
    with pytest.raises(ValueError, match="separately"):
        plan_release(folder, **arguments)


def test_distributed_archive_never_selects_best_from_holdout(tmp_path):
    import json
    from copy import deepcopy

    from training.resume_archive import verify_archive

    folder = tmp_path / "archive"
    binding = archive_fixture(folder)
    path = folder / "manifest.json"
    manifest = json.loads(path.read_text())
    best = deepcopy(manifest["roles"]["latest"])
    best["progress"]["best_val_loss"] = 0.5
    (folder / "best").mkdir()
    for entry in best["files"]:
        source = folder / entry["path"]
        entry["path"] = entry["path"].replace("latest/", "best/")
        (folder / entry["path"]).write_bytes(source.read_bytes())
    manifest["roles"]["best"] = best
    manifest["files"].extend(best["files"])
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="distributed.*best"):
        verify_archive(folder, expected_binding=binding, profile="distributed")


def test_distributed_archive_never_enters_normal_model_publication(tmp_path):
    import json

    from training.hub_release import plan_release

    # All of these filenames would otherwise be permitted for a normal model.
    (tmp_path / "README.md").write_text("---\nlicense: apache-2.0\n---\nFixture")
    (tmp_path / "LICENSE").write_text("Opaque fixture")
    (tmp_path / "state.safetensors").write_bytes(b"opaque state fixture")
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema": "voxelshogi-distributed-resume-archive-v1",
                "purpose": "resume-state",
            }
        )
    )
    with pytest.raises(ValueError, match="separately"):
        plan_release(
            tmp_path,
            repo_id="voxelshogi/fixture",
            repo_type="model",
            license_id="apache-2.0",
            license_approved=True,
            source_commit="a" * 40,
        )
