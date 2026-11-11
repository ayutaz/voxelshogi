"""Actual tiny val-origin arithmetic and Rust query replay on Linux CI only."""

import json

import pytest


def test_origin_partition_matches_same_weights_combined_validation():
    import torch

    from export.research_model import make_research_model
    from infrastructure.research.pilot.validation import origin_metrics
    from training.research_visit_fit import VisitRunConfig, evaluate_visits
    from training.tests.test_research_model_native import tiny
    from training.tests.test_research_visit_fit_native import corpus

    torch.set_num_threads(1)
    data = corpus().val
    data.provenance["split"] = "val"
    data.rows[0]["value"] = {"kind": "terminal-v1", "value": 1.0}
    config = VisitRunConfig(architecture=tiny("full"), batch_size=1, device="cpu")
    model = make_research_model(config.architecture, seed=config.seed)
    actual = origin_metrics(model, data, config)
    expected = evaluate_visits(model, data, config)
    for key in ("policy_ce", "value_mse", "loss"):
        assert actual["aggregate"][key] == pytest.approx(
            expected[key], rel=1e-6, abs=1e-7
        )
    assert actual["by_origin"]["terminal-v1"]["examples"] == 1
    assert actual["by_origin"]["bootstrap-v1"]["examples"] == 1


def test_real_query_port_replays_history_and_matches_both_identities():
    from voxelshogi import Game

    from infrastructure.research.pilot.validation import _query
    from training.evaluation_v2_runner import position_identity
    from training.research_data import input_identity
    from training.supervision import ROOT

    fixture = json.loads((ROOT / "export/fixtures/positions.json").read_text())[3]
    game = Game.from_record(fixture["record"])
    row = _query("model", game)
    assert row == {
        "role": "model",
        "record": game.record(),
        "physical_id": position_identity(game.snapshot()["vsfen"]),
        "input_id": input_identity(game.snapshot()),
    }
