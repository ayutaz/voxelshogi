"""Small numerical update and exact checkpoint replay on Linux CI."""

import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="external Linux only")


def samples():
    import numpy as np

    from training.research_targets import visit_policy
    from training.selfplay_training import Samples

    rows = [
        {
            "id": "first",
            "policy": visit_policy([3, 5], {3: 3, 5: 1}),
            "value": {"kind": "terminal-v1", "value": 1.0},
            "legal_actions": [3, 5],
        },
        {
            "id": "second",
            "policy": visit_policy([3, 5], {3: 1, 5: 3}),
            "value": {"kind": "bootstrap-v1", "value": -0.125},
            "legal_actions": [3, 5],
        },
    ]
    return Samples(
        [np.zeros((729, 43), dtype=np.float32) for _ in rows],
        rows,
        {"buffer_sha256": "b" * 64, "protected_sha256": "c" * 64},
    )


def model_optimizer(config):
    import torch

    from training.research_targets import ACTIONS

    class Heads(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.logits = torch.nn.Parameter(torch.zeros(6))
            self.estimate = torch.nn.Parameter(torch.tensor(0.0))

        def forward(self, features):
            logits = torch.nn.functional.pad(self.logits, (0, ACTIONS - 6)).expand(
                len(features), -1
            )
            return logits, self.estimate.tanh().reshape(1, 1).expand(len(features), 1)

    model = Heads()
    return model, torch.optim.AdamW(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
        foreach=False,
        fused=False,
    )


def binding():
    return {
        "source_commit": "1" * 40,
        "parent_model_sha256": "a" * 64,
        "generation": 0,
        "architecture": "fixture-v1",
    }


def test_soft_visit_learning_updates_parameters_and_resumes_bit_exactly(tmp_path):
    import torch

    from training.selfplay_training import TrainConfig, fit_samples

    cfg = TrainConfig(
        device="cpu",
        epochs=2,
        batch_size=2,
        learning_rate=0.01,
        weight_decay=0,
        save_every=1,
        threads=1,
    )
    a, ao = model_optimizer(cfg)
    b, bo = model_optimizer(cfg)
    full = fit_samples(
        a, ao, samples(), tmp_path / "full", config=cfg, input_binding=binding()
    )
    partial = fit_samples(
        b,
        bo,
        samples(),
        tmp_path / "resumed",
        config=cfg,
        input_binding=binding(),
        max_new_steps=1,
    )
    assert partial["reason"] == "max_steps" and partial["progress"]["step"] == 1
    c, co = model_optimizer(cfg)
    resumed = fit_samples(
        c,
        co,
        samples(),
        tmp_path / "resumed",
        config=cfg,
        input_binding=binding(),
        resume=True,
    )
    assert full["reason"] == resumed["reason"] == "complete"
    assert resumed["progress"]["epoch"] == 2 and resumed["progress"]["step"] == 4
    assert resumed["progress"]["examples"] == 4
    assert any(torch.count_nonzero(p).item() for p in a.parameters())
    for name, t in a.state_dict().items():
        torch.testing.assert_close(t, c.state_dict()[name], rtol=0, atol=0)
    for slot in ao.state.values():
        assert slot["step"].item() == 4


def test_initial_loss_matches_independent_uniform_ce_and_squared_value_oracle():
    import math

    from training.selfplay_training import TrainConfig, update_step

    cfg = TrainConfig(device="cpu", learning_rate=0.01, weight_decay=0)
    model, optimizer = model_optimizer(cfg)
    metrics = update_step(model, optimizer, samples(), [0], device="cpu")
    assert metrics["policy_loss"] == pytest.approx(math.log(2), abs=1e-6)
    assert metrics["value_mse"] == 1.0
    assert metrics["loss"] == pytest.approx(1 + math.log(2), abs=1e-6)
    assert metrics["value_kind"] == "terminal-v1" and metrics["examples"] == 1
    with pytest.raises(ValueError, match="homogeneous"):
        update_step(model, optimizer, samples(), [0, 1], device="cpu")


def test_replay_samples_encode_full_real_histories_and_filter_protected_inputs(
    tmp_path,
):
    from voxelshogi import Game

    from training.replay import ReplayBuffer
    from training.research_data import input_identity
    from training.selfplay_actor import ActorConfig, play_episode
    from training.selfplay_search import SearchConfig
    from training.selfplay_training import replay_samples
    from training.tests.test_engine import corner_position

    game = Game(corner_position())
    cfg = ActorConfig(
        max_plies=1,
        temperature_plies=0,
        noise_fraction=0,
        search=SearchConfig(simulations=1),
    )

    def evaluate(p):
        legal = p.legal_actions()
        return {a: 1 / len(legal) for a in legal}, 0.25

    e = play_episode(game, evaluate, cfg, model_sha256="a" * 64, source_commit="1" * 40)
    b = ReplayBuffer(
        tmp_path / "buffer", source_commit="1" * 40, run_id="b" * 64, capacity=2
    )
    b.append(0, e, model_sha256="a" * 64, config=cfg)
    data = replay_samples(b, protected={"f" * 64})
    assert len(data.rows) == 1 and data.features[0].shape == (729, 43)
    assert data.rows[0]["value"]["kind"] == "bootstrap-v1"
    with pytest.raises(ValueError, match="eligible"):
        replay_samples(b, protected={input_identity(game.snapshot())})


def test_changed_feature_bytes_cannot_resume_under_same_metadata(tmp_path):
    from training.selfplay_training import TrainConfig, fit_samples

    cfg = TrainConfig(device="cpu", epochs=2, batch_size=1, save_every=1)
    model, optimizer = model_optimizer(cfg)
    data = samples()
    fit_samples(
        model,
        optimizer,
        data,
        tmp_path / "run",
        config=cfg,
        input_binding=binding(),
        max_new_steps=1,
    )
    data.features[0][0, 0] = 1
    restored, ro = model_optimizer(cfg)
    with pytest.raises(ValueError, match="binding"):
        fit_samples(
            restored,
            ro,
            data,
            tmp_path / "run",
            config=cfg,
            input_binding=binding(),
            resume=True,
        )


def test_soft_policy_gradient_uses_all_visit_mass_and_masks_illegal_logits():
    import torch

    from training.selfplay_training import TrainConfig, update_step

    cfg = TrainConfig(device="cpu", learning_rate=0.01, weight_decay=0)
    model, _ = model_optimizer(cfg)
    optimizer = torch.optim.SGD(model.parameters(), lr=0)
    data = samples()
    data.rows[0]["value"]["value"] = 0.0
    update_step(model, optimizer, data, [0], device="cpu")
    torch.testing.assert_close(
        model.logits.grad,
        torch.tensor([0.0, 0.0, 0.0, -0.25, 0.0, 0.25]),
        rtol=0,
        atol=0,
    )
