"""Typed research state metadata and dedicated publication policy, fake files only."""

import json

import pytest

from training.feature_cache import file_hash
from training.hub_release import plan_release
from training.research_fit import ResearchRunConfig
from training.tests.test_training_state_release import package


def research_package(folder):
    binding = package(folder)
    binding["config"] = ResearchRunConfig(device="cpu").value()
    path = folder / "config.json"
    path.write_text(
        json.dumps({"schema": "voxelshogi-training-run-v1", "binding": binding})
    )
    path = folder / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest.update(schema="voxelshogi-research-resume-archive-v1", binding=binding)
    for entry in manifest["files"]:
        if entry["path"] == "config.json":
            entry.update(
                bytes=(folder / "config.json").stat().st_size,
                sha256=file_hash(folder / "config.json"),
            )
    path.write_text(json.dumps(manifest))
    return binding


def research_plan(folder, binding, **changes):
    args = {
        "repo_id": "voxelshogi/voxelshogi-research-training-state-v1",
        "repo_type": "model",
        "license_id": "apache-2.0",
        "license_approved": True,
        "source_commit": "a" * 40,
        "artifact_role": "research-training-state",
        "state_publication_approved": True,
        "expected_binding": binding,
    }
    return plan_release(folder, **(args | changes))


def test_research_profile_binds_architecture_in_a_dedicated_state_repo(tmp_path):
    from training.resume_archive import verify_archive

    folder = tmp_path / "archive"
    binding = research_package(folder)
    verified = verify_archive(folder, expected_binding=binding, profile="research")
    assert verified["binding"]["config"]["architecture"]["architecture"] == "full"
    planned = research_plan(folder, binding)
    assert planned["artifact_role"] == "research-training-state"
    assert len(planned["files"]) == 7
    assert planned["gated"] == "manual" and planned["private"] is False
    for profile in ("m6", "selfplay", "distributed"):
        with pytest.raises(ValueError):
            verify_archive(folder, expected_binding=binding, profile=profile)


@pytest.mark.parametrize(
    "change",
    [
        "normal",
        "m6-repo",
        "unapproved",
        "wrong-binding",
        "wrong-schema",
        "wrong-dimensions",
    ],
)
def test_research_state_cannot_be_published_as_normal_weights_or_another_profile(
    tmp_path, change
):
    folder = tmp_path / "archive"
    binding = research_package(folder)
    overrides = {}
    if change == "normal":
        overrides = {
            "artifact_role": "artifacts",
            "state_publication_approved": False,
            "expected_binding": None,
        }
    elif change == "m6-repo":
        overrides = {"repo_id": "voxelshogi/voxelshogi-transformer-s-training-state"}
    elif change == "unapproved":
        overrides = {"state_publication_approved": False}
    elif change == "wrong-binding":
        overrides = {"expected_binding": binding | {"cache_sha256": "c" * 64}}
    elif change == "wrong-schema":
        path = folder / "manifest.json"
        value = json.loads(path.read_text())
        value["schema"] = "voxelshogi-resume-archive-v1"
        path.write_text(json.dumps(value))
    else:
        import copy

        wrong = copy.deepcopy(binding)
        wrong["config"]["architecture"]["architecture"] = "axial"
        overrides = {"expected_binding": wrong}
    with pytest.raises(ValueError):
        research_plan(folder, binding, **overrides)


def test_research_state_files_have_bounded_m_capacity_without_raising_inference_limits():
    from training.hub_release import artifact_limits

    assert artifact_limits("research-training-state", "latest/state.safetensors") == (
        536_870_912,
        2_147_483_648,
    )
    assert artifact_limits("research-training-state", "latest/config.json") == (
        67_108_864,
        2_147_483_648,
    )
    assert artifact_limits("inference-package", "fp32.onnx") == (
        67_108_864,
        536_870_912,
    )
    assert artifact_limits("inference-package", "evaluation.json") == (
        16_777_216,
        536_870_912,
    )
    assert artifact_limits("training-state", "latest/state.safetensors") == (
        67_108_864,
        536_870_912,
    )


def test_archive_validator_dispatches_research_config_checks(tmp_path):
    from training.resume_archive import _binding

    binding = research_package(tmp_path / "archive")
    binding["config"]["precision"] = "float16"
    with pytest.raises(ValueError):
        _binding(binding, profile="research")


def test_publication_inventory_uses_the_research_limits(monkeypatch, tmp_path):
    from training import hub_release

    folder = tmp_path / "archive"
    binding = research_package(folder)
    limits, observed = hub_release.artifact_limits, []

    def limited(role, path):
        observed.append((role, path))
        return limits(role, path)

    monkeypatch.setattr(hub_release, "artifact_limits", limited)
    research_plan(folder, binding)
    assert ("research-training-state", "latest/state.safetensors") in observed
    assert ("research-training-state", "") in observed
