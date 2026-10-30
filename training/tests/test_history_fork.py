"""Rust-backed histories and independent branches; actual games run on Linux."""

import pytest

from training.tests.test_engine import corner_position


def before_repetition():
    from voxelshogi import Game

    game = Game(corner_position())
    cycle = ["999899", "111211", "899999", "211111"]
    for move in (cycle * 3)[:-1]:
        game.play(move)
    return game


def test_fork_preserves_repetition_history_and_branches_are_independent():
    from voxelshogi import Game

    game = before_repetition()
    original = game.record()
    fork, other = game.fork(), game.fork()
    assert fork.record() == original and fork.snapshot() == game.snapshot()
    fork.play("211111")
    assert fork.snapshot()["result"] == {"Draw": {"reason": "Repetition"}}
    assert fork.snapshot()["finished"] and fork.legal_actions() == {}
    assert game.record() == original and not game.snapshot()["finished"]
    other.play("211311")
    assert other.snapshot()["result"] is None
    assert other.record()["moves"][-1] == "211311"
    assert game.record() == original and fork.record()["moves"][-1] == "211111"
    assert Game.from_record(fork.record()).snapshot() == fork.snapshot()
    # Same VSFEN without the earlier occurrences cannot produce this repetition.
    without_history = Game(game.snapshot()["vsfen"])
    without_history.play("211111")
    assert not without_history.snapshot()["finished"]


@pytest.mark.parametrize(
    "termination,result",
    [
        ("MaxPlies", {"Draw": {"reason": "MaxPlies"}}),
        ("Abandoned", None),
    ],
)
def test_fork_keeps_external_stop_and_rejects_further_play(termination, result):
    from voxelshogi import Game

    record = Game(corner_position()).record()
    record.update(termination=termination, result=result)
    stopped = Game.from_record(record)
    fork = stopped.fork()
    assert fork.record() == record and fork.snapshot()["finished"]
    assert fork.snapshot()["result"] == result and fork.legal_actions() == {}
    with pytest.raises(ValueError):
        fork.play("999899")
    assert fork.record() == record and stopped.record() == record
