"""Generate checkpoint, FP32/FP16/INT8 models and per-format references."""

import argparse
import hashlib
import json
import math
import platform
import re
import subprocess
from importlib.metadata import version
from pathlib import Path, PurePosixPath

import numpy as np
import onnx
import onnxruntime as ort
import torch
from safetensors.torch import save_file

from export.contract import (
    ACTIONS,
    FEATURES,
    INPUT_SCHEMA,
    compare_outputs,
    encode_position,
)
from export.model import CONFIG, SEED, make_model
from export.numeric import TRAINED_NUMERIC_CONTRACT
from export.variants import make_fp16, make_fp16_weights, make_int8

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def descriptor(root, path):
    return {
        "path": str(path.relative_to(root)),
        "bytes": path.stat().st_size,
        "sha256": digest(path),
    }


def write_floats(root, name, values):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    np.asarray(values, dtype="<f4").tofile(path)
    return descriptor(root, path)


def output_difference(reference, actual):
    if (
        reference.shape != actual.shape
        or reference.size == 0
        or not np.isfinite(reference).all()
        or not np.isfinite(actual).all()
    ):
        raise ValueError("invalid low-precision comparison")
    delta = actual.astype(np.float64) - reference.astype(np.float64)
    return {
        "elements": int(delta.size),
        "maxAbs": float(np.abs(delta).max()),
        "mae": float(np.abs(delta).mean()),
        "rmse": float(np.sqrt(np.square(delta).mean())),
        "maxRelative": float(
            (
                np.abs(delta) / np.maximum(np.abs(reference), np.finfo(np.float32).tiny)
            ).max()
        ),
        "argmaxEqual": bool(reference.argmax() == actual.argmax()),
    }


def low_precision_variant(
    root, source, fixtures, fp32_references, precision, converter
):
    graph, settings = converter(source)
    path = root / f"{precision}.onnx"
    onnx.save(graph, path)
    options = ort.SessionOptions()
    options.intra_op_num_threads = options.inter_op_num_threads = 1
    options.graph_optimization_level = (
        ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
        if precision == "int8"
        else ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    )
    session = ort.InferenceSession(path, options, providers=["CPUExecutionProvider"])
    references, differences = {}, {}
    for fixture in fixtures:
        name = fixture["name"]
        values = np.fromfile(root / fixture["input"]["path"], dtype="<f4").reshape(
            1, 729, FEATURES
        )
        actual = session.run(["policy", "value"], {"features": values})
        references[name], differences[name] = {}, {}
        for output_name, output in zip(["policy", "value"], actual, strict=True):
            expected_shape = (1, ACTIONS) if output_name == "policy" else (1, 1)
            if (
                output.shape != expected_shape
                or output.dtype != np.float32
                or not np.isfinite(output).all()
            ):
                raise ValueError("invalid converted output shape/dtype/finite")
            base = np.fromfile(
                root / fp32_references[name][output_name]["path"], dtype="<f4"
            ).reshape(expected_shape)
            references[name][output_name] = write_floats(
                root, f"reference/{precision}/{name}-{output_name}.f32", output
            )
            differences[name][output_name] = output_difference(base, output)
    return {
        "id": precision,
        "precision": precision,
        "model": descriptor(root, path),
        "opset": 18,
        "operators": sorted(
            {(n.domain + ":" if n.domain else "") + n.op_type for n in graph.graph.node}
        ),
        "conversion": settings,
        "references": references,
        "fp32Difference": differences,
        "referenceEngine": {
            "name": "onnxruntime",
            "version": ort.__version__,
            "provider": "CPUExecutionProvider",
            "graphOptimization": "basic" if precision == "int8" else "all",
        },
    }


def source_context():
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
        dirty = bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"],
                cwd=ROOT,
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        )
        return {"sourceCommit": commit, "sourceDirty": dirty}
    except subprocess.CalledProcessError:
        # Isolated mutation/source copies are deliberately not release builds.
        return {"sourceCommit": None, "sourceDirty": True}


def generate(
    output,
    *,
    seed=SEED,
    license=None,
    selected_evaluation=None,
    training_source_commit=None,
    fp16_weights_only=False,
):
    output = Path(output)
    if selected_evaluation is not None and output.exists():
        raise FileExistsError("trained conversion requires a new output directory")
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    context = source_context()
    if selected_evaluation is None and (
        training_source_commit is not None or fp16_weights_only
    ):
        raise ValueError(
            "portable FP16/explicit lineage requires a selected trained evaluation"
        )
    review = None
    if selected_evaluation is not None:
        from export.trained import load_evaluated_weights

        state, review = load_evaluated_weights(
            selected_evaluation,
            context={
                **context,
                **(
                    {"trainingSourceCommit": training_source_commit}
                    if training_source_commit is not None
                    else {}
                ),
            },
            seed=seed,
        )
    model = make_model(seed)
    if review is not None:
        model.load_state_dict(state, strict=True)
    output.mkdir(parents=True, exist_ok=selected_evaluation is None)
    checkpoint = output / "model.safetensors"
    save_file(model.state_dict(), checkpoint)
    if review is not None and digest(checkpoint) != review["weights"]["sha256"]:
        raise ValueError("converted checkpoint differs from evaluated weight bytes")
    positions = json.loads((ROOT / "export/fixtures/positions.json").read_text())
    fixtures = []
    for position in positions:
        values = encode_position(position["board"], position["hands"], position["side"])
        fixtures.append(
            {
                "name": position["name"],
                "side": position["side"],
                "record": position["record"],
                "input": write_floats(output, f"inputs/{position['name']}.f32", values),
            }
        )
    sample = torch.from_numpy(
        encode_position(
            positions[0]["board"], positions[0]["hands"], positions[0]["side"]
        )
    )
    path = output / "fp32.onnx"
    torch.onnx.export(
        model,
        (sample,),
        path,
        dynamo=True,
        opset_version=18,
        external_data=False,
        input_names=["features"],
        output_names=["policy", "value"],
    )
    graph = onnx.load(path)
    onnx.checker.check_model(graph)
    options = ort.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(path, options, providers=["CPUExecutionProvider"])
    references, comparison = {}, {}
    for fixture in fixtures:
        values = np.fromfile(output / fixture["input"]["path"], dtype="<f4").reshape(
            1, 729, FEATURES
        )
        actual = session.run(["policy", "value"], {"features": values})
        with torch.inference_mode():
            expected = model(torch.from_numpy(values.copy()))
        references[fixture["name"]], comparison[fixture["name"]] = {}, {}
        for name, ref, observed in zip(
            ["policy", "value"], expected, actual, strict=True
        ):
            comparison[fixture["name"]][name] = compare_outputs(
                ref.numpy(),
                observed,
                output=name,
                numeric_contract=TRAINED_NUMERIC_CONTRACT if review else None,
            )
            references[fixture["name"]][name] = write_floats(
                output, f"reference/fp32/{fixture['name']}-{name}.f32", observed
            )
    sources = [
        "export/contract.py",
        "export/numeric.py",
        "export/model.py",
        "export/generate.py",
        "export/variants.py",
        "export/trained.py",
        "export/fixtures/positions.json",
        "uv.lock",
    ]
    manifest = {
        "schema": 1,
        "id": review["model_id"]
        if review
        else f"voxelshogi-transformer-s-untrained-{seed}-v1",
        "trained": review is not None,
        **({"numericContract": TRAINED_NUMERIC_CONTRACT} if review else {}),
        "license": license,
        "inputSchema": INPUT_SCHEMA,
        "seed": seed,
        "ruleset": "voxelshogi-standard-v1",
        "config": CONFIG,
        "parameters": sum(p.numel() for p in model.parameters()),
        "inputs": {"features": {"shape": [1, 729, FEATURES], "dtype": "float32"}},
        "outputs": {
            "policy": {"shape": [1, ACTIONS], "dtype": "float32"},
            "value": {"shape": [1, 1], "dtype": "float32"},
        },
        "sourceFiles": {name: digest(ROOT / name) for name in sources},
        **context,
        "environment": {
            "python": platform.python_version(),
            "system": platform.system(),
            "machine": platform.machine(),
            "packages": {
                name: version(name)
                for name in [
                    "torch",
                    "onnx",
                    "onnxruntime",
                    "numpy",
                    "onnxscript",
                    "safetensors",
                    "onnxconverter-common",
                ]
            },
        },
        "checkpoint": descriptor(output, checkpoint),
        "fixtures": fixtures,
        "variants": [
            {
                "id": "fp32",
                "precision": "fp32",
                "model": descriptor(output, path),
                "opset": 18,
                "operators": sorted(
                    {
                        (n.domain + ":" if n.domain else "") + n.op_type
                        for n in graph.graph.node
                    }
                ),
                "references": references,
                "torchComparison": comparison,
            }
        ],
    }
    if review is not None:
        manifest["training"] = review["training"]
    manifest["variants"].extend(
        [
            low_precision_variant(
                output,
                graph,
                fixtures,
                references,
                "fp16",
                make_fp16_weights if fp16_weights_only else make_fp16,
            ),
            low_precision_variant(
                output, graph, fixtures, references, "int8", make_int8
            ),
        ]
    )
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    validate_package(output)
    return manifest


def validate_package(root):
    root = Path(root).resolve()
    manifest = json.loads((root / "manifest.json").read_text())
    if manifest.get("schema") != 1 or manifest.get("inputSchema") != INPUT_SCHEMA:
        raise ValueError("unsupported manifest schema")
    if type(manifest.get("trained")) is not bool:
        raise ValueError("manifest must declare trained status")
    if manifest["trained"]:
        if "training" not in manifest:
            raise ValueError(
                "trained manifest requires selection/evaluation provenance"
            )
        from export.trained import validate_training_manifest

        validate_training_manifest(manifest)
    elif "training" in manifest or "numericContract" in manifest:
        raise ValueError("untrained manifest must not contain trained provenance")
    if not manifest.get("fixtures") or not manifest.get("variants"):
        raise ValueError("manifest must contain fixtures and variants")
    if manifest.get("inputs") != {
        "features": {"shape": [1, 729, FEATURES], "dtype": "float32"}
    }:
        raise ValueError("input shape/dtype mismatch")
    if manifest.get("outputs") != {
        "policy": {"shape": [1, ACTIONS], "dtype": "float32"},
        "value": {"shape": [1, 1], "dtype": "float32"},
    }:
        raise ValueError("output shape/dtype mismatch")
    names = [f["name"] for f in manifest["fixtures"]]
    if len(set(names)) != len(names) or any(
        not re.fullmatch(r"[a-z0-9-]+", name) for name in names
    ):
        raise ValueError("duplicate or invalid fixture name")
    ids = [v["id"] for v in manifest["variants"]]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate variant")
    if any(f["input"]["bytes"] != 1 * 729 * FEATURES * 4 for f in manifest["fixtures"]):
        raise ValueError("input byte length mismatch")
    files = [manifest["checkpoint"]] + [f["input"] for f in manifest["fixtures"]]
    for variant in manifest["variants"]:
        if (
            variant.get("id") not in {"fp32", "fp16", "int8"}
            or variant.get("precision") != variant["id"]
            or variant.get("opset") != 18
        ):
            raise ValueError("unsupported or inconsistent variant precision")
        if variant["id"] != "fp32":
            differences = variant.get("fp32Difference")
            if not isinstance(differences, dict) or set(differences) != set(names):
                raise ValueError("missing FP32 differences")
            for outputs in differences.values():
                if not isinstance(outputs, dict) or set(outputs) != {"policy", "value"}:
                    raise ValueError("missing FP32 difference outputs")
                for name, stats in outputs.items():
                    expected = ACTIONS if name == "policy" else 1
                    if (
                        not isinstance(stats, dict)
                        or type(stats.get("elements")) is not int
                        or stats["elements"] != expected
                        or type(stats.get("argmaxEqual")) is not bool
                    ):
                        raise ValueError("invalid FP32 difference count")
                    if any(
                        type(stats.get(key)) not in (int, float)
                        or not math.isfinite(stats[key])
                        or stats[key] < 0
                        for key in ["maxAbs", "mae", "rmse", "maxRelative"]
                    ):
                        raise ValueError("invalid FP32 difference statistic")
        files.append(variant["model"])
        if set(variant["references"]) != {f["name"] for f in manifest["fixtures"]}:
            raise ValueError("missing fixture references")
        for outputs in variant["references"].values():
            if set(outputs) != {"policy", "value"}:
                raise ValueError("missing outputs")
            if (
                outputs["policy"]["bytes"] != ACTIONS * 4
                or outputs["value"]["bytes"] != 4
            ):
                raise ValueError("output byte length mismatch")
            files.extend(outputs.values())
    for file in files:
        relative = file.get("path", "")
        if not isinstance(relative, str) or not re.fullmatch(
            r"[a-zA-Z0-9_./-]+", relative
        ):
            raise ValueError("invalid file path")
        parts = PurePosixPath(relative)
        path = (root / relative).resolve()
        if parts.is_absolute() or ".." in parts.parts or not path.is_relative_to(root):
            raise ValueError("file path escapes package")
        if (
            not path.is_file()
            or path.stat().st_size != file.get("bytes")
            or digest(path) != file.get("sha256")
        ):
            raise ValueError(f"file size/hash mismatch: {relative}")
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--license", choices=["Apache-2.0"])
    parser.add_argument("--selected-evaluation", type=Path)
    parser.add_argument("--training-source-commit")
    parser.add_argument("--fp16-weights-only", action="store_true")
    args = parser.parse_args()
    manifest = generate(
        args.output,
        seed=args.seed,
        license=args.license,
        selected_evaluation=args.selected_evaluation,
        training_source_commit=args.training_source_commit,
        fp16_weights_only=args.fp16_weights_only,
    )
    print(
        json.dumps(
            {
                "id": manifest["id"],
                "parameters": manifest["parameters"],
                "model": manifest["variants"][0]["model"],
                "manifestSha256": digest(args.output / "manifest.json"),
            }
        )
    )


if __name__ == "__main__":
    main()
