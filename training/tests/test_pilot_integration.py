"""Run with the full suite on Linux CI, not as a local performance benchmark."""


def test_fixed_pilot_cases_replay_and_preserve_the_64_ply_history():
    from voxelshogi import Game

    from training.pilot import _cases

    cases = _cases(False)
    assert [c["name"] for c in cases] == [
        "opening-b",
        "opening-w",
        "trajectory-64",
        "sparse-mate",
        "sparse-hands",
    ]
    for case in cases:
        snapshot = Game.from_record(case["record"]).snapshot()
        assert not snapshot["finished"] and snapshot["legal_moves"]
    middle = cases[2]
    assert len(middle["record"]["moves"]) == 64
    assert Game.from_record(middle["record"]).snapshot()["ply"] == 64
    assert middle["kind"] == "fixed-random-trajectory-not-strategic-phase"
