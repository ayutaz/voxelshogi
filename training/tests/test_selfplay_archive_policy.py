"""Archive binding and publication boundaries only; no tensor data on Mac."""

import json
from copy import deepcopy

import pytest


def binding():
    from training.selfplay_training import TrainConfig

    return {
        "source_commit": "a" * 40,
        "cache_sha256": "b" * 64,
        "config": TrainConfig(device="cpu").value(),
        "contract": {
            "schema": "voxelshogi-selfplay-training-v1",
            "source_commit": "a" * 40,
            "parent_model_sha256": "c" * 64,
            "generation": 0,
            "architecture": "fixture-v1",
        },
        "environment": {"device": "cpu"},
    }


def test_selfplay_binding_requires_explicit_archive_profile():
    from training.resume_archive import _binding

    _binding(binding(), profile="selfplay")
    with pytest.raises(ValueError):
        _binding(binding())
    with pytest.raises(ValueError):
        _binding(binding(), profile="unknown")
    for field, value in [
        ("generation", True),
        ("generation", 64),
        ("source_commit", "d" * 40),
        ("parent_model_sha256", "short"),
        ("architecture", "../unknown"),
    ]:
        bad = binding()
        bad["contract"][field] = value
        with pytest.raises(ValueError):
            _binding(bad, profile="selfplay")
    bad = binding()
    bad["config"]["selection"] = "test selection"
    with pytest.raises(ValueError):
        _binding(bad, profile="selfplay")


def archive_fixture(folder):
    from training.tests.test_resume_archive_policy import manifest_fixture

    manifest_fixture(folder)
    value = binding()
    (folder / "config.json").write_text(
        json.dumps({"schema": "voxelshogi-training-run-v1", "binding": value})
    )
    path = folder / "manifest.json"
    m = json.loads(path.read_text())
    m.update(schema="voxelshogi-selfplay-resume-archive-v1", binding=value)
    import hashlib

    for file in m["files"]:
        raw = (folder / file["path"]).read_bytes()
        file.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    path.write_text(json.dumps(m))
    return value


def test_metadata_profile_is_part_of_archive_schema_and_disallows_best(tmp_path):
    from training.resume_archive import verify_archive
    from training.tests.test_resume_archive_policy import manifest_fixture

    supervised_folder = tmp_path / "supervised"
    supervised = manifest_fixture(supervised_folder)
    with pytest.raises(ValueError):
        verify_archive(
            supervised_folder, expected_binding=supervised, profile="selfplay"
        )
    folder = tmp_path / "archive"
    value = archive_fixture(folder)
    path = folder / "manifest.json"
    m = json.loads(path.read_text())
    assert verify_archive(folder, expected_binding=value, profile="selfplay")[
        "complete"
    ]
    with pytest.raises(ValueError):
        verify_archive(folder, expected_binding=value)
    before_best = deepcopy(m)
    best = deepcopy(m["roles"]["latest"])
    best["progress"]["best_val_loss"] = 0.5
    (folder / "best").mkdir()
    for entry in best["files"]:
        original = entry["path"]
        entry["path"] = original.replace("latest/", "best/")
        (folder / entry["path"]).write_bytes((folder / original).read_bytes())
    m["roles"]["best"] = best
    m["files"].extend(best["files"])
    path.write_text(json.dumps(m))
    with pytest.raises(ValueError, match="selfplay.*best|best.*selfplay"):
        verify_archive(folder, expected_binding=value, profile="selfplay")
    before_best["roles"]["latest"]["progress"]["best_val_loss"] = 0.5
    path.write_text(json.dumps(before_best))
    with pytest.raises(ValueError, match="selfplay.*best|best.*selfplay"):
        verify_archive(folder, expected_binding=value, profile="selfplay")


def test_selfplay_archive_never_enters_normal_model_publication(tmp_path):
    from training.hub_release import plan_release

    (tmp_path / "README.md").write_text("---\nlicense: apache-2.0\n---\nFixture")
    (tmp_path / "LICENSE").write_text("Fixture")
    (tmp_path / "state.safetensors").write_bytes(b"opaque metadata fixture")
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "schema": "voxelshogi-selfplay-resume-archive-v1",
                "purpose": "resume-state",
            }
        )
    )
    with pytest.raises(ValueError, match="resume"):
        plan_release(
            tmp_path,
            repo_id="voxelshogi/fixture",
            repo_type="model",
            license_id="apache-2.0",
            license_approved=True,
            source_commit="a" * 40,
        )


def test_selfplay_state_publication_requires_its_own_role_repo_and_approval(tmp_path):
    from training.hub_release import plan_release, publish_release

    value = archive_fixture(tmp_path / "archive")
    folder = tmp_path / "archive"
    card = "---\nlicense: apache-2.0\n---\n"
    for title in (
        "Training and provenance",
        "Resume contents",
        "Verification",
        "Access and license",
    ):
        card += "## " + title + "\nExplicit fixture text.\n"
    (folder / "README.md").write_text(card)
    (folder / "LICENSE").write_text("Fixture license")
    settings = dict(
        repo_id="voxelshogi/voxelshogi-transformer-s-selfplay-training-state-v1",
        repo_type="model",
        license_id="apache-2.0",
        license_approved=True,
        source_commit="a" * 40,
        artifact_role="selfplay-training-state",
        state_publication_approved=True,
        expected_binding=value,
    )
    plan = plan_release(folder, **settings)
    assert plan["artifact_role"] == "selfplay-training-state"
    assert {x["path"] for x in plan["files"]} == {
        "README.md",
        "LICENSE",
        "manifest.json",
        "config.json",
        "history.json",
        "latest/config.json",
        "latest/state.safetensors",
    }
    assert publish_release(folder, plan, None)["dry_run"]
    for change in (
        {"state_publication_approved": False},
        {"repo_id": "voxelshogi/voxelshogi-transformer-s-training-state"},
        {"artifact_role": "training-state"},
        {"repo_type": "dataset"},
    ):
        with pytest.raises(ValueError):
            plan_release(folder, **{**settings, **change})
    with pytest.raises(ValueError, match="Linux"):
        publish_release(folder, plan, None, execute=True, system="darwin")
    with pytest.raises(ValueError, match="budget"):
        publish_release(folder, plan, None, execute=True, system="linux")

    # Opaque metadata exercises the existing public/manual, Community OFF and
    # fixed-revision hash harness without creating any real repository.
    from types import SimpleNamespace

    from training.hub_release import verify_release
    from training.tests.test_hub_release import Hub

    class Remote(Hub):
        def repo_info(self, **kwargs):
            if "revision" in kwargs:
                assert kwargs["revision"] == "c" * 40
                return SimpleNamespace(private=False, gated="manual", sha="c" * 40)
            return super().repo_info(**kwargs)

    ledger = tmp_path / "upload-budget.json"
    ledger.write_text(
        json.dumps(
            {
                "schema": "voxelshogi-state-upload-budget-v1",
                "approved_maximum_new_bytes": 1024**3,
                "reservations": [],
            }
        )
    )
    api = Remote()
    receipt = publish_release(
        folder, plan, api, execute=True, system="linux", upload_budget=ledger
    )
    fetched = []

    def fetch(**kwargs):
        assert kwargs["repo_id"] == settings["repo_id"]
        assert kwargs["repo_type"] == "model" and kwargs["revision"] == "c" * 40
        fetched.append(kwargs["filename"])
        return folder / kwargs["filename"]

    verified = verify_release(plan, receipt, api, fetch, system="linux")
    assert verified["verified"] and verified["community_disabled"]
    assert set(fetched) == {x["path"] for x in plan["files"]}
    api.calls.clear()
    with pytest.raises(ValueError, match="reserved"):
        publish_release(
            folder, plan, api, execute=True, system="linux", upload_budget=ledger
        )
    assert not api.calls
    (folder / "latest/state.safetensors").write_bytes(b"changed opaque fixture")
    with pytest.raises(ValueError, match="hash"):
        verify_release(plan, receipt, api, fetch, system="linux")
