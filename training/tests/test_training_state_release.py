"""Opaque resume metadata publication checks; no tensor decoding or Hub calls."""

import json

import pytest

from training.hub_release import plan_release, publish_release
from training.tests.test_resume_archive_policy import manifest_fixture


def package(folder):
    binding = manifest_fixture(folder)
    (folder / "README.md").write_text(
        "---\nlicense: apache-2.0\n---\n# Opaque state fixture\n\n"
        "## Training and provenance\nFixture only.\n\n"
        "## Resume contents\nOptimizer and RNG state, latest/best.\n\n"
        "## Verification\nFixture only.\n\n"
        "## Access and license\nFixture only.\n"
    )
    (folder / "LICENSE").write_text("Opaque license fixture")
    return binding


def plan(folder, binding, **overrides):
    arguments = dict(
        repo_id="voxelshogi/voxelshogi-transformer-s-training-state",
        repo_type="model",
        license_id="apache-2.0",
        license_approved=True,
        source_commit="a" * 40,
        artifact_role="training-state",
        state_publication_approved=True,
        expected_binding=binding,
    )
    return plan_release(folder, **(arguments | overrides))


def test_separate_state_approval_and_external_binding_are_required(tmp_path):
    folder = tmp_path / "archive"
    binding = package(folder)
    reviewed = plan(folder, binding)
    assert reviewed["state_publication_approved"] is True
    assert len(reviewed["files"]) == 7
    assert publish_release(folder, reviewed, None)["dry_run"] is True
    for changes in (
        {"state_publication_approved": False},
        {"expected_binding": None},
        {"repo_id": "voxelshogi/voxelshogi-transformer-s"},
        {"license_approved": False},
        {"source_commit": "b" * 40},
        {"artifact_role": "inference-package"},
    ):
        with pytest.raises(ValueError):
            plan(folder, binding, **changes)


@pytest.mark.parametrize("change", ["extra", "hash", "binding", "best", "card", "link"])
def test_unexpected_or_changed_state_is_rejected(tmp_path, change):
    folder = tmp_path / "archive"
    binding = package(folder)
    if change == "extra":
        (folder / "optimizer.pt").write_bytes(b"not publishable")
    elif change == "hash":
        path = folder / "latest/state.safetensors"
        raw = path.read_bytes()
        path.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
    elif change == "binding":
        binding = binding | {"cache_sha256": "d" * 64}
    elif change == "best":
        path = folder / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["roles"]["best"] = manifest["roles"]["latest"]
        path.write_text(json.dumps(manifest))
    elif change == "card":
        (folder / "README.md").write_text(
            "---\nlicense: apache-2.0\n---\nMissing contents"
        )
    elif change == "link":
        source = folder / "latest"
        target = tmp_path / "outside"
        source.rename(target)
        source.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError):
        plan(folder, binding)


def test_state_upload_reserves_lifetime_bytes_before_api_and_never_resends_blindly(
    tmp_path,
):
    from training.tests.test_hub_release import Hub

    folder = tmp_path / "archive"
    binding = package(folder)
    reviewed, api = plan(folder, binding), Hub()
    ledger = tmp_path / "budget.json"
    ledger.write_text(
        json.dumps(
            {
                "schema": "voxelshogi-state-upload-budget-v1",
                "approved_maximum_new_bytes": 1024**3,
                "reservations": [],
            }
        )
    )
    with pytest.raises(ValueError, match="budget"):
        publish_release(folder, reviewed, api, execute=True, system="linux")
    assert api.calls == []
    receipt = publish_release(
        folder, reviewed, api, execute=True, system="linux", upload_budget=ledger
    )
    reservations = json.loads(ledger.read_text())["reservations"]
    assert reservations == [
        {
            "release_sha256": receipt["release_sha256"],
            "maximum_bytes": sum(file["bytes"] for file in reviewed["files"]),
        }
    ]
    api.calls.clear()
    with pytest.raises(ValueError, match="reserved"):
        publish_release(
            folder, reviewed, api, execute=True, system="linux", upload_budget=ledger
        )
    assert api.calls == []


def test_used_budget_and_mac_publication_do_not_create_side_effects(tmp_path):
    from training.tests.test_hub_release import Hub

    folder = tmp_path / "archive"
    binding = package(folder)
    reviewed, api = plan(folder, binding), Hub()
    ledger = tmp_path / "budget.json"
    contents = {
        "schema": "voxelshogi-state-upload-budget-v1",
        "approved_maximum_new_bytes": 1024**3,
        "reservations": [{"release_sha256": "b" * 64, "maximum_bytes": 1024**3}],
    }
    ledger.write_text(json.dumps(contents))
    for system in ("darwin", "linux"):
        with pytest.raises(ValueError):
            publish_release(
                folder, reviewed, api, execute=True, system=system, upload_budget=ledger
            )
        assert api.calls == []
        assert json.loads(ledger.read_text()) == contents


def test_api_failure_keeps_the_reserved_upper_bound_for_audit(tmp_path):
    from training.tests.test_hub_release import Hub

    folder = tmp_path / "archive"
    binding = package(folder)
    reviewed = plan(folder, binding)
    ledger = tmp_path / "budget.json"
    ledger.write_text(
        json.dumps(
            {
                "schema": "voxelshogi-state-upload-budget-v1",
                "approved_maximum_new_bytes": 1024**3,
                "reservations": [],
            }
        )
    )

    class Failed(Hub):
        def upload_folder(self, **kwargs):
            raise RuntimeError("response lost")

    with pytest.raises(RuntimeError, match="response lost"):
        publish_release(
            folder,
            reviewed,
            Failed(),
            execute=True,
            system="linux",
            upload_budget=ledger,
        )
    assert len(json.loads(ledger.read_text())["reservations"]) == 1
