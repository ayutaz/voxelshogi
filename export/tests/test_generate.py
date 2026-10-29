import json

import numpy as np
import onnx
import onnxruntime as ort
import pytest
import torch

from export.contract import ACTIONS, compare_outputs
from export.generate import generate, validate_package
from export.model import make_model


@pytest.fixture(scope="module")
def package(tmp_path_factory):
    path = tmp_path_factory.mktemp("m3-fp32")
    generate(path)
    return path


def test_full_representative_export_matches_torch_for_all_four_fixed_inputs(package):
    manifest = validate_package(package)
    assert manifest["trained"] is False
    assert manifest["parameters"] == 5_021_064
    assert manifest["inputSchema"] == "voxelshogi-standard-features-v1"
    assert len(manifest["fixtures"]) == 4
    assert [f["side"] for f in manifest["fixtures"]][:2] == ["b", "w"]
    variant = manifest["variants"][0]
    assert variant["id"] == "fp32"
    graph = onnx.load(package / variant["model"]["path"])
    onnx.checker.check_model(graph)
    assert {"MatMul", "Softmax", "LayerNormalization"} <= {
        n.op_type for n in graph.graph.node
    }
    assert sum(n.op_type == "Softmax" for n in graph.graph.node) == 6
    session = ort.InferenceSession(
        package / variant["model"]["path"], providers=["CPUExecutionProvider"]
    )
    model = make_model()
    for fixture in manifest["fixtures"]:
        inputs = np.fromfile(package / fixture["input"]["path"], dtype="<f4").reshape(
            1, 729, 43
        )
        with torch.inference_mode():
            expected = [v.numpy() for v in model(torch.from_numpy(inputs.copy()))]
        actual = session.run(None, {"features": inputs})
        assert actual[0].shape == (1, ACTIONS)
        assert actual[1].shape == (1, 1)
        for name, ref, output in zip(
            ["policy", "value"], expected, actual, strict=True
        ):
            compare_outputs(ref, output)
            saved = np.fromfile(
                package / variant["references"][fixture["name"]][name]["path"],
                dtype="<f4",
            ).reshape(ref.shape)
            np.testing.assert_array_equal(saved, output)


def test_export_files_are_reproducible_in_the_same_environment(package, tmp_path):
    generate(tmp_path)
    first, second = validate_package(package), validate_package(tmp_path)
    assert first == second
    assert first["checkpoint"]["sha256"] == second["checkpoint"]["sha256"]
    assert (
        first["variants"][0]["model"]["sha256"]
        == second["variants"][0]["model"]["sha256"]
    )


def test_all_low_precision_variants_have_same_file_references_and_separate_fp32_differences(
    package,
):
    manifest = validate_package(package)
    assert [v["id"] for v in manifest["variants"]] == ["fp32", "fp16", "int8"]
    fp32_bytes = manifest["variants"][0]["model"]["bytes"]
    for variant in manifest["variants"][1:]:
        assert variant["model"]["bytes"] < fp32_bytes
        graph = onnx.load(package / variant["model"]["path"])
        onnx.checker.check_model(graph)
        options = ort.SessionOptions()
        options.graph_optimization_level = (
            ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
            if variant["id"] == "int8"
            else ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        )
        session = ort.InferenceSession(
            graph.SerializeToString(), options, providers=["CPUExecutionProvider"]
        )
        assert variant["referenceEngine"]["graphOptimization"] == (
            "basic" if variant["id"] == "int8" else "all"
        )
        assert len(variant["fp32Difference"]) == 4
        for fixture in manifest["fixtures"]:
            inputs = np.fromfile(
                package / fixture["input"]["path"], dtype="<f4"
            ).reshape(1, 729, 43)
            actual = session.run(["policy", "value"], {"features": inputs})
            for name, values in zip(["policy", "value"], actual, strict=True):
                saved = np.fromfile(
                    package / variant["references"][fixture["name"]][name]["path"],
                    dtype="<f4",
                ).reshape(values.shape)
                compare_outputs(saved, values, precision=variant["id"])
                assert values.size == (ACTIONS if name == "policy" else 1)
                assert np.isfinite(values).all()
                stats = variant["fp32Difference"][fixture["name"]][name]
                assert stats["elements"] == values.size
                assert stats["maxAbs"] >= stats["mae"] >= 0
                assert stats["rmse"] >= 0
        assert any(
            v["policy"]["maxAbs"] > 0 for v in variant["fp32Difference"].values()
        )


def test_manifest_and_hash_validation_rejects_changed_files(package, tmp_path):
    import shutil

    shutil.copytree(package, tmp_path / "copy")
    copy = tmp_path / "copy"
    manifest = validate_package(copy)
    file = copy / manifest["fixtures"][0]["input"]["path"]
    original = file.read_bytes()
    file.write_bytes(bytes([original[0] ^ 1]) + original[1:])
    with pytest.raises(ValueError, match="hash"):
        validate_package(copy)
    file.write_bytes(original)
    manifest["variants"][0]["model"]["path"] = "../escape.onnx"
    (copy / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="path"):
        validate_package(copy)


@pytest.mark.parametrize(
    "field",
    [
        "shape",
        "duplicate",
        "empty-variants",
        "dtype",
        "variant-precision",
        "missing-difference",
        "nonfinite-difference",
        "unproven-trained",
    ],
)
def test_corrupt_manifest_contract_is_rejected(package, tmp_path, field):
    import shutil

    shutil.copytree(package, tmp_path / "copy")
    copy = tmp_path / "copy"
    manifest = json.loads((copy / "manifest.json").read_text())
    if field == "shape":
        manifest["outputs"]["policy"]["shape"] = [1, 1]
    elif field == "duplicate":
        manifest["fixtures"].append(manifest["fixtures"][0])
    elif field == "empty-variants":
        manifest["variants"] = []
    elif field == "dtype":
        manifest["inputs"]["features"]["dtype"] = "float16"
    elif field == "variant-precision":
        manifest["variants"][1]["precision"] = "fp32"
    elif field == "missing-difference":
        del manifest["variants"][1]["fp32Difference"]
    elif field == "unproven-trained":
        manifest["trained"] = True
    else:
        manifest["variants"][1]["fp32Difference"]["initial-b"]["policy"]["rmse"] = (
            float("nan")
        )
    (copy / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        validate_package(copy)
