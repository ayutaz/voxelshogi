"""Handwritten metadata and fake ORT ports; never decode a model on Mac."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from training.feature_cache import file_hash
from training.tests.test_research_weights import metadata


def converted(precision):
    if precision == "fp32":
        return None
    return {
        "method": "fp16-weight-only"
        if precision == "fp16"
        else "symmetric-per-tensor-weight-only-int8",
        "compute": "float32",
        "activations": "float32",
        **(
            {"convertedTensors": 2, "convertedElements": 32}
            if precision == "fp16"
            else {"quantizedTensors": 2, "quantizedElements": 32}
        ),
    }


def properties(precision="fp32", **kwargs):
    from training.research_onnx import onnx_properties

    return onnx_properties(
        metadata(),
        precision=precision,
        weights_sha256="d" * 64,
        export_source="e" * 40,
        conversion=converted(precision),
        **kwargs,
    )


@pytest.mark.parametrize("name", ["full", "axial", "geometry", "cnn"])
@pytest.mark.parametrize("precision", ["fp32", "fp16", "int8"])
def test_properties_bind_real_M_profile_selected_weights_format_and_export(
    name, precision
):
    from training.research_onnx import onnx_properties, review_properties

    value = onnx_properties(
        metadata(name),
        precision=precision,
        weights_sha256="d" * 64,
        export_source="e" * 40,
        conversion=converted(precision),
    )
    assert len(value) == 5
    assert review_properties(list(value.items())) == {
        "metadata": metadata(name),
        "precision": precision,
        "weights_sha256": "d" * 64,
        "export_source_commit": "e" * 40,
        "conversion": converted(precision),
    }


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "duplicate",
        "unknown-tag",
        "format",
        "weights",
        "source",
        "json",
        "duplicate-json",
        "unselected",
        "toy",
        "count",
        "oversize",
    ],
)
def test_ambiguous_unselected_or_unbound_ONNX_metadata_is_rejected(change):
    from training.research_onnx import review_properties

    values = properties("fp16")
    if change == "missing":
        values.pop("voxelshogi.precision")
    elif change == "duplicate":
        rows = list(values.items())
        with pytest.raises(ValueError):
            review_properties(rows + [rows[0]])
        return
    elif change == "unknown-tag":
        values["voxelshogi.other"] = "unexpected"
    elif change == "format":
        values = properties("int8")
        values["voxelshogi.precision"] = "fp64"
    elif change == "weights":
        values["voxelshogi.weights_sha256"] = "d" * 63
    elif change == "source":
        values["voxelshogi.export_source"] = "main"
    elif change == "json":
        values["voxelshogi.research"] = "not JSON"
    elif change == "duplicate-json":
        values["voxelshogi.research"] = values["voxelshogi.research"].replace(
            '"step":128', '"step":1,"step":128'
        )
    elif change in ("unselected", "toy"):
        m = metadata()
        if change == "unselected":
            m["checkpoint_role"] = "latest"
        else:
            m["architecture"]["width"] = 4
        values["voxelshogi.research"] = json.dumps(m)
    elif change == "count":
        values["voxelshogi.conversion"] = json.dumps(
            converted("fp16") | {"convertedTensors": 33}
        )
    else:
        values["other"] = "x" * 65537
    with pytest.raises(ValueError):
        review_properties(list(values.items()))


@pytest.mark.parametrize("precision", ["fp16", "int8"])
@pytest.mark.parametrize(
    "change", ["compute", "activations", "method", "tensors", "elements", "boolean"]
)
def test_half_and_int8_weights_cannot_claim_other_compute_or_fake_conversion_counts(
    precision, change
):
    from training.research_onnx import onnx_properties

    c = converted(precision)
    tensor_key, element_key = (
        ("convertedTensors", "convertedElements")
        if precision == "fp16"
        else ("quantizedTensors", "quantizedElements")
    )
    if change in ("compute", "activations"):
        c[change] = "float16"
    elif change == "method":
        c["method"] = "onnxconverter-common-float16"
    elif change == "tensors":
        c[tensor_key] = 0
    elif change == "elements":
        c[element_key] = 25_783_689
    else:
        c[tensor_key] = True
    with pytest.raises(ValueError):
        onnx_properties(
            metadata(),
            precision=precision,
            weights_sha256="d" * 64,
            export_source="e" * 40,
            conversion=c,
        )


def test_fp32_has_no_conversion_and_foreign_exporter_metadata_is_preserved():
    from training.research_onnx import onnx_properties, review_properties

    with pytest.raises(ValueError):
        onnx_properties(
            metadata(),
            precision="fp32",
            weights_sha256="d" * 64,
            export_source="e" * 40,
            conversion={},
        )
    values = properties()
    assert (
        review_properties([("producer", "torch-export"), *values.items()])["precision"]
        == "fp32"
    )


def fake_ports(path, *, providers=None, mutate=False):
    calls = []

    def inspect(file):
        calls.append(("inspect", str(file)))
        return {
            "metadata": metadata(),
            "precision": "int8",
            "weights_sha256": "d" * 64,
            "export_source_commit": "e" * 40,
            "conversion": converted("int8"),
        }

    def open_session(file, precision):
        calls.append(("open", str(file), precision))
        if mutate:
            path.write_bytes(b"changed bytes")
        return SimpleNamespace(
            get_providers=lambda: providers or ["CPUExecutionProvider"]
        )

    def student(file, precision, session):
        calls.append(("student", str(file), precision))
        return lambda game: 7

    return {"inspect": inspect, "open": open_session, "student": student}, calls


def test_loader_uses_exact_ONNX_bytes_and_actual_format_with_observation_and_stop(
    monkeypatch, tmp_path
):
    import training.research_onnx as module

    monkeypatch.setattr(module.sys, "platform", "linux")
    path = tmp_path / "model.onnx"
    path.write_bytes(b"opaque fake ONNX port bytes")
    ports, calls = fake_ports(path)
    observed, stop = [], [False]
    player = module.load_research_onnx_player(
        path,
        expected_sha256=file_hash(path),
        ports=ports,
        observe_input=observed.append,
        stop_requested=lambda: stop[0],
    )
    marker = object()
    assert player(marker) == 7 and observed == [marker]
    assert [row[0] for row in calls] == ["inspect", "open", "student"]
    assert calls[1][2] == calls[2][2] == "int8"
    assert player.binding["backend"] == "ort-cpu"
    assert player.binding["weights_sha256"] == "d" * 64
    stop[0] = True
    with pytest.raises(InterruptedError):
        player(marker)
    assert observed == [marker]


@pytest.mark.parametrize(
    "change", ["hash", "symlink", "extension", "provider", "mutation", "expired"]
)
def test_invalid_ORNX_or_wrong_provider_does_not_become_a_valid_player(
    monkeypatch, tmp_path, change
):
    import training.research_onnx as module

    monkeypatch.setattr(module.sys, "platform", "linux")
    path = tmp_path / "model.onnx"
    path.write_bytes(b"opaque fake port bytes")
    expected = file_hash(path)
    if change == "hash":
        expected = "f" * 64
    elif change == "symlink":
        linked = tmp_path / "linked.onnx"
        linked.symlink_to(path)
        path = linked
    elif change == "extension":
        moved = tmp_path / "model.safetensors"
        path.rename(moved)
        path = moved
    ports, calls = fake_ports(
        path,
        providers=["CUDAExecutionProvider"] if change == "provider" else None,
        mutate=change == "mutation",
    )
    with pytest.raises((ValueError, InterruptedError)):
        module.load_research_onnx_player(
            path,
            expected_sha256=expected,
            ports=ports,
            stop_requested=lambda: change == "expired",
        )
    if change in ("hash", "symlink", "extension", "expired"):
        assert calls == []
    assert not any(row[0] == "student" for row in calls)


def test_Mac_guard_precedes_all_numerical_imports_and_port_calls(monkeypatch, tmp_path):
    import training.research_onnx as module

    monkeypatch.setattr(module.sys, "platform", "darwin")
    monkeypatch.setitem(module.sys.modules, "onnx", None)
    monkeypatch.setitem(module.sys.modules, "torch", None)
    with pytest.raises(ValueError, match="external Linux"):
        module.load_research_onnx_player(
            tmp_path / "unused.onnx", expected_sha256="a" * 64
        )


def test_external_tensor_references_are_detected_inside_repeated_and_nested_graph_attributes():
    from training.research_onnx import _external_data

    tensor = SimpleNamespace(
        DESCRIPTOR=SimpleNamespace(full_name="onnx.TensorProto"),
        external_data=[],
        data_location=0,
    )

    def message(name, children):
        fields = [
            (SimpleNamespace(message_type=object(), is_repeated=repeated), value)
            for repeated, value in children
        ]
        return SimpleNamespace(
            DESCRIPTOR=SimpleNamespace(full_name=name), ListFields=lambda: fields
        )

    nested = message(
        "onnx.ModelProto",
        [
            (
                False,
                message(
                    "onnx.GraphProto",
                    [
                        (
                            True,
                            [
                                message(
                                    "onnx.NodeProto",
                                    [
                                        (
                                            True,
                                            [
                                                message(
                                                    "onnx.AttributeProto",
                                                    [
                                                        (
                                                            False,
                                                            message(
                                                                "onnx.GraphProto",
                                                                [(True, [tensor])],
                                                            ),
                                                        )
                                                    ],
                                                )
                                            ],
                                        )
                                    ],
                                )
                            ],
                        )
                    ],
                ),
            )
        ],
    )
    assert _external_data(nested) is False
    tensor.external_data = [{"key": "location", "value": "unpublished.onnx.data"}]
    assert _external_data(nested) is True
    tensor.external_data = []
    tensor.data_location = 1
    assert _external_data(nested) is True


def test_v2_runner_routes_M_ONNX_without_Torch_weights_or_a_precision_guess(
    monkeypatch, tmp_path
):
    import training.research_onnx as module
    from training.evaluation_v2_runner import _prepare_players, rust_policy_identity
    from training.tests.test_evaluation_v2 import protocol

    path = tmp_path / "candidate.onnx"
    path.write_bytes(b"opaque fake port ONNX")
    spec = deepcopy(protocol())
    spec["participants"]["model"] = {
        "policy": "legal-argmax-v1",
        "backend": "ort-cpu",
        "artifact_sha256": file_hash(path),
    }
    spec["participants"]["opponent"] = {
        "policy": "alphabeta-v1",
        "backend": "rust",
        "artifact_sha256": rust_policy_identity(
            "alphabeta-v1", spec["source_commit"], spec["search_limits"]
        ),
    }
    called = []

    def load(file, **kwargs):
        called.append((file, kwargs))
        return "fake explicit ONNX player"

    monkeypatch.setattr(module, "load_research_onnx_player", load)
    observed = []
    result = _prepare_players(
        spec,
        {"model": path},
        observe_input=lambda role, game: observed.append((role, game)),
    )
    assert result["model"] == "fake explicit ONNX player" and result["opponent"] is None
    assert called[0][0] == path and called[0][1]["expected_sha256"] == file_hash(path)
    called[0][1]["observe_input"]("fake game port")
    assert observed == [("model", "fake game port")]


@pytest.mark.parametrize(
    "change",
    [None, "external", "input-name", "output-name", "dtype", "shape", "symbolic"],
)
def test_graph_inspector_refuses_external_or_incompatible_IO_before_session_creation(
    monkeypatch, change
):
    import training.research_onnx as module

    def node(name, shape):
        dimensions = [SimpleNamespace(dim_value=n, dim_param="") for n in shape]
        return SimpleNamespace(
            name=name,
            type=SimpleNamespace(
                tensor_type=SimpleNamespace(
                    elem_type=1, shape=SimpleNamespace(dim=dimensions)
                )
            ),
        )

    graph = SimpleNamespace(
        input=[node("features", [1, 729, 43])],
        output=[node("policy", [1, 1067985]), node("value", [1, 1])],
    )
    if change == "input-name":
        graph.input[0].name = "other"
    elif change == "output-name":
        graph.output[0].name = "other"
    elif change == "dtype":
        graph.input[0].type.tensor_type.elem_type = 10
    elif change == "shape":
        graph.output[0].type.tensor_type.shape.dim[1].dim_value = 3
    elif change == "symbolic":
        graph.input[0].type.tensor_type.shape.dim[0].dim_param = "batch"
    model = SimpleNamespace(
        graph=graph,
        metadata_props=[
            SimpleNamespace(key=k, value=v) for k, v in properties().items()
        ],
    )
    reads, checks = [], []

    def load(path, **kwargs):
        reads.append((path, kwargs))
        return model

    fake = SimpleNamespace(
        load=load,
        TensorProto=SimpleNamespace(FLOAT=1),
        checker=SimpleNamespace(
            check_model=lambda *args, **kwargs: checks.append((args, kwargs))
        ),
    )
    monkeypatch.setitem(module.sys.modules, "onnx", fake)
    monkeypatch.setattr(module, "_external_data", lambda value: change == "external")
    if change is None:
        assert module._inspect("opaque-path-not-a-model")["precision"] == "fp32"
        assert checks[0][1] == {"full_check": True}
    else:
        with pytest.raises(ValueError):
            module._inspect("opaque-path-not-a-model")
        assert checks == []
    assert reads == [("opaque-path-not-a-model", {"load_external_data": False})]


def test_runtime_records_actual_ORT_version_without_labelling_it_CUDA(monkeypatch):
    import training.evaluation_v2_runner as runner
    from training.tests.test_evaluation_v2 import protocol

    fake = protocol()
    fake["participants"]["model"]["backend"] = "ort-cpu"
    monkeypatch.setitem(
        runner.sys.modules, "torch", SimpleNamespace(__version__="fake-torch-version")
    )
    monkeypatch.setitem(
        runner.sys.modules,
        "onnxruntime",
        SimpleNamespace(__version__="fake-ort-version"),
    )
    result = runner.execution_runtime(fake, {"model"}, "a" * 40)
    assert (
        result["onnxruntime"] == "fake-ort-version"
        and result["torch"] == "fake-torch-version"
    )
    assert "cuda" not in result and "gpu" not in result
