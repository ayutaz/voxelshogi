"""Linux-only Rust integration; handwritten policies isolate orchestration."""

import pytest


@pytest.mark.parametrize(
    "case_id,move,winner",
    [("mate-black", "232222", "Black"), ("mate-white", "878888", "White")],
)
def test_actor_forks_real_histories_and_records_a_handwritten_mate(
    case_id, move, winner
):
    from voxelshogi import Game

    from training.evaluation_cases import handmade_cases
    from training.selfplay_actor import ActorConfig, play_episode
    from training.selfplay_search import SearchConfig

    case = next(
        item["case"] for item in handmade_cases() if item["case"]["id"] == case_id
    )
    game = Game.from_record(case["opening"])
    original = game.record()
    calls = []

    def evaluate(position):
        calls.append(position.snapshot()["side"])
        legal = position.legal_actions()
        assert move in legal.values()
        return {a: float(text == move) for a, text in legal.items()}, 0.8

    config = ActorConfig(
        max_plies=1,
        temperature_plies=0,
        noise_fraction=0,
        search=SearchConfig(simulations=1),
    )
    episode = play_episode(
        game, evaluate, config, model_sha256="a" * 64, source_commit="1" * 40
    )
    assert episode["record"]["result"] == {
        "Win": {"winner": winner, "reason": "Checkmate"}
    }
    assert episode["termination_kind"] == "natural"
    assert episode["samples"][0]["move"] == move
    assert episode["samples"][0]["value"] == {"kind": "terminal-v1", "value": 1.0}
    assert len(calls) == 1 and game.record() == original
    assert (
        Game.from_record(episode["record"]).snapshot()["result"]
        == episode["record"]["result"]
    )


def test_actor_keeps_eleven_ply_repetition_history_and_uses_natural_draw_label():
    from voxelshogi import Game

    from training.evaluation_cases import handmade_cases
    from training.selfplay_actor import ActorConfig, play_episode
    from training.selfplay_search import SearchConfig

    case = next(
        item["case"]
        for item in handmade_cases()
        if item["case"]["id"] == "repetition-near-end"
    )
    game = Game.from_record(case["opening"])
    original = game.record()
    calls = []

    def evaluate(position):
        calls.append(1)
        return {
            a: float(text == "211111") for a, text in position.legal_actions().items()
        }, 0.9

    config = ActorConfig(
        max_plies=1,
        temperature_plies=0,
        noise_fraction=0,
        search=SearchConfig(simulations=1),
    )
    episode = play_episode(
        game, evaluate, config, model_sha256="a" * 64, source_commit="1" * 40
    )
    assert len(episode["record"]["moves"]) == 12 and len(episode["samples"]) == 1
    assert episode["samples"][0]["ply"] == 11
    assert episode["record"]["result"] == {"Draw": {"reason": "Repetition"}}
    assert episode["samples"][0]["value"] == {"kind": "terminal-v1", "value": 0.0}
    assert len(calls) == 1 and game.record() == original
    assert Game.from_record(episode["record"]).snapshot()["finished"]


def test_actual_cutoff_record_replays_in_rust_without_becoming_a_draw_teacher():
    from voxelshogi import Game

    from training.selfplay_actor import ActorConfig, play_episode
    from training.selfplay_search import SearchConfig
    from training.tests.test_engine import corner_position

    game = Game(corner_position())

    def evaluate(position):
        legal = position.legal_actions()
        return {a: 1 / len(legal) for a in legal}, 0.2

    config = ActorConfig(
        max_plies=1,
        temperature_plies=0,
        noise_fraction=0,
        search=SearchConfig(simulations=1),
    )
    episode = play_episode(
        game, evaluate, config, model_sha256="a" * 64, source_commit="1" * 40
    )
    assert episode["termination_kind"] == "cutoff"
    assert episode["samples"][0]["value"]["kind"] == "bootstrap-v1"
    assert episode["samples"][0]["value"]["value"] == -0.2
    replayed = Game.from_record(episode["record"])
    assert replayed.snapshot()["finished"]
    assert replayed.snapshot()["result"] == {"Draw": {"reason": "MaxPlies"}}
    assert not game.snapshot()["finished"]
