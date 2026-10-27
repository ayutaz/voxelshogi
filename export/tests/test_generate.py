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


@pytest.mark.parametrize("field", ["shape", "duplicate", "empty-variants", "dtype"])
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
    else:
        manifest["inputs"]["features"]["dtype"] = "float16"
    (copy / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        validate_package(copy)
