import numpy as np
import onnx
import onnxruntime as ort
import pytest
from onnx import TensorProto, helper, numpy_helper

from export.variants import make_fp16, make_int8, symmetric_int8


def toy():
    # max(abs(w))=127, so scale=1 and ties have hand-calculated answers.
    weights = np.array([[-127, -1.5, -0.5], [0.5, 1.5, 127]], dtype=np.float32)
    graph = helper.make_graph(
        [
            helper.make_node("MatMul", ["x", "w"], ["m"]),
            helper.make_node("Add", ["m", "bias"], ["y"]),
        ],
        "independent-quantization-example",
        [helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 2])],
        [helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 3])],
        [
            numpy_helper.from_array(weights, "w"),
            numpy_helper.from_array(np.array([1, 2, 3], np.float32), "bias"),
        ],
    )
    return helper.make_model(
        graph, opset_imports=[helper.make_opsetid("", 18)], ir_version=10
    )


def test_symmetric_int8_uses_signed_range_zero_point_and_ties_to_even():
    quantized, scale, zero = symmetric_int8(
        np.array([[-127, -1.5, -0.5], [0.5, 1.5, 127]], dtype=np.float32)
    )
    np.testing.assert_array_equal(quantized, [[-127, -2, 0], [0, 2, 127]])
    assert quantized.dtype == np.int8
    assert scale.dtype == np.float32 and scale == 1
    assert zero.dtype == np.int8 and zero == 0
    q, s, z = symmetric_int8(np.zeros((2, 3), np.float32))
    np.testing.assert_array_equal(q, np.zeros((2, 3), np.int8))
    assert s == 1 and z == 0
    q, s, z = symmetric_int8(np.array([[-254, 127]], np.float32))
    np.testing.assert_array_equal(q, [[-127, 64]])
    assert s == 2 and z == 0


@pytest.mark.parametrize(
    "value",
    [
        np.array([[np.nan]], np.float32),
        np.array([[np.inf]], np.float32),
        np.empty((0, 2), np.float32),
        np.ones((2, 2), np.int32),
    ],
)
def test_quantizer_rejects_invalid_weights(value):
    with pytest.raises(ValueError):
        symmetric_int8(value)


def test_int8_graph_executes_dequantized_weights_but_retains_bias_and_source():
    original = toy()
    before = original.SerializeToString()
    graph, settings = make_int8(original)
    assert original.SerializeToString() == before
    onnx.checker.check_model(graph)
    assert settings["quantizedTensors"] == 1
    assert settings["quantizedElements"] == 6
    assert any(n.op_type == "DequantizeLinear" for n in graph.graph.node)
    bias = next(i for i in graph.graph.initializer if i.name == "bias")
    np.testing.assert_array_equal(numpy_helper.to_array(bias), [1, 2, 3])
    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
    session = ort.InferenceSession(
        graph.SerializeToString(), options, providers=["CPUExecutionProvider"]
    )
    # [1,2] @ [[-127,-2,0],[0,2,127]] + [1,2,3]
    actual = session.run(None, {"x": np.array([[1, 2]], np.float32)})[0]
    np.testing.assert_array_equal(actual, [[-126, 4, 257]])


def test_fp16_conversion_keeps_public_io_float32_and_converts_real_weights():
    original = toy()
    graph, settings = make_fp16(original)
    onnx.checker.check_model(graph)
    assert all(
        v.type.tensor_type.elem_type == TensorProto.FLOAT
        for v in [*graph.graph.input, *graph.graph.output]
    )
    assert (
        next(i for i in graph.graph.initializer if i.name == "w").data_type
        == TensorProto.FLOAT16
    )
    assert settings["keepIoTypes"] is True
    assert settings["minPositive"] == 2**-24
    assert settings["maxFinite"] == 65504
