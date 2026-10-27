"""Generate immutable-by-hash model inputs, checkpoint and FP32 reference data."""

import argparse
import hashlib
import json
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


def generate(output, *, seed=SEED, license=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    model = make_model(seed)
    checkpoint = output / "model.safetensors"
    save_file(model.state_dict(), checkpoint)
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
            comparison[fixture["name"]][name] = compare_outputs(ref.numpy(), observed)
            references[fixture["name"]][name] = write_floats(
                output, f"reference/fp32/{fixture['name']}-{name}.f32", observed
            )
    sources = [
        "export/contract.py",
        "export/model.py",
        "export/generate.py",
        "export/fixtures/positions.json",
        "uv.lock",
    ]
    manifest = {
        "schema": 1,
        "id": f"voxelshogi-transformer-s-untrained-{seed}-v1",
        "trained": False,
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
        **source_context(),
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
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    validate_package(output)
    return manifest


def validate_package(root):
    root = Path(root).resolve()
    manifest = json.loads((root / "manifest.json").read_text())
    if manifest.get("schema") != 1 or manifest.get("inputSchema") != INPUT_SCHEMA:
        raise ValueError("unsupported manifest schema")
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
    args = parser.parse_args()
    manifest = generate(args.output, seed=args.seed, license=args.license)
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
