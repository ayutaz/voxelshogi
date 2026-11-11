"""Hash-bound trained-M ONNX formats for Linux evaluation, not Web publication."""

import json
import re
import sys
from pathlib import Path

from export.research_contract import ResearchConfig, parameter_count
from training.feature_cache import file_hash
from training.research_weights import validate_metadata

KEYS = {
    "voxelshogi.research",
    "voxelshogi.precision",
    "voxelshogi.weights_sha256",
    "voxelshogi.export_source",
    "voxelshogi.conversion",
}
MAX_MODEL_BYTES = 512 * 1024**2


def _hash(value, length=64):
    return (
        isinstance(value, str)
        and re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is not None
    )


def onnx_properties(metadata, *, precision, weights_sha256, export_source, conversion):
    metadata = validate_metadata(metadata)
    if (
        metadata["checkpoint_role"] != "best"
        or precision not in ("fp32", "fp16", "int8")
        or not _hash(weights_sha256)
        or not _hash(export_source, 40)
    ):
        raise ValueError("ONNX requires selected M weights and immutable format/source")
    if precision == "fp32":
        if conversion is not None:
            raise ValueError("FP32 is the unconverted reference")
    else:
        tensors, elements = (
            ("convertedTensors", "convertedElements")
            if precision == "fp16"
            else ("quantizedTensors", "quantizedElements")
        )
        if (
            type(conversion) is not dict
            or conversion.get("method")
            != (
                "fp16-weight-only"
                if precision == "fp16"
                else "symmetric-per-tensor-weight-only-int8"
            )
            or conversion.get("compute") != "float32"
            or conversion.get("activations") != "float32"
            or type(conversion.get(tensors)) is not int
            or type(conversion.get(elements)) is not int
            or not 1 <= conversion[tensors] <= conversion[elements]
            or conversion[elements]
            > parameter_count(ResearchConfig(**metadata["architecture"]))
        ):
            raise ValueError(
                "ONNX format needs actual FP32-compute weight-only conversion"
            )
    return {
        "voxelshogi.research": json.dumps(
            metadata, sort_keys=True, separators=(",", ":"), allow_nan=False
        ),
        "voxelshogi.precision": precision,
        "voxelshogi.weights_sha256": weights_sha256,
        "voxelshogi.export_source": export_source,
        "voxelshogi.conversion": json.dumps(
            conversion, sort_keys=True, separators=(",", ":"), allow_nan=False
        ),
    }


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate ONNX JSON property")
        result[key] = value
    return result


def review_properties(pairs):
    try:
        if not isinstance(pairs, (tuple, list)) or not 1 <= len(pairs) <= 256:
            raise ValueError("bounded ONNX properties required")
        values, size = {}, 0
        for key, value in pairs:
            if not isinstance(key, str) or not isinstance(value, str) or key in values:
                raise ValueError("invalid or duplicate ONNX property")
            size += len(key.encode()) + len(value.encode())
            values[key] = value
        if (
            size > 65536
            or {key for key in values if key.startswith("voxelshogi.")} != KEYS
        ):
            raise ValueError("incomplete or oversized M ONNX properties")
        metadata = json.loads(values["voxelshogi.research"], object_pairs_hook=_unique)
        conversion = json.loads(
            values["voxelshogi.conversion"], object_pairs_hook=_unique
        )
        actual = onnx_properties(
            metadata,
            precision=values["voxelshogi.precision"],
            weights_sha256=values["voxelshogi.weights_sha256"],
            export_source=values["voxelshogi.export_source"],
            conversion=conversion,
        )
        # Compare parsed values, accepting JSON whitespace but no duplicate keys.
        return {
            "metadata": json.loads(actual["voxelshogi.research"]),
            "precision": actual["voxelshogi.precision"],
            "weights_sha256": actual["voxelshogi.weights_sha256"],
            "export_source_commit": actual["voxelshogi.export_source"],
            "conversion": json.loads(actual["voxelshogi.conversion"]),
        }
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("invalid trained M ONNX properties") from error


def _external_data(message):
    """Walk protobuf messages, including tensors inside graph attributes."""
    if message.DESCRIPTOR.full_name == "onnx.TensorProto":
        return bool(message.external_data) or message.data_location != 0
    for field, value in message.ListFields():
        if field.message_type is not None:
            children = value if field.is_repeated else [value]
            if any(_external_data(child) for child in children):
                return True
    return False


def _inspect(path):
    import onnx

    from training.supervision import ACTIONS

    model = onnx.load(str(path), load_external_data=False)
    if _external_data(model):
        raise ValueError("M ONNX must be one hash-bound file without external tensors")
    for nodes, shapes in (
        (model.graph.input, {"features": [1, 729, 43]}),
        (model.graph.output, {"policy": [1, ACTIONS], "value": [1, 1]}),
    ):
        if [node.name for node in nodes] != list(shapes):
            raise ValueError("M ONNX input/output names differ")
        for node in nodes:
            tensor = node.type.tensor_type
            if (
                tensor.elem_type != onnx.TensorProto.FLOAT
                or [dim.dim_value for dim in tensor.shape.dim] != shapes[node.name]
                or any(dim.dim_param for dim in tensor.shape.dim)
            ):
                raise ValueError("M ONNX requires fixed batch1 FP32 input/output")
    onnx.checker.check_model(model, full_check=True)
    return review_properties([(item.key, item.value) for item in model.metadata_props])


def _open(path, precision):
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.intra_op_num_threads = options.inter_op_num_threads = 1
    options.graph_optimization_level = (
        ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
        if precision == "int8"
        else ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    )
    return ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])


def _student(path, precision, session):
    from training.students import TorchStudent, make_ort_model

    return TorchStudent(
        make_ort_model(str(path), precision=precision, session=session), device="cpu"
    )


def load_research_onnx_player(
    path,
    *,
    expected_sha256,
    stop_requested=lambda: False,
    observe_input=None,
    ports=None,
):
    if sys.platform != "linux":
        raise ValueError("M ONNX evaluation requires external Linux")
    if stop_requested():
        raise InterruptedError("M ONNX initialization interrupted")
    path = Path(path)
    if (
        not _hash(expected_sha256)
        or path.is_symlink()
        or not path.is_file()
        or path.suffix != ".onnx"
        or not 0 < path.stat().st_size <= MAX_MODEL_BYTES
        or file_hash(path) != expected_sha256
    ):
        raise ValueError("M ONNX format/bytes/hash differ")
    ports = (
        {"inspect": _inspect, "open": _open, "student": _student}
        if ports is None
        else ports
    )
    if set(ports) != {"inspect", "open", "student"}:
        raise ValueError("complete explicit ONNX ports required")
    binding = ports["inspect"](path)
    if stop_requested():
        raise InterruptedError("M ONNX inspection interrupted")
    session = ports["open"](path, binding["precision"])
    if session.get_providers() != ["CPUExecutionProvider"]:
        raise ValueError("explicit ORT CPU provider required; no backend fallback")
    if file_hash(path) != expected_sha256:
        raise ValueError("M ONNX changed during session initialization")
    if stop_requested():
        raise InterruptedError("M ONNX session initialization interrupted")
    student = ports["student"](path, binding["precision"], session)

    def choose(game):
        if stop_requested():
            raise InterruptedError("M ONNX evaluation interrupted")
        if observe_input is not None:
            observe_input(game)
        return student(game)

    choose.binding = {
        **binding,
        "artifact_sha256": expected_sha256,
        "backend": "ort-cpu",
    }
    return choose
