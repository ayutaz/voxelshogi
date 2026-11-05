"""Synthetic opaque ONNX bytes test staging, never evidence of real M inference."""

import json

import pytest


def fixture(tmp_path):
    import numpy as np
    from safetensors.numpy import save_file

    from export.research_contract import (
        ARCHITECTURES,
        architecture_config,
        parameter_count,
    )
    from training.evaluation_v2 import fingerprint
    from training.hub_release import plan_release
    from training.research_probe import _inputs, probe_protocol

    folder = tmp_path / "published"
    folder.mkdir()
    protocol = probe_protocol("a" * 40)
    inputs = _inputs(protocol)
    for name in ARCHITECTURES:
        target = folder / name
        target.mkdir()
        (target / "fp32.onnx").write_bytes(b"opaque fixture, not an ONNX model")
        refs = {}
        for index, features, _ in inputs:
            refs[f"fixture{index}.features"] = features[None]
            refs[f"fixture{index}.policy"] = np.zeros((1, 1067985), dtype=np.float32)
            refs[f"fixture{index}.value"] = np.zeros((1, 1), dtype=np.float32)
        save_file(refs, target / "references.safetensors")
    manifest = {
        "schema": "voxelshogi-research-operator-release-v1",
        "source_commit": "a" * 40,
        "pipeline_complete": True,
        "protocol_sha256": fingerprint(protocol),
        "probe_result": {
            "complete": True,
            "source_commit": "a" * 40,
            "architectures": {
                n: {
                    "export": {
                        "passed": True,
                        "parameter_count": parameter_count(architecture_config(n)),
                    }
                }
                for n in ARCHITECTURES
            },
        },
    }
    (folder / "config.json").write_text(json.dumps(protocol))
    (folder / "manifest.json").write_text(json.dumps(manifest))
    (folder / "README.md").write_text(
        "# Synthetic fixture\n\n## Model and provenance\nOpaque fixture; no real model or Hub publication.\n\n## Usage and schema\nStaging test only.\n\n## Verification and limitations\nNo actual inference.\n\n## Access and license\nApache-2.0 fixture.\n"
    )
    (folder / "LICENSE").write_text("Apache-2.0 test fixture")
    plan = plan_release(
        folder,
        repo_id="voxelshogi/voxelshogi-research-operator-probe-v1",
        repo_type="model",
        license_id="apache-2.0",
        license_approved=True,
        source_commit="a" * 40,
    )
    receipt = {
        "verified": True,
        "dry_run": False,
        "community_disabled": True,
        "repo_id": plan["repo_id"],
        "repo_type": "model",
        "hub_commit": "b" * 40,
        "release_sha256": fingerprint(plan),
    }
    return folder, plan, receipt


def test_exact_onnx_bytes_and_full_zero_reference_bytes_survive_staging(tmp_path):
    import hashlib

    from training.research_browser_inputs import prepare_inputs

    folder, plan, receipt = fixture(tmp_path)
    out = tmp_path / "browser"
    result = prepare_inputs(folder, out, plan=plan, receipt=receipt)
    assert result["trained"] is False
    assert result["origin"]["revision"] == "b" * 40
    assert [m["name"] for m in result["models"]] == ["full", "axial", "geometry", "cnn"]
    assert result["numeric"] == {
        "policy_atol": 1e-4,
        "policy_rtol": 1e-4,
        "value_atol": 1e-5,
        "value_rtol": 1e-5,
    }
    expected = hashlib.sha256(b"\0" * 4271940).hexdigest()
    for model in result["models"]:
        assert (
            out / model["model"]["path"]
        ).read_bytes() == b"opaque fixture, not an ONNX model"
        assert [f["id"] for f in model["fixtures"]] == [0, 3]
        for f in model["fixtures"]:
            assert f["policy"]["bytes"] == 4271940
            assert f["policy"]["sha256"] == expected
            assert f["value"]["bytes"] == 4
            assert f["features"]["bytes"] == 125388
    assert json.loads((out / "browser-inputs.json").read_text()) == result


@pytest.mark.parametrize("change", ["unverified", "floating-revision", "changed-body"])
def test_unverified_or_changed_source_never_creates_browser_staging(tmp_path, change):
    from training.research_browser_inputs import prepare_inputs

    folder, plan, receipt = fixture(tmp_path)
    if change == "unverified":
        receipt["verified"] = False
    elif change == "floating-revision":
        receipt["hub_commit"] = "main"
    else:
        (folder / "full/fp32.onnx").write_bytes(b"changed opaque fixture")
    out = tmp_path / "browser"
    with pytest.raises(ValueError, match="verified"):
        prepare_inputs(folder, out, plan=plan, receipt=receipt)
    assert not out.exists()
