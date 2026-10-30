"""Small fake ports exercise orchestration only, never simulate shogi rules."""

from copy import deepcopy

import pytest

from training.tests.test_evaluation_v2 import protocol


class FakeGame:
    def __init__(self, record, mate_after=None):
        self.value = deepcopy(record)
        self.mate_after = mate_after
        self.played = 0

    def record(self):
        return deepcopy(self.value)

    def snapshot(self):
        return {
            "finished": self.value["result"] is not None,
            "side": "b" if self.played % 2 == 0 else "w",
            "result": deepcopy(self.value["result"]),
        }

    def legal_actions(self):
        return {7: "legal-seven", 9: "legal-nine"}

    def play(self, move):
        assert move in self.legal_actions().values()
        self.value["moves"].append(move)
        self.played += 1
        if self.played == self.mate_after:
            self.value["result"] = {"Win": {"winner": "Black", "reason": "Checkmate"}}


def play(case, game, **kwargs):
    from training.evaluation_v2_runner import _play_case

    times = iter([10.0, 13.0])
    return _play_case(
        case,
        game,
        model_side="b",
        choose_model=lambda g: 7,
        choose_opponent=lambda g: 9,
        clock=lambda: next(times),
        **kwargs,
    )


def test_additional_limit_excludes_opening_and_preserves_prefix_and_color_routing():
    case = protocol()["cases"][0]
    result = play(case, FakeGame(case["opening"]))
    assert result["record"]["moves"] == ["opaque-prefix", "legal-seven", "legal-nine"]
    assert result["record"]["termination"] == "MaxPlies"
    assert result["record"]["result"] == {"Draw": {"reason": "MaxPlies"}}
    assert result["outcome"] == "cutoff" and result["elapsed_seconds"] == 3.0
    assert case["opening"]["moves"] == ["opaque-prefix"]


def test_natural_last_ply_mate_precedes_cutoff_and_cannot_be_relabelled_draw():
    case = protocol()["cases"][0]
    result = play(case, FakeGame(case["opening"], mate_after=2))
    assert result["outcome"] == "win"
    assert result["record"]["termination"] is None
    assert result["record"]["result"] == {
        "Win": {"winner": "Black", "reason": "Checkmate"}
    }


def test_interruption_illegal_actions_and_no_actions_do_not_emit_completed_result():
    from training.evaluation_v2_runner import _play_case

    case = protocol()["cases"][0]
    with pytest.raises(InterruptedError):
        play(case, FakeGame(case["opening"]), stop_requested=lambda: True)
    game = FakeGame(case["opening"])
    with pytest.raises(ValueError):
        _play_case(
            case,
            game,
            model_side="b",
            choose_model=lambda g: 999,
            choose_opponent=lambda g: 9,
        )
    game.legal_actions = lambda: {}
    with pytest.raises(ValueError):
        play(case, game)


def test_position_identity_excludes_ply_but_retains_rules_side_and_hands():
    from training.evaluation_v2_runner import position_identity

    original = position_identity("opaque-board b 2P 1")
    assert original == position_identity("opaque-board b 2P 900")
    for value in ("other-board b 2P 1", "opaque-board w 2P 1", "opaque-board b P 1"):
        assert position_identity(value) != original
    with pytest.raises(ValueError):
        position_identity("opaque-board b 2P 1", ruleset="nine-kings")
    for value in ("broken", "board x - 1", "board b - 0", "board b - nan"):
        with pytest.raises(ValueError):
            position_identity(value)


def test_native_execution_is_rejected_on_mac_before_importing_engine(monkeypatch):
    from training.evaluation_v2_runner import run_protocol

    monkeypatch.setattr("training.evaluation_v2_runner.sys.platform", "darwin")
    with pytest.raises(ValueError, match="Linux"):
        run_protocol(protocol(), {}, "unused-output")


def test_native_policy_identity_binds_source_search_limits_and_random_seed_rule():
    from training.evaluation_v2_runner import rust_policy_identity

    limits = protocol()["search_limits"]
    original = rust_policy_identity("alphabeta-v1", "a" * 40, limits)
    assert original != rust_policy_identity("alphabeta-v1", "b" * 40, limits)
    assert original != rust_policy_identity(
        "alphabeta-v1", "a" * 40, {**limits, "max_nodes": 1}
    )
    assert original != rust_policy_identity("random-canonical-v1", "a" * 40, limits)
    with pytest.raises(ValueError):
        rust_policy_identity("unknown", "a" * 40, limits)


def test_random_policy_identifies_python_rng_separately_from_rust_search():
    from training.evaluation_v2 import validate_protocol

    spec = protocol()
    spec["participants"]["opponent"].update(
        policy="random-canonical-v1", backend="python-rng"
    )
    assert len(validate_protocol(spec)) == 64
    spec["participants"]["opponent"]["backend"] = "rust"
    with pytest.raises(ValueError):
        validate_protocol(spec)
