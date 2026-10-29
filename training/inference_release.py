"""Explicit trained inference inventory and a catalog entry from verified bytes.

Pure metadata/hash checks only. The external generation/evaluation steps must
already have verified the actual models, reference shapes, and playing results.
"""

import hashlib
import json
import re
from pathlib import Path

from export.trained import validate_training_manifest

NAMES = ("initial-b", "after-one-w", "mate-in-one-b", "material-b")
PRECISIONS = ("fp32", "fp16", "int8")


def inference_inventory(folder, plan, card):
    folder = Path(folder)
    path = folder / "manifest.json"
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError("invalid inference manifest")
    try:
        manifest = json.loads(path.read_text())
        if (
            "ciFixture" in manifest
            or manifest["schema"] != 1
            or manifest["sourceDirty"] is not False
            or manifest["sourceCommit"] != plan["source_commit"]
            or manifest["license"].lower() != plan["license"]
        ):
            raise ValueError(
                "inference source/license or CI fixture is not publishable"
            )
        validate_training_manifest(manifest)
        for title in (
            "Training and provenance",
            "Evaluation",
            "Inference",
            "Access and license",
        ):
            section = re.search(
                rf"^## {re.escape(title)}[ \t]*\n(.*?)(?=^## |\Z)",
                card,
                re.MULTILINE | re.DOTALL,
            )
            if section is None or not section.group(1).strip():
                raise ValueError(f"Model Card requires a populated section: {title}")
        expected = {name: None for name in ("README.md", "LICENSE", "manifest.json")}
        if (folder / "NOTICE").exists():
            expected["NOTICE"] = None
        for name in ("README.md", "LICENSE", "NOTICE"):
            file = folder / name
            if file.exists() and (
                file.is_symlink() or file.stat().st_size > 1024 * 1024
            ):
                raise ValueError("invalid inference notice")

        def include(descriptor, wanted):
            if (
                set(descriptor) != {"path", "bytes", "sha256"}
                or descriptor["path"] != wanted
                or type(descriptor["bytes"]) is not int
                or not 0 < descriptor["bytes"] <= 64 * 1024 * 1024
                or not re.fullmatch(r"[0-9a-f]{64}", descriptor["sha256"])
            ):
                raise ValueError("invalid inference artifact descriptor")
            expected[wanted] = descriptor

        include(manifest["checkpoint"], "model.safetensors")
        fixtures, variants = manifest["fixtures"], manifest["variants"]
        if [entry["name"] for entry in fixtures] != list(NAMES) or [
            entry["precision"] for entry in variants
        ] != list(PRECISIONS):
            raise ValueError(
                "inference package requires all four fixtures and three formats"
            )
        for fixture in fixtures:
            include(fixture["input"], f"inputs/{fixture['name']}.f32")
        for variant in variants:
            precision = variant["precision"]
            if variant["id"] != precision or set(variant["references"]) != set(NAMES):
                raise ValueError("incomplete inference references")
            include(variant["model"], f"{precision}.onnx")
            for name in NAMES:
                references = variant["references"][name]
                if set(references) != {"policy", "value"}:
                    raise ValueError("invalid inference reference outputs")
                for output in ("policy", "value"):
                    include(
                        references[output], f"reference/{precision}/{name}-{output}.f32"
                    )
        for filename, key in (
            ("evaluation.json", "evaluation_report_sha256"),
            ("test.json", "test_report_sha256"),
        ):
            expected[filename] = {"sha256": manifest["training"][key]}
        return expected
    except (
        OSError,
        KeyError,
        TypeError,
        AttributeError,
        json.JSONDecodeError,
    ) as error:
        raise ValueError("incomplete inference package metadata") from error


def catalog_release(folder, plan, receipt):
    from training.hub_release import _canonical, plan_release

    if (
        plan.get("artifact_role") != "inference-package"
        or receipt.get("verified") is not True
        or receipt.get("community_disabled") is not True
        or receipt.get("dry_run") is not False
        or receipt.get("repo_id") != plan["repo_id"]
        or receipt.get("repo_type") != "model"
        or not re.fullmatch(r"[0-9a-f]{40}", receipt.get("hub_commit", ""))
        or receipt.get("release_sha256")
        != hashlib.sha256(_canonical(plan).encode()).hexdigest()
    ):
        raise ValueError("catalog requires a verified immutable inference release")
    current = plan_release(
        folder,
        repo_id=plan["repo_id"],
        repo_type=plan["repo_type"],
        license_id=plan["license"],
        license_approved=plan["license_approved"],
        source_commit=plan["source_commit"],
        artifact_role="inference-package",
    )
    if current != plan:
        raise ValueError("catalog artifacts changed since verified release")
    manifest = json.loads((Path(folder) / "manifest.json").read_text())
    files = {file["path"]: file for file in plan["files"]}
    return {
        "approved": True,
        "id": manifest["id"],
        "license": manifest["license"],
        "sourceCommit": plan["source_commit"],
        "repo": plan["repo_id"],
        "revision": receipt["hub_commit"],
        "manifest": files["manifest.json"],
        "notices": [
            files[name] for name in ("README.md", "LICENSE", "NOTICE") if name in files
        ],
    }
