"""Hub publication policy: exercise side effects through a recording fake."""

import hashlib
from types import SimpleNamespace

import pytest


def release(tmp_path):
    from training.hub_release import plan_release

    (tmp_path / "README.md").write_text("---\nlicense: apache-2.0\n---\nTest model\n")
    (tmp_path / "LICENSE").write_text("Test license fixture\n")
    (tmp_path / "model.onnx").write_bytes(b"abc")
    return plan_release(
        tmp_path,
        repo_id="voxelshogi/test-model",
        repo_type="model",
        license_id="apache-2.0",
        license_approved=True,
        source_commit="a" * 40,
    )


class Hub:
    def __init__(self, *, private=False, gated="manual"):
        self.private, self.gated, self.calls = private, gated, []

    def repo_info(self, **kwargs):
        self.calls.append(("info", kwargs))
        return SimpleNamespace(private=self.private, gated=self.gated, sha="b" * 40)

    def repo_exists(self, **kwargs):
        self.calls.append(("exists", kwargs))
        return True

    def update_repo_settings(self, **kwargs):
        self.calls.append(("settings", kwargs))

    def upload_folder(self, **kwargs):
        self.calls.append(("upload", kwargs))
        return SimpleNamespace(oid="c" * 40)


def test_new_repo_is_public_and_gated_before_any_artifact_upload(tmp_path):
    from training.hub_release import create_release_repository

    class EmptyHub(Hub):
        def repo_exists(self, **kwargs):
            return False

        def create_repo(self, **kwargs):
            self.calls.append(("create", kwargs))

    plan, api = release(tmp_path), EmptyHub()
    create_release_repository(plan, api, execute=False, system="linux")
    assert api.calls == []
    create_release_repository(plan, api, execute=True, system="linux")
    create = next(v for name, v in api.calls if name == "create")
    assert create == {
        "repo_id": "voxelshogi/test-model",
        "repo_type": "model",
        "private": False,
    }
    assert not any(name == "upload" for name, _ in api.calls)


def test_hash_verification_does_not_accept_an_upload_receipt_as_proof(tmp_path):
    from training.hub_release import verify_release

    plan = release(tmp_path)
    receipt = {
        "hub_commit": "c" * 40,
        "repo_id": plan["repo_id"],
        "repo_type": "model",
        "release_sha256": hashlib.sha256(
            __import__("json")
            .dumps(plan, sort_keys=True, separators=(",", ":"))
            .encode()
        ).hexdigest(),
    }

    class UploadedHub(Hub):
        def repo_info(self, **kwargs):
            assert kwargs["revision"] == "c" * 40
            return SimpleNamespace(private=False, gated="manual", sha="c" * 40)

    def fetch(**kwargs):
        assert kwargs["revision"] == "c" * 40
        return tmp_path / kwargs["filename"]

    assert (
        verify_release(plan, receipt, UploadedHub(), fetch, system="linux")["verified"]
        is True
    )
    (tmp_path / "model.onnx").write_bytes(b"abd")
    with pytest.raises(ValueError, match="hash"):
        verify_release(plan, receipt, UploadedHub(), fetch, system="linux")


def test_plan_pins_files_and_requires_explicit_execution(tmp_path):
    from training.hub_release import publish_release

    plan = release(tmp_path)
    assert plan["private"] is False and plan["gated"] == "manual"
    model = next(f for f in plan["files"] if f["path"] == "model.onnx")
    assert model == {
        "path": "model.onnx",
        "bytes": 3,
        "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    }
    api = Hub()
    result = publish_release(tmp_path, plan, api, execute=False, system="linux")
    assert result["dry_run"] and api.calls == []


@pytest.mark.parametrize(
    "change",
    [
        {"repo_id": "ayousanz/test-model"},
        {"repo_id": "voxelshogi/../escape"},
        {"repo_type": "space"},
        {"private": True},
        {"gated": "auto"},
        {"license_approved": False},
    ],
)
def test_wrong_destination_or_unapproved_policy_has_no_side_effects(tmp_path, change):
    from training.hub_release import publish_release

    plan = {**release(tmp_path), **change}
    api = Hub()
    with pytest.raises(ValueError):
        publish_release(tmp_path, plan, api, execute=True, system="linux")
    assert api.calls == []


def test_changed_artifact_and_mac_upload_are_rejected_before_network(tmp_path):
    from training.hub_release import publish_release

    plan = release(tmp_path)
    api = Hub()
    with pytest.raises(ValueError, match="Linux"):
        publish_release(tmp_path, plan, api, execute=True, system="darwin")
    (tmp_path / "model.onnx").write_bytes(b"abcd")
    with pytest.raises(ValueError, match="changed"):
        publish_release(tmp_path, plan, api, execute=True, system="linux")
    assert api.calls == []


def test_secret_files_symlinks_and_checkpoints_cannot_enter_release(tmp_path):
    from training.hub_release import plan_release

    release(tmp_path)
    for name in [".env", "worker.log", "optimizer.pt"]:
        path = tmp_path / name
        path.write_text("must not upload")
        with pytest.raises(ValueError):
            plan_release(
                tmp_path,
                repo_id="voxelshogi/test-model",
                repo_type="model",
                license_id="apache-2.0",
                license_approved=True,
                source_commit="a" * 40,
            )
        path.unlink()
    (tmp_path / "link.onnx").symlink_to(tmp_path / "model.onnx")
    with pytest.raises(ValueError):
        release(tmp_path)


def test_gating_is_verified_before_upload_and_private_repo_is_not_exposed(tmp_path):
    from training.hub_release import publish_release

    plan = release(tmp_path)
    for api in [Hub(private=True), Hub(gated="auto")]:
        with pytest.raises(ValueError):
            publish_release(tmp_path, plan, api, execute=True, system="linux")
        assert not any(name == "upload" for name, _ in api.calls)


def test_manual_gate_precedes_upload_and_receipt_pins_hub_commit(tmp_path):
    from training.hub_release import publish_release

    plan, api = release(tmp_path), Hub()
    result = publish_release(tmp_path, plan, api, execute=True, system="linux")
    names = [name for name, _ in api.calls]
    assert names.index("settings") < names.index("upload")
    settings = next(v for name, v in api.calls if name == "settings")
    assert settings["gated"] == "manual"
    upload = next(v for name, v in api.calls if name == "upload")
    assert set(upload["allow_patterns"]) == {"README.md", "LICENSE", "model.onnx"}
    assert upload["parent_commit"] == "b" * 40
    assert result["hub_commit"] == "c" * 40
    assert result["verified"] is False  # Upload success alone is not hash verification.
    assert (
        result["release_sha256"]
        == hashlib.sha256(
            __import__("json")
            .dumps(plan, sort_keys=True, separators=(",", ":"))
            .encode()
        ).hexdigest()
    )
