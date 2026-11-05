"""Linux Rust fixtures and tiny real exporter, never a GPU performance claim."""

import pytest


def test_real_probe_fixtures_remove_only_the_existing_batch_axis():
    import numpy as np

    from training.research_probe import _inputs, probe_protocol

    inputs = _inputs(probe_protocol("d" * 40))
    assert [index for index, _, _ in inputs] == [0, 3]
    for _, features, legal in inputs:
        assert features.shape == (729, 43) and features.dtype == np.float32
        assert legal and legal == sorted(set(legal))
        np.testing.assert_array_equal(features[:, :29].sum(axis=1), np.ones(729))
    assert inputs[0][1][:, 0].sum() == 357  # 729 cells minus372 standard pieces
    assert inputs[1][1][:, 0].sum() == 725  # two kings, dragon and promoted pawn
    np.testing.assert_allclose(inputs[1][1][:, 29], 2 / 162)
    np.testing.assert_allclose(inputs[1][1][:, 39], 1 / 32)


@pytest.mark.parametrize("name", ["full", "axial", "geometry", "cnn"])
def test_probe_exporter_preserves_initial_weights_and_full_reference_tensors(
    name, tmp_path
):
    import numpy as np
    import torch
    from safetensors.torch import load_file

    from export.research_contract import ResearchConfig
    from export.research_model import make_research_model
    from training.feature_cache import file_hash
    from training.research_probe import _export_and_check, probe_protocol

    torch.set_num_threads(1)
    config = ResearchConfig(
        architecture=name, side=2, width=4, layers=1, heads=2, ffn=8, policy_rank=2
    )
    arrays = [
        np.linspace(-0.2, 0.4, 8 * 43, dtype=np.float32).reshape(8, 43),
        np.linspace(0.3, -0.1, 8 * 43, dtype=np.float32).reshape(8, 43),
    ]
    inputs = [(i, array, [0, 3, 7]) for i, array in enumerate(arrays)]
    report = _export_and_check(
        config, probe_protocol("d" * 40), inputs, tmp_path, device="cpu"
    )
    assert report["passed"] and report["reference_backend"] == "torch-cpu"
    assert len(report["numeric"]) == 8 and len(report["files"]) == 3
    for descriptor in report["files"]:
        path = tmp_path / descriptor["path"]
        assert (
            descriptor["sha256"] == file_hash(path)
            and descriptor["bytes"] == path.stat().st_size
        )
    original = make_research_model(config, seed=66001)
    saved = load_file(tmp_path / "model.safetensors")
    for key, tensor in original.state_dict().items():
        torch.testing.assert_close(saved[key], tensor, rtol=0, atol=0)
    references = load_file(tmp_path / "references.safetensors")
    with torch.inference_mode():
        for i, array in enumerate(arrays):
            features = torch.from_numpy(array[None])
            torch.testing.assert_close(
                references[f"fixture{i}.features"], features, rtol=0, atol=0
            )
            for label, tensor in zip(
                ("policy", "value"), original(features), strict=True
            ):
                torch.testing.assert_close(
                    references[f"fixture{i}.{label}"], tensor, rtol=0, atol=0
                )
