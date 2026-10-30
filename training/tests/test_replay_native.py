"""Actual Rust replay and disk restoration on Linux; no learned-model fixture."""

import copy
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="external Linux only")


def test_native_cutoff_buffer_preserves_bootstrap_and_history_on_reopen(tmp_path):
    from voxelshogi import Game

    from training.replay import ReplayBuffer, verify_episode
    from training.selfplay_actor import ActorConfig, play_episode
    from training.selfplay_search import SearchConfig
    from training.tests.test_engine import corner_position

    game = Game(corner_position())
    cfg = ActorConfig(
        max_plies=1,
        temperature_plies=0,
        noise_fraction=0,
        bootstrap_discount=0.5,
        search=SearchConfig(simulations=1),
    )

    def evaluate(position):
        legal = position.legal_actions()
        return {a: 1 / len(legal) for a in legal}, 0.25

    e = play_episode(game, evaluate, cfg, model_sha256="a" * 64, source_commit="1" * 40)
    assert e["bootstrap"] == {"side": "w", "ply": 1, "value": 0.25}
    assert e["samples"][0]["value"]["value"] == -0.125
    report = verify_episode(
        e, expected_source="1" * 40, expected_model="a" * 64, expected_config=cfg
    )
    assert report["samples"] == 1
    b = ReplayBuffer(
        tmp_path / "buffer", source_commit="1" * 40, run_id="b" * 64, capacity=2
    )
    b.append(0, e, model_sha256="a" * 64, config=cfg)
    restored = ReplayBuffer(
        tmp_path / "buffer", source_commit="1" * 40, run_id="b" * 64, capacity=2
    )
    assert restored.next_slot == 1 and restored.episodes() == [e]
    assert game.record()["moves"] == []


@pytest.mark.parametrize(
    "case_id,move", [("mate-black", "232222"), ("repetition-near-end", "211111")]
)
def test_native_natural_results_and_eleven_ply_prefix_are_independently_verified(
    case_id, move
):
    from voxelshogi import Game

    from training.evaluation_cases import handmade_cases
    from training.replay import verify_episode
    from training.selfplay_actor import ActorConfig, play_episode
    from training.selfplay_search import SearchConfig

    case = next(x["case"] for x in handmade_cases() if x["case"]["id"] == case_id)
    game = Game.from_record(case["opening"])
    cfg = ActorConfig(
        max_plies=1,
        temperature_plies=0,
        noise_fraction=0,
        search=SearchConfig(simulations=1),
    )

    def evaluate(position):
        return {a: float(m == move) for a, m in position.legal_actions().items()}, 0.9

    e = play_episode(game, evaluate, cfg, model_sha256="a" * 64, source_commit="1" * 40)
    report = verify_episode(
        e, expected_source="1" * 40, expected_model="a" * 64, expected_config=cfg
    )
    assert report["value_kind"] == "terminal-v1" and report["samples"] == 1
    wrong = copy.deepcopy(e)
    wrong["samples"][0]["value"]["value"] = -0.5
    with pytest.raises(ValueError, match="value target"):
        verify_episode(
            wrong,
            expected_source="1" * 40,
            expected_model="a" * 64,
            expected_config=cfg,
        )
