"""Explicit FP16 and weight-only INT8 transformations of the same ONNX graph."""

import copy

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper
from onnxconverter_common import float16


def symmetric_int8(values):
    values = np.asarray(values)
    if values.dtype != np.float32 or values.size == 0 or not np.isfinite(values).all():
        raise ValueError("weights must be nonempty finite float32")
    maximum = float(np.abs(values).max())
    scale = (
        np.float32(max(maximum / 127, np.finfo(np.float32).tiny))
        if maximum
        else np.float32(1)
    )
    quantized = np.rint(np.clip(values / scale, -127, 127)).astype(np.int8)
    return quantized, scale, np.int8(0)


def make_int8(source):
    graph = copy.deepcopy(source)
    initializers, nodes, tensors, elements = [], [], 0, 0
    for weight in graph.graph.initializer:
        if weight.data_type != TensorProto.FLOAT or len(weight.dims) < 2:
            initializers.append(weight)
            continue
        values = numpy_helper.to_array(weight)
        quantized, scale, zero = symmetric_int8(values)
        prefix = f"m3_int8__{weight.name}"
        initializers.extend(
            [
                numpy_helper.from_array(quantized, prefix + "__q"),
                numpy_helper.from_array(np.asarray(scale), prefix + "__scale"),
                numpy_helper.from_array(np.asarray(zero), prefix + "__zero"),
            ]
        )
        nodes.append(
            helper.make_node(
                "DequantizeLinear",
                [prefix + "__q", prefix + "__scale", prefix + "__zero"],
                [weight.name],
                name=prefix + "__dequantize",
            )
        )
        tensors += 1
        elements += values.size
    if tensors == 0:
        raise ValueError("no rank>=2 float32 weights to quantize")
    original_nodes = list(graph.graph.node)
    del graph.graph.node[:]
    graph.graph.node.extend([*nodes, *original_nodes])
    del graph.graph.initializer[:]
    graph.graph.initializer.extend(initializers)
    onnx.checker.check_model(graph)
    return graph, {
        "method": "symmetric-per-tensor-weight-only-int8",
        "range": [-127, 127],
        "zeroPoint": 0,
        "rounding": "ties-to-even",
        "minimumScale": float(np.finfo(np.float32).tiny),
        "activations": "float32",
        "compute": "float32",
        "quantizedTensors": tensors,
        "quantizedElements": elements,
    }


def make_fp16(source):
    graph = float16.convert_float_to_float16(
        copy.deepcopy(source),
        min_positive_val=2**-24,
        max_finite_val=65504,
        keep_io_types=True,
    )
    onnx.checker.check_model(graph)
    return graph, {
        "method": "onnxconverter-common-float16",
        "keepIoTypes": True,
        "minPositive": 2**-24,
        "maxFinite": 65504,
        "blockedOperators": list(float16.DEFAULT_OP_BLOCK_LIST),
        "initializerTypes": {
            str(kind): sum(i.data_type == kind for i in graph.graph.initializer)
            for kind in sorted({i.data_type for i in graph.graph.initializer})
        },
        "castNodes": sum(n.op_type == "Cast" for n in graph.graph.node),
    }
