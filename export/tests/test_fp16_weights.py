"""Hand-rounded constants; no representative model or training."""

import numpy as np
import onnx
import pytest
from onnx import TensorProto, helper, numpy_helper

from export import variants


def example(values):
    graph = helper.make_graph(
        [
            helper.make_node("MatMul", ["x", "w"], ["m"]),
            helper.make_node("Add", ["m", "b"], ["y"]),
        ],
        "fp16-storage-fp32-compute",
        [helper.make_tensor_value_info("x", TensorProto.FLOAT, [1, 1])],
        [helper.make_tensor_value_info("y", TensorProto.FLOAT, [1, 3])],
        [
            numpy_helper.from_array(np.array([values], np.float32), "w"),
            numpy_helper.from_array(np.array([1, 2, 3], np.float32), "b"),
        ],
    )
    return helper.make_model(
        graph, opset_imports=[helper.make_opsetid("", 18)], ir_version=10
    )


def test_fp16_storage_uses_half_weights_cast_to_float32_without_changing_bias_or_source():
    original = example([1.0006, -2.0006, 1e-9])
    before = original.SerializeToString()
    graph, settings = variants.make_fp16_weights(original)
    assert original.SerializeToString() == before
    onnx.checker.check_model(graph)
    weight = next(i for i in graph.graph.initializer if i.name != "b")
    assert weight.data_type == TensorProto.FLOAT16
    np.testing.assert_array_equal(
        numpy_helper.to_array(weight), [[1.0009765625, -2, 0]]
    )
    bias = next(i for i in graph.graph.initializer if i.name == "b")
    assert bias.data_type == TensorProto.FLOAT
    np.testing.assert_array_equal(numpy_helper.to_array(bias), [1, 2, 3])
    cast = graph.graph.node[0]
    assert cast.op_type == "Cast" and list(cast.output) == ["w"]
    assert helper.get_attribute_value(cast.attribute[0]) == TensorProto.FLOAT
    assert (
        settings["method"] == "fp16-weight-only"
        and settings["compute"] == settings["activations"] == "float32"
    )
    assert settings["convertedTensors"] == 1 and settings["convertedElements"] == 3


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), 70000])
def test_fp16_storage_rejects_nonfinite_or_overflow_instead_of_clipping(bad):
    with pytest.raises(ValueError):
        variants.make_fp16_weights(example([bad, 1, 2]))
