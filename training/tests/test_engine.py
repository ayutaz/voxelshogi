"""Python boundary: rule-derived expectations plus native/WASM fixture parity."""

import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]


def corner_position(side="b", hands="-"):
    layers = ["9/9/9/9/9/9/9/9/9"] * 9
    layers[0] = "8k/9/9/9/9/9/9/9/9"
    layers[8] = "9/9/9/9/9/9/9/9/K8"
    return "|".join(layers) + f" {side} {hands} 1"


def test_initial_position_has_rule_derived_piece_counts_and_fixed_hash():
    from voxelshogi import Game

    s = Game().snapshot()
    assert s["hash"] == "043b66e12f6b84fd"
    assert s["side"] == "b" and s["ply"] == 0
    assert len(s["board"]) == 729 and sum(x != 0 for x in s["board"]) == 372
    assert s["hands"] == [0] * 14
    assert s["board"][4 * 81 + 8 * 9 + 4] == 8  # Black king
    assert s["board"][4 * 81 + 4] == 22  # White king
    assert len(s["legal_moves"]) == 424
    assert s["result"] is None and not s["in_check"] and not s["finished"]
    assert s["evaluation"] == 0


def test_corner_king_moves_actions_and_features_are_hand_computed():
    from voxelshogi import Game

    g = Game(corner_position())
    expected = {"999888", "999889", "999898", "999899", "999988", "999989", "999998"}
    assert set(g.snapshot()["legal_moves"]) == expected
    # From (x=8,y=8,z=8), one step in each available cube direction.
    origin = 728
    destinations = {
        z * 81 + y * 9 + x for z in (7, 8) for y in (7, 8) for x in (7, 8)
    } - {origin}
    assert set(g.legal_actions()) == {2 * (origin * 729 + to) for to in destinations}
    features = g.features()
    assert features.shape == (729, 43) and features.dtype == np.float32
    assert features[origin, 8] == 1 and features[0, 22] == 1
    assert np.all(features[:, :29].sum(axis=1) == 1)
    assert np.count_nonzero(g.action_masks()) == 7
    for action, text in g.legal_actions().items():
        assert text in expected and g.action_masks()[action]


def test_play_replay_and_rejected_move_preserve_state():
    from voxelshogi import Game

    g = Game()
    before = g.snapshot()
    for text in ("garbage", "555554"):
        with pytest.raises(ValueError):
            g.play(text)
        assert g.snapshot() == before
    g.play("577567")
    s = g.snapshot()
    assert s["side"] == "w" and s["ply"] == 1
    assert s["board"][6 * 81 + 6 * 9 + 4] == 0
    assert s["board"][6 * 81 + 5 * 9 + 4] == 1
    assert Game.from_record(g.record()).snapshot() == s
    bad = g.record()
    bad["moves"][0] = "555554"
    with pytest.raises(ValueError):
        Game.from_record(bad)
    with pytest.raises(ValueError):
        Game("invalid")


def test_search_has_fixed_depth_nodes_and_no_false_teacher_score():
    from voxelshogi import Game

    g = Game(corner_position())
    a = g.search(max_depth=1, max_nodes=100)
    assert a == g.search(max_depth=1, max_nodes=100)
    assert a["score"] == 0 and a["completed_depth"] == 1 and a["nodes"] == 8
    assert a["best_move"] in g.snapshot()["legal_moves"] and a["stop_reason"] == "depth"
    interrupted = g.search(max_depth=3, max_nodes=1)
    assert interrupted["nodes"] == 1 and interrupted["completed_depth"] == 0
    assert interrupted["score"] is None and interrupted["stop_reason"] == "nodes"
    for kwargs in ({"max_depth": 65}, {"max_nodes": -1}, {"table_capacity": 1000001}):
        with pytest.raises((ValueError, OverflowError)):
            g.search(**kwargs)


def test_history_changes_repetition_outcome_and_survives_record_roundtrip():
    from voxelshogi import Game

    g = Game(corner_position())
    cycle = ["999899", "111211", "899999", "211111"]
    for _ in range(3):
        for text in cycle:
            g.play(text)
    s = g.snapshot()
    assert s["result"] == {"Draw": {"reason": "Repetition"}}
    assert s["finished"] and not s["legal_moves"]
    assert Game.from_record(g.record()).snapshot() == s
    assert not Game(s["vsfen"]).snapshot()["finished"]
    assert g.search()["best_move"] is None
    with pytest.raises(ValueError):
        g.play(cycle[0])


def test_model_contract_fixtures_and_native_wasm_search_results_match():
    from voxelshogi import Game

    fixtures = json.loads((ROOT / "export/fixtures/positions.json").read_text())
    assert len(fixtures) == 4
    for fixture in fixtures:
        g = Game.from_record(fixture["record"])
        s = g.snapshot()
        assert s["board"] == fixture["board"]
        assert s["hands"] == fixture["hands"] and s["side"] == fixture["side"]
        from export.contract import encode_position

        np.testing.assert_array_equal(
            g.features(), encode_position(s["board"], s["hands"], s["side"])[0]
        )
    cases = json.loads(
        (ROOT / "crates/voxelshogi-wasm/tests/fixtures/search.json").read_text()
    )
    assert len(cases) >= 3
    for case in cases:
        g = Game.from_record(case["record"])
        c = case["config"]
        # Fixtures can disable optimization; expose exactly those core options.
        result = g.search(
            max_depth=c["maxDepth"],
            max_nodes=c.get("maxNodes"),
            max_game_ply=c.get("maxGamePly"),
            **{
                {
                    "iterativeDeepening": "iterative_deepening",
                    "moveOrdering": "move_ordering",
                    "transpositionTable": "transposition_table",
                    "tableCapacity": "table_capacity",
                }[key]: value
                for key, value in c.get("options", {}).items()
            },
        )
        e = case["expected"]
        for key, native in {
            "bestMove": "best_move",
            "score": "score",
            "completedDepth": "completed_depth",
            "nodes": "nodes",
            "stopReason": "stop_reason",
            "lastIterationNodes": "last_iteration_nodes",
            "ttHits": "tt_hits",
        }.items():
            if key in e:
                assert result[native] == (
                    int(e[key])
                    if key in ("nodes", "lastIterationNodes", "ttHits")
                    else e[key]
                )


def test_white_drop_and_promotion_action_mapping():
    from voxelshogi import Game

    g = Game(corner_position("w", "p"))
    actions = g.legal_actions()
    # White pawn dropped at display 555 is canonical square 364.
    assert actions[1062882 + 364] == "P*555"
    assert actions[1062882 + 394] == "P*225"  # 728 - (4*81 + 1*9 + 1)
    assert g.action_masks().dtype == np.bool_
    g = Game.from_record(
        json.loads((ROOT / "export/fixtures/positions.json").read_text())[3]["record"]
    )
    assert g.snapshot()["evaluation"] == 500  # 1300 - 550 + 200 - 450
    promoted = [a for a, text in g.legal_actions().items() if text.endswith("+")]
    # The material fixture has already-promoted pieces; a pawn-in-zone fixture
    # below checks normal and promoted labels differ by exactly one.
    assert promoted == []
    layers = corner_position().split(" ")[0].split("|")
    layers[4] = "9/9/4P4/9/9/9/9/9/9"
    pawn = Game("|".join(layers) + " b - 1")
    ids = {text: a for a, text in pawn.legal_actions().items()}
    assert ids["535525+"] == ids["535525"] + 1


def test_gym_env_reports_actor_reward_and_truncation():
    from voxelshogi.env import VoxelShogiEnv

    env = VoxelShogiEnv(initial=corner_position(), max_plies=1)
    observation, info = env.reset(seed=17)
    assert env.observation_space.contains(observation)
    assert info["side"] == "b" and info["action_mask"].sum() == 7
    action = int(np.flatnonzero(info["action_mask"])[0])
    _, reward, terminated, truncated, info = env.step(action)
    assert reward == 0 and not terminated and truncated and info["side"] == "w"
    with pytest.raises(RuntimeError):
        env.step(action)
    env.reset(seed=17)
    with pytest.raises(ValueError):
        env.step(0)


def test_gym_natural_win_precedes_limit_and_reward_is_for_actor():
    from voxelshogi.env import VoxelShogiEnv

    case = json.loads((ROOT / "export/fixtures/positions.json").read_text())[2]
    env = VoxelShogiEnv(initial=case["record"]["initial"], max_plies=1)
    env.reset(seed=3)
    text = env.game.search(max_depth=1)["best_move"]
    action = next(a for a, m in env.game.legal_actions().items() if m == text)
    _, reward, terminated, truncated, info = env.step(action)
    assert terminated and not truncated and reward == 1.0
    assert info["result"] == {"Win": {"winner": "Black", "reason": "Checkmate"}}
    assert info["action_mask"].sum() == 0


def test_external_record_termination_is_preserved_by_search_and_masks():
    from voxelshogi import Game

    for termination, result, score in [
        ("MaxPlies", {"Draw": {"reason": "MaxPlies"}}, 0),
        ("Abandoned", None, None),
    ]:
        rec = Game(corner_position()).record()
        rec.update(termination=termination, result=result)
        game = Game.from_record(rec)
        assert game.snapshot()["finished"] and not game.legal_actions()
        assert game.search()["score"] == score
        assert game.search()["best_move"] is None


def test_capture_unpromotes_to_hand_and_promotion_survives_replay():
    from voxelshogi import Game

    fixture = json.loads((ROOT / "export/fixtures/positions.json").read_text())[3]
    game = Game.from_record(fixture["record"])
    game.play("555545")
    s = game.snapshot()
    assert s["hands"][0] == 3 and s["hands"][10] == 1
    assert s["side"] == "w" and s["evaluation"] == -1150
    assert Game.from_record(game.record()).snapshot() == s
    features = game.features()
    np.testing.assert_allclose(features[:, 32], 1 / 32)
    np.testing.assert_allclose(features[:, 36], 3 / 162)
    layers = corner_position().split(" ")[0].split("|")
    layers[4] = "9/9/4P4/9/9/9/9/9/9"
    pawn = Game("|".join(layers) + " b - 1")
    pawn.play("535525+")
    assert pawn.snapshot()["board"][4 * 81 + 9 + 4] == 9
    assert Game.from_record(pawn.record()).snapshot() == pawn.snapshot()
