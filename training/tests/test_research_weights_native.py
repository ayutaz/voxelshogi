"""Actual M safetensors and Rust-facing players, executed on Linux only."""

import json
from pathlib import Path

import pytest

from training.tests.test_research_weights import metadata

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("architecture", ["full", "axial", "geometry", "cnn"])
def test_actual_M_weight_roundtrip_and_legal_player_use_the_declared_structure(
    tmp_path, architecture
):
    import torch
    from voxelshogi import Game

    from export.research_contract import architecture_config
    from export.research_model import make_research_model
    from training.evaluation_puct import PuctPlayer
    from training.research_weights import (
        load_research_network,
        load_research_player,
        research_metadata,
        write_research_weights,
    )

    torch.set_num_threads(1)
    value = metadata(architecture)
    model = make_research_model(architecture_config(architecture), seed=value["seed"])
    # Distinct from constructor weights: skipping load_state_dict must fail.
    with torch.no_grad():
        model.position[0, 0, 0] += 0.25
    path = tmp_path / "M.safetensors"
    receipt = write_research_weights(model.state_dict(), path, metadata=value)
    assert research_metadata(path) == value
    network, loaded_metadata = load_research_network(
        path, expected_sha256=receipt["sha256"], device="cpu"
    )
    assert loaded_metadata == value
    assert network.config == architecture_config(architecture) and not network.training
    for key, tensor in model.state_dict().items():
        assert torch.equal(tensor, network.state_dict()[key])
    del network
    fixture = json.loads((ROOT / "export/fixtures/positions.json").read_text())[2]
    game = Game.from_record(fixture["record"])
    features = torch.from_numpy(game.features()).unsqueeze(0)
    legal = sorted(game.legal_actions())
    with torch.inference_mode():
        logits, _ = model(features)
    expected = min(legal, key=lambda a: (-logits[0, a].item(), a))
    seen = []
    player = load_research_player(
        path,
        expected_sha256=receipt["sha256"],
        device="cpu",
        policy="legal-argmax-v1",
        observe_input=lambda g: seen.append(g.record()),
    )
    assert player(game) == expected
    assert seen == [game.record()]
    puct = load_research_player(
        path, expected_sha256=receipt["sha256"], device="cpu", policy="puct32-v1"
    )
    assert isinstance(puct, PuctPlayer)
    assert puct.evaluate.model.config == architecture_config(architecture)
    assert puct.evaluate.binding["artifact_sha256"] == receipt["sha256"]
    for key, tensor in model.state_dict().items():
        assert torch.equal(tensor, puct.evaluate.model.state_dict()[key])
    if architecture == "geometry":
        priors, estimate = puct.evaluate(game)
        assert set(priors) == set(legal) and abs(sum(priors.values()) - 1) < 1e-12
        assert -1 <= estimate <= 1
    stopped = load_research_player(
        path,
        expected_sha256=receipt["sha256"],
        device="cpu",
        policy="legal-argmax-v1",
        stop_requested=lambda: True,
        observe_input=lambda _: pytest.fail("stopped player observed a neural input"),
    )
    with pytest.raises(InterruptedError):
        stopped(game)
    with pytest.raises(ValueError, match="fresh"):
        write_research_weights(model.state_dict(), path, metadata=value)
    bad = dict(model.state_dict())
    key = next(iter(bad))
    bad[key] = bad[key].half()
    with pytest.raises(ValueError, match="FP32"):
        write_research_weights(bad, tmp_path / "half.safetensors", metadata=value)
    assert not (tmp_path / "half.safetensors").exists()
    missing = dict(model.state_dict())
    missing.pop(next(iter(missing)))
    with pytest.raises(ValueError, match="parameter count"):
        write_research_weights(
            missing, tmp_path / "missing.safetensors", metadata=value
        )
    assert not (tmp_path / "missing.safetensors").exists()
