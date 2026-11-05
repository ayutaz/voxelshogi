"""Prepare exact published operator ONNX/full references for Linux browsers."""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

from export.research_contract import ARCHITECTURES, architecture_config, parameter_count
from training.evaluation_v2 import fingerprint
from training.feature_cache import file_hash
from training.hub_release import plan_release
from training.research_probe import _inputs, validate_probe


def _linux():
    if sys.platform != "linux":
        raise ValueError("research browser input preparation requires external Linux")


def prepare_inputs(folder, output, *, plan, receipt):
    _linux()
    import numpy as np
    from safetensors.numpy import load_file

    folder, output = Path(folder), Path(output)
    if (
        receipt.get("verified") is not True
        or receipt.get("dry_run") is not False
        or receipt.get("community_disabled") is not True
        or receipt.get("repo_id") != "voxelshogi/voxelshogi-research-operator-probe-v1"
        or receipt.get("repo_type") != "model"
        or re.fullmatch(r"[0-9a-f]{40}", receipt.get("hub_commit", "")) is None
        or receipt.get("release_sha256") != fingerprint(plan)
        or plan.get("repo_id") != receipt["repo_id"]
        or plan.get("repo_type") != "model"
        or plan_release(
            folder,
            repo_id=plan["repo_id"],
            repo_type="model",
            license_id="apache-2.0",
            license_approved=True,
            source_commit=plan["source_commit"],
        )
        != plan
    ):
        raise ValueError("verified fixed Hub release and exact local bytes required")
    protocol = json.loads((folder / "config.json").read_text())
    validate_probe(protocol)
    manifest = json.loads((folder / "manifest.json").read_text())
    report = manifest["probe_result"]
    if (
        manifest.get("schema") != "voxelshogi-research-operator-release-v1"
        or manifest.get("pipeline_complete") is not True
        or report.get("complete") is not True
        or manifest["source_commit"] != plan["source_commit"]
        or report["source_commit"] != plan["source_commit"]
        or manifest["protocol_sha256"] != fingerprint(protocol)
        or set(report["architectures"]) != set(ARCHITECTURES)
        or any(
            report["architectures"][name]["export"].get("passed") is not True
            for name in ARCHITECTURES
        )
    ):
        raise ValueError("all four successful published operator exports required")
    inputs = _inputs(protocol)
    models = []
    output.mkdir(parents=True, exist_ok=False)

    def describe(path):
        return {
            "path": path.relative_to(output).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": file_hash(path),
        }

    def tensor(path, values, shape):
        if (
            values.shape != shape
            or values.dtype != np.float32
            or not np.isfinite(values).all()
        ):
            raise ValueError("full reference shape/dtype/numeric differs")
        # Browser Float32Array expects little-endian IEEE754 bytes.
        path.write_bytes(np.asarray(values, dtype="<f4", order="C").tobytes(order="C"))
        return describe(path)

    for name in ARCHITECTURES:
        row = report["architectures"][name]
        parameters = parameter_count(architecture_config(name))
        if row["export"]["parameter_count"] != parameters:
            raise ValueError("published M parameter count differs")
        target = output / name
        target.mkdir()
        original = folder / name / "fp32.onnx"
        shutil.copyfile(original, target / "fp32.onnx")
        if file_hash(original) != file_hash(target / "fp32.onnx"):
            raise ValueError("browser ONNX copy changed bytes")
        refs = load_file(folder / name / "references.safetensors")
        expected_keys = {
            f"fixture{i}.{k}"
            for i in protocol["fixture_indices"]
            for k in ("features", "policy", "value")
        }
        if set(refs) != expected_keys:
            raise ValueError("exact frozen full references required")
        fixtures = []
        for index, features, legal in inputs:
            prefix = f"fixture{index}"
            if not np.array_equal(refs[prefix + ".features"], features[None]):
                raise ValueError(
                    "published reference input differs from frozen Rust fixture"
                )
            fixtures.append(
                {
                    "id": index,
                    "features": tensor(
                        target / (prefix + ".features.f32"),
                        refs[prefix + ".features"],
                        (1, 729, 43),
                    ),
                    "policy": tensor(
                        target / (prefix + ".policy.f32"),
                        refs[prefix + ".policy"],
                        (1, 1067985),
                    ),
                    "value": tensor(
                        target / (prefix + ".value.f32"),
                        refs[prefix + ".value"],
                        (1, 1),
                    ),
                    "legal_actions": legal,
                }
            )
        models.append(
            {
                "name": name,
                "parameters": parameters,
                "model": describe(target / "fp32.onnx"),
                "fixtures": fixtures,
            }
        )
    # Rehash the entire reviewed release after preparation, including weights.
    if (
        plan_release(
            folder,
            repo_id=plan["repo_id"],
            repo_type="model",
            license_id="apache-2.0",
            license_approved=True,
            source_commit=plan["source_commit"],
        )
        != plan
    ):
        raise ValueError("published source changed during browser preparation")
    result = {
        "schema": "voxelshogi-research-browser-input-v1",
        "trained": False,
        "model_source_commit": plan["source_commit"],
        "release_sha256": receipt["release_sha256"],
        "origin": {"repo_id": receipt["repo_id"], "revision": receipt["hub_commit"]},
        "numeric": protocol["numeric"],
        "warmup_steps": 8,
        "measured_steps": 32,
        "models": models,
        "scope": "Exact untrained operator ONNX bytes and full CUDA references; no game-strength, learned-model, display or physical-mobile evidence.",
    }
    (output / "browser-inputs.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    result = prepare_inputs(
        args.folder,
        args.output,
        plan=json.loads(args.plan.read_text()),
        receipt=json.loads(args.receipt.read_text()),
    )
    print(
        json.dumps(
            {
                "prepared_models": len(result["models"]),
                "fixed_revision": result["origin"]["revision"],
            }
        )
    )


if __name__ == "__main__":
    main()
