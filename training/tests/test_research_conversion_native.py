"""Linux tiny real graphs exercise the converter, not trained-M performance.

The graph carries a handwritten M-profile metadata fixture. Only the production
outer generator's strict selected-weight loader establishes a real M network.
No model, references or inference run from this module may execute on Mac.
"""

import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="external Linux only")


def test_real_three_formats_preserve_bound_metadata_references_and_legal_argmax(
    tmp_path,
):
    import numpy as np
    import onnx
    import torch
    from onnx import TensorProto
    from voxelshogi import Game

    from export.research_generate import _fixtures, _fp32, _variant
    from training.feature_cache import file_hash
    from training.research_onnx import _inspect, load_research_onnx_player
    from training.tests.test_research_weights import metadata

    torch.set_num_threads(1)

    class TinyGraph(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.weight = torch.nn.Parameter(
                torch.tensor([[1.001, 0.002], [-1.0, 0.75]], dtype=torch.float32)
            )

        def forward(self, features):
            pair = features.mean(dim=1)[:, :2] @ self.weight
            policy = (pair[:, :1] - pair[:, 1:]).expand(1, 1067985)
            value = pair.sum(dim=1, keepdim=True).tanh()
            return policy, value

    fixtures = _fixtures(tmp_path)
    assert [f["name"] for f in fixtures] == [
        "initial-b",
        "after-one-w",
        "mate-in-one-b",
        "material-b",
    ]
    binding = {
        "metadata": metadata(),
        "weights_sha256": "d" * 64,
        "export_source_commit": "e" * 40,
    }
    base = _fp32(TinyGraph().eval(), tmp_path, fixtures, binding)
    variants = [
        base,
        *[_variant(p, tmp_path, fixtures, base, binding) for p in ("fp16", "int8")],
    ]
    hashes = set()
    for variant in variants:
        path = tmp_path / variant["model"]["path"]
        hashes.add(file_hash(path))
        identity = _inspect(path)
        stored = [
            tensor.data_type
            for tensor in onnx.load(path).graph.initializer
            if len(tensor.dims) >= 2
        ]
        assert {
            "fp32": TensorProto.FLOAT,
            "fp16": TensorProto.FLOAT16,
            "int8": TensorProto.INT8,
        }[variant["precision"]] in stored
        assert identity["precision"] == variant["precision"]
        assert identity["weights_sha256"] == binding["weights_sha256"]
        assert identity["export_source_commit"] == "e" * 40
        if variant["precision"] != "fp32":
            assert identity["conversion"]["compute"] == "float32"
            assert set(variant["fp32Difference"]) == {f["name"] for f in fixtures}
        seen = []
        player = load_research_onnx_player(
            path,
            expected_sha256=file_hash(path),
            observe_input=lambda game: seen.append(game.record()),
        )
        game = Game.from_record(fixtures[0]["record"])
        assert player(game) == min(game.legal_actions())  # All policy logits tie.
        assert seen == [fixtures[0]["record"]]
        for fixture in fixtures:
            features = np.fromfile(
                tmp_path / fixture["input"]["path"], dtype="<f4"
            ).reshape(1, 729, 43)
            references = variant["references"][fixture["name"]]
            from training.research_onnx import _open

            actual = _open(path, variant["precision"]).run(
                ["policy", "value"], {"features": features}
            )
            for output, values in zip(("policy", "value"), actual, strict=True):
                descriptor = references[output]
                assert file_hash(tmp_path / descriptor["path"]) == descriptor["sha256"]
                expected = np.fromfile(
                    tmp_path / descriptor["path"], dtype="<f4"
                ).reshape(values.shape)
                np.testing.assert_array_equal(values, expected)
    assert len(hashes) == 3


def test_real_protobuf_rejects_external_tensors_in_nested_graph_before_loading_files(
    tmp_path,
):
    from onnx import TensorProto, helper

    from training.research_onnx import _external_data, _inspect

    tensor = helper.make_tensor("hidden", TensorProto.FLOAT, [1], [1.0])
    tensor.ClearField("float_data")
    tensor.data_location = TensorProto.EXTERNAL
    tensor.external_data.add(key="location", value="never-read.onnx.data")
    nested = helper.make_graph([], "nested", [], [], [tensor])
    node = helper.make_node(
        "If", ["condition"], ["out"], then_branch=nested, else_branch=nested
    )
    graph = helper.make_graph([node], "outer", [], [])
    model = helper.make_model(graph)
    assert _external_data(model) is True
    path = tmp_path / "nested.onnx"
    path.write_bytes(model.SerializeToString())
    with pytest.raises(ValueError, match="external tensors"):
        _inspect(path)
    assert not (tmp_path / "never-read.onnx.data").exists()
