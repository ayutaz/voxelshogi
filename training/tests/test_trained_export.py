"""Linux-only conversion of altered fixture weights, not evidence of learning."""


def test_evaluated_weight_bytes_survive_all_three_conversions(tmp_path, monkeypatch):
    import copy
    import json
    import math

    import numpy as np
    import onnxruntime as ort
    import pytest
    import torch
    from safetensors.torch import save_file

    from export import generate as generator
    from export import trained
    from export.contract import compare_outputs
    from export.generate import validate_package
    from export.model import make_model
    from export.trained import export_evaluated
    from training.tests.test_trained_metadata import fixture

    # Independent value oracle: zero final matrix and bias=0.5 => tanh(0.5).
    model = make_model()
    with torch.no_grad():
        model.value[2].weight.zero_()
        model.value[2].bias.fill_(0.5)

    def weights_writer(path):
        save_file(model.state_dict(), path)

    # Synthetic source metadata isolates weight loading from Git cleanliness.
    # Dirty-source rejection is separately checked by the pure metadata tests.
    source = {"sourceCommit": "a" * 40, "sourceDirty": False}
    monkeypatch.setattr(generator, "source_context", lambda: source)
    evaluated = fixture(
        tmp_path / "evaluated",
        source_commit=source["sourceCommit"],
        weights_writer=weights_writer,
    )
    replays = []
    monkeypatch.setattr(
        trained, "verify_evaluation_games", lambda path: replays.append(path)
    )
    output = tmp_path / "converted"
    manifest = export_evaluated(evaluated, output)
    assert replays == [evaluated]
    assert manifest["trained"] is True and manifest["license"] is None
    assert manifest["numericContract"] == "voxelshogi-trained-numeric-v1"
    for row in manifest["variants"][0]["torchComparison"].values():
        assert row["policy"]["atol"] == 0.0001 and row["policy"]["rtol"] == 0.0001
        assert row["value"]["atol"] == 0.00001 and row["value"]["rtol"] == 0.0001
    assert manifest["id"] == "voxelshogi-transformer-s-m6-314159-v1"
    assert (
        manifest["checkpoint"]["sha256"]
        == manifest["training"]["evaluated_weights_sha256"]
    )
    assert validate_package(output) == manifest
    fixture_input = manifest["fixtures"][0]["input"]["path"]
    values = np.fromfile(output / fixture_input, dtype="<f4").reshape(1, 729, 43)
    for variant in manifest["variants"]:
        options = ort.SessionOptions()
        options.intra_op_num_threads = options.inter_op_num_threads = 1
        options.graph_optimization_level = (
            ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
            if variant["id"] == "int8"
            else ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        )
        session = ort.InferenceSession(
            output / variant["model"]["path"],
            options,
            providers=["CPUExecutionProvider"],
        )
        results = session.run(["policy", "value"], {"features": values})
        np.testing.assert_allclose(results[1], [[math.tanh(0.5)]], atol=1e-5, rtol=1e-4)
        for name, result in zip(("policy", "value"), results, strict=True):
            saved = np.fromfile(
                output
                / variant["references"][manifest["fixtures"][0]["name"]][name]["path"],
                dtype="<f4",
            ).reshape(result.shape)
            compare_outputs(
                saved,
                result,
                precision=variant["id"],
                output=name,
                numeric_contract=manifest["numericContract"],
            )
    changed = copy.deepcopy(manifest)
    changed["training"]["evaluated_weights_sha256"] = "d" * 64
    (output / "manifest.json").write_text(json.dumps(changed))
    with pytest.raises(ValueError):
        validate_package(output)
