"""Pure opaque files exercise the explicit inference publication role, no models."""

import hashlib
import json

import pytest

from training.hub_release import plan_release, publish_release, verify_release
from training.tests.test_trained_metadata import fixture


def package(folder):
    from export.trained import review_evaluation

    evaluated = fixture(folder.parent / "evaluation")
    review = review_evaluation(
        evaluated, context={"sourceCommit": "a" * 40, "sourceDirty": False}, seed=314159
    )
    folder.mkdir()

    def file(path, content=b"opaque"):
        target = folder / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return {
            "path": path,
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }

    checkpoint = file(
        "model.safetensors", (evaluated / "student.safetensors").read_bytes()
    )
    names = ["initial-b", "after-one-w", "mate-in-one-b", "material-b"]
    manifest = {
        "schema": 1,
        "trained": True,
        "id": review["model_id"],
        "license": "Apache-2.0",
        "seed": 314159,
        "sourceCommit": "a" * 40,
        "sourceDirty": False,
        "checkpoint": checkpoint,
        "training": review["training"],
        "fixtures": [
            {"name": name, "input": file(f"inputs/{name}.f32")} for name in names
        ],
        "variants": [
            {
                "id": precision,
                "precision": precision,
                "model": file(f"{precision}.onnx"),
                "references": {
                    name: {
                        output: file(f"reference/{precision}/{name}-{output}.f32")
                        for output in ("policy", "value")
                    }
                    for name in names
                },
            }
            for precision in ("fp32", "fp16", "int8")
        ],
    }
    for name in ("evaluation.json", "test.json"):
        file(name, (evaluated / name).read_bytes())
    file("manifest.json", json.dumps(manifest).encode())
    file("LICENSE", b"Opaque license fixture")
    file(
        "README.md",
        b"---\nlicense: apache-2.0\n---\n# Opaque model fixture\n\n## Training and provenance\nFixture only.\n\n## Evaluation\nFixture only.\n\n## Inference\nFixture only.\n\n## Access and license\nFixture only.\n",
    )
    return manifest


def plan(folder, **overrides):
    return plan_release(
        folder,
        **dict(
            repo_id="voxelshogi/test-model",
            repo_type="model",
            license_id="apache-2.0",
            license_approved=True,
            source_commit="a" * 40,
            artifact_role="inference-package",
        )
        | overrides,
    )


def test_only_explicit_role_includes_complete_hash_pinned_references(tmp_path):
    folder = tmp_path / "release"
    package(folder)
    result = plan(folder)
    names = {entry["path"] for entry in result["files"]}
    assert len(names) == 37
    assert "reference/int8/material-b-policy.f32" in names
    assert result["artifact_role"] == "inference-package"
    with pytest.raises(ValueError, match="unexpected"):
        from training.hub_release import _inventory

        _inventory(folder, "model")
    assert publish_release(folder, result, None)["dry_run"] is True


@pytest.mark.parametrize(
    "change",
    [
        "unknown",
        "optimizer",
        "reference",
        "report",
        "checkpoint",
        "source",
        "license",
        "variant",
        "missing",
        "ci",
        "dataset",
        "unapproved",
        "role",
        "card",
    ],
)
def test_unreviewed_files_and_mismatched_evidence_cannot_be_published(tmp_path, change):
    folder = tmp_path / "release"
    manifest = package(folder)
    arguments = {}
    if change in ("unknown", "optimizer"):
        (
            folder
            / ("unlisted.f32" if change == "unknown" else "optimizer.safetensors")
        ).write_bytes(b"secret")
    elif change in ("reference", "report", "checkpoint"):
        path = {
            "reference": "reference/fp16/after-one-w-policy.f32",
            "report": "test.json",
            "checkpoint": "model.safetensors",
        }[change]
        target = folder / path
        original = target.read_bytes()
        target.write_bytes(bytes([original[0] ^ 1]) + original[1:])
    elif change == "missing":
        (folder / "inputs/material-b.f32").unlink()
    elif change == "card":
        (folder / "README.md").write_text("---\nlicense: apache-2.0\n---\nempty")
    elif change == "source":
        manifest["sourceCommit"] = "b" * 40
        manifest["training"]["binding"]["source_commit"] = "b" * 40
        manifest["training"]["receipt"]["binding"]["source_commit"] = "b" * 40
    elif change == "license":
        manifest["license"] = "MIT"
    elif change == "variant":
        manifest["variants"].pop()
        (folder / "int8.onnx").unlink()
        for path in (folder / "reference/int8").iterdir():
            path.unlink()
    elif change == "ci":
        manifest["ciFixture"] = "not a trained release"
    elif change == "dataset":
        arguments["repo_type"] = "dataset"
    elif change == "unapproved":
        arguments["license_approved"] = False
    elif change == "role":
        arguments["artifact_role"] = "anything"
    (folder / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        plan(folder, **arguments)


def test_catalog_requires_verified_fixed_hub_revision_and_same_release(tmp_path):
    from training.inference_release import catalog_release
    from training.tests.test_hub_release import Hub

    folder = tmp_path / "release"
    manifest = package(folder)
    reviewed = plan(folder)

    class Uploaded(Hub):
        def repo_info(self, **kwargs):
            from types import SimpleNamespace

            return SimpleNamespace(private=False, gated="manual", sha="c" * 40)

    receipt = publish_release(
        folder, reviewed, Uploaded(), execute=True, system="linux"
    )
    with pytest.raises(ValueError, match="verified"):
        catalog_release(folder, reviewed, receipt)
    verified = verify_release(
        reviewed,
        receipt,
        Uploaded(),
        lambda **kw: folder / kw["filename"],
        system="linux",
    )
    result = catalog_release(folder, reviewed, verified)
    assert result["revision"] == "c" * 40
    assert result["manifest"] == next(
        file for file in reviewed["files"] if file["path"] == "manifest.json"
    )
    assert result["id"] == manifest["id"]
    for change in (
        {"verified": False},
        {"hub_commit": "main"},
        {"community_disabled": False},
        {"release_sha256": "d" * 64},
        {"repo_id": "voxelshogi/other"},
    ):
        with pytest.raises(ValueError):
            catalog_release(folder, reviewed, verified | change)
    (folder / "README.md").write_text("changed")
    with pytest.raises(ValueError):
        catalog_release(folder, reviewed, verified)


def test_changed_package_is_stopped_before_api_calls(tmp_path):
    from training.tests.test_hub_release import Hub

    folder = tmp_path / "release"
    package(folder)
    reviewed, api = plan(folder), Hub()
    (folder / "reference/int8/initial-b-value.f32").write_bytes(b"changed")
    with pytest.raises(ValueError):
        publish_release(folder, reviewed, api, execute=True, system="linux")
    assert api.calls == []
