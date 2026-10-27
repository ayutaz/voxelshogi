"""Hand-computable dependency/export probe, not the representative model test."""

import numpy as np
import onnx
import onnxruntime as ort
import torch


def test_python314_torch_dynamo_onnx_and_cpu_runtime_agree_with_hand_calculation(
    tmp_path,
):
    class Affine(torch.nn.Module):
        def forward(self, x):
            return 2 * x + 1

    path = tmp_path / "probe.onnx"
    torch.onnx.export(
        Affine().eval(),
        (torch.tensor([[-2.0, 0.0, 3.0]]),),
        path,
        dynamo=True,
        opset_version=18,
        input_names=["x"],
        output_names=["y"],
        external_data=False,
    )
    onnx.checker.check_model(onnx.load(path))
    session = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
    actual = session.run(["y"], {"x": np.array([[-2.0, 0.0, 3.0]], np.float32)})[0]
    np.testing.assert_array_equal(actual, [[-3.0, 1.0, 7.0]])
