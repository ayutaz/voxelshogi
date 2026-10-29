"""Small metadata boundaries only; no model/tensor/archive data on Mac."""

import json

import pytest


def manifest_fixture(folder):
    from training.feature_cache import file_hash
    from training.fit import RunConfig
    from training.supervision import label_contract

    folder.mkdir()
    binding = {
        "source_commit": "a" * 40,
        "cache_sha256": "b" * 64,
        "contract": label_contract(),
        "config": RunConfig(device="cpu").value(),
        "environment": {"device": "cpu"},
    }
    run = {"schema": "voxelshogi-training-run-v1", "binding": binding}
    (folder / "config.json").write_text(json.dumps(run))
    (folder / "history.json").write_text(
        json.dumps({"schema": "voxelshogi-training-history-v1", "events": []})
    )
    (folder / "latest").mkdir()
    (folder / "latest/config.json").write_text("{}")
    (folder / "latest/state.safetensors").write_bytes(b"opaque metadata fixture")
    files = [
        {
            "path": name,
            "bytes": (folder / name).stat().st_size,
            "sha256": file_hash(folder / name),
        }
        for name in (
            "config.json",
            "history.json",
            "latest/config.json",
            "latest/state.safetensors",
        )
    ]
    progress = {
        "epoch": 0,
        "next_batch": 0,
        "step": 0,
        "examples": 0,
        "best_val_loss": None,
    }
    manifest = {
        "schema": "voxelshogi-resume-archive-v1",
        "purpose": "resume-state",
        "binding": binding,
        "complete": True,
        "files": files,
        "roles": {
            "latest": {
                "progress": progress,
                "source_checkpoint_sha256": "c" * 64,
                "files": files[2:],
            }
        },
    }
    (folder / "manifest.json").write_text(json.dumps(manifest))
    return binding


def test_resume_metadata_binds_whitelisted_files_and_rejects_parent_symlinks(tmp_path):
    from training.resume_archive import verify_archive

    folder = tmp_path / "archive"
    binding = manifest_fixture(folder)
    assert (
        verify_archive(folder, expected_binding=binding)["roles"]["latest"]["progress"][
            "step"
        ]
        == 0
    )
    original = folder / "latest"
    outside = tmp_path / "outside"
    original.rename(outside)
    original.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        verify_archive(folder, expected_binding=binding)


def test_normal_model_publication_does_not_silently_publish_optimizer_archives(
    tmp_path,
):
    from training.hub_release import plan_release

    (tmp_path / "README.md").write_text("---\nlicense: apache-2.0\n---\nResume fixture")
    (tmp_path / "LICENSE").write_text("Fixture license")
    (tmp_path / "state.safetensors").write_bytes(b"opaque state fixture")
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {"schema": "voxelshogi-resume-archive-v1", "purpose": "resume-state"}
        )
    )
    with pytest.raises(ValueError, match="resume"):
        plan_release(
            tmp_path,
            repo_id="voxelshogi/voxelshogi-transformer-s",
            repo_type="model",
            license_id="apache-2.0",
            license_approved=True,
            source_commit="a" * 40,
        )


def test_archive_best_requires_a_recorded_validation_loss(tmp_path):
    from copy import deepcopy

    from training.resume_archive import verify_archive

    folder = tmp_path / "archive"
    binding = manifest_fixture(folder)
    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    best = folder / "best"
    best.mkdir()
    descriptor = deepcopy(manifest["roles"]["latest"])
    for entry in descriptor["files"]:
        original = entry["path"]
        entry["path"] = original.replace("latest/", "best/")
        (folder / entry["path"]).write_bytes((folder / original).read_bytes())
    manifest["roles"]["best"] = descriptor
    manifest["files"].extend(descriptor["files"])
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="validation"):
        verify_archive(folder, expected_binding=binding)


def test_model_publication_rejects_linked_manifest_before_reading_it(tmp_path):
    from training.hub_release import plan_release

    folder = tmp_path / "model"
    folder.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("not JSON")
    (folder / "manifest.json").symlink_to(outside)
    with pytest.raises(ValueError, match="manifest.*symlink"):
        plan_release(
            folder,
            repo_id="voxelshogi/voxelshogi-transformer-s",
            repo_type="model",
            license_id="apache-2.0",
            license_approved=True,
            source_commit="a" * 40,
        )
