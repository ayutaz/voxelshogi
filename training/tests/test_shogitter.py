"""Hand-written protocol examples; no third-party game records in fixtures."""

import json

import pytest


def test_transport_decodes_only_the_requested_record_without_executing_script():
    from training.shogitter import extract_record

    pool = [
        {"_1": 2, "_3": 4, "_5": 6},
        "id",
        42,
        "ruleId",
        166,
        "data",
        {"_7": 4, "_8": 9},
        "ruleid",
        "kifu",
        [],
    ]
    page = '<script>throw new Error("must not execute");</script><script>'
    page += (
        "window.__reactRouterContext.streamController.enqueue("
        + json.dumps(json.dumps(pool))
        + ");</script>"
    )
    assert extract_record(page, 42) == {"ruleid": 166, "kifu": []}
    with pytest.raises(ValueError):
        extract_record(page, 43)


@pytest.mark.parametrize(
    "move,expected",
    [
        ([0, [7, 24, [], [0, "aa"]], [7, 25, [0, "aa"], []]], "773763"),
        (
            [1, [3, 61, [0, "aa"], [1, "am"]], [3, 11, [1, "af"], []], [1, 1, "aa"]],
            "322377+",
        ),
        ([0, [5, 41, [], [0, "ag"]], [-1, 0, "ag"]], "R*555"),
        ([0, [5, 41, [], [0, "am"]], [5, 42, [0, "am"], []]], "565555"),
    ],
)
def test_delta_translation_preserves_layer_capture_promotion_and_drop(move, expected):
    from training.shogitter import convert_move

    assert convert_move(move) == expected


@pytest.mark.parametrize(
    "move",
    [
        [0, [0, 24, [], [0, "aa"]], [7, 25, [0, "aa"], []]],
        [0, [7, 82, [], [0, "aa"]], [7, 25, [0, "aa"], []]],
        [0, [7, 24, [], [1, "aa"]], [7, 25, [0, "aa"], []]],
        [0, [5, 41, [], [0, "ag"]]],  # Drop must consume a rook in hand.
        [
            0,
            [5, 41, [1, "aa"], [0, "ag"]],
            [5, 42, [0, "ag"], []],
        ],  # Missing captured pawn.
        [0, [5, 41, [], [0, "ah"]], [5, 42, [0, "aa"], []]],  # Pawn cannot become king.
    ],
)
def test_malformed_or_incomplete_move_deltas_are_rejected(move):
    from training.shogitter import convert_move

    with pytest.raises(ValueError):
        convert_move(move)


def test_source_deltas_require_matching_old_board_and_nonnegative_hands():
    from training.shogitter import apply_delta

    board, hands = [0] * 729, [0] * 14
    board[2 * 81 + 6 * 9 + 6] = 1
    move = [0, [7, 24, [], [0, "aa"]], [7, 25, [0, "aa"], []]]
    apply_delta(board, hands, move)
    assert board[2 * 81 + 5 * 9 + 6] == 1
    assert board[2 * 81 + 6 * 9 + 6] == 0
    with pytest.raises(ValueError):
        apply_delta(board, hands, move)
    with pytest.raises(ValueError):
        apply_delta([0] * 729, [0] * 14, [0, [5, 41, [], [0, "ag"]], [-1, 0, "ag"]])


@pytest.mark.parametrize("terminal", ["Resignation", "Checkmate"])
def test_replay_compares_all_board_hand_and_terminal_results(monkeypatch, terminal):
    import sys
    from types import SimpleNamespace

    from training.shogitter import replay_record

    before, after = [0] * 729, [0] * 729
    before[222] = after[213] = 1  # 7七III -> 7六III.
    result = {"Win": {"winner": "Black", "reason": terminal}}

    class FakeGame:
        moved = False
        adjudicated = False

        @classmethod
        def from_record(cls, claim):
            assert claim["result"] == result
            game = cls()
            game.moved = True
            game.adjudicated = True
            return game

        def snapshot(self):
            return {
                "board": after if self.moved else before,
                "hands": [0] * 14,
                "side": "w" if self.moved else "b",
                "finished": self.moved and terminal == "Checkmate",
                "result": result
                if self.moved and (terminal == "Checkmate" or self.adjudicated)
                else None,
                "hash": "0123456789abcdef",
            }

        def play(self, text):
            assert text == "773763"
            self.moved = True

        def record(self):
            return {"result": result}

    monkeypatch.setitem(sys.modules, "voxelshogi", SimpleNamespace(Game=FakeGame))
    ban = [[[] for _ in range(81)] for _ in range(9)]
    ban[6][23] = [0, "aa"]
    status = {"lost": 1, "ranking": [0, 1]}
    record = {
        "ruleid": 166,
        "date": {"start": "2026-10-20"},
        "status": status,
        "ban": ban,
        "players": [{"mochigoma": {}}, {"mochigoma": {}}],
        "kifu": [
            {"move": [0, [7, 24, [], [0, "aa"]], [7, 25, [0, "aa"], []]]},
            {
                "move": "_1",
                "disp": "☖投了" if terminal == "Resignation" else "☖詰み",
                "status": status,
            },
        ],
    }
    answer = replay_record(record)
    assert (
        answer["complete"] and answer["plies"] == 1 and answer["terminal"] == terminal
    )
    normal_snapshot = FakeGame.snapshot

    def corrupt_snapshot(self):
        snapshot = normal_snapshot(self)
        if self.moved:
            snapshot["board"] = snapshot["board"].copy()
            snapshot["board"][0] = 1
        return snapshot

    monkeypatch.setattr(FakeGame, "snapshot", corrupt_snapshot)
    with pytest.raises(ValueError, match="board/hand"):
        replay_record(record)
    monkeypatch.setattr(FakeGame, "snapshot", normal_snapshot)
    record["status"] = {"lost": 0}
    with pytest.raises(ValueError, match="ranking"):
        replay_record(record)


def test_final_holdings_are_independently_decoded_and_negative_counts_rejected():
    from training.shogitter import final_hands

    record = {"players": [{"mochigoma": {"aa": 2, "af": 1}}, {"mochigoma": {"ag": 3}}]}
    assert final_hands(record) == [2, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 3]
    record["players"][0]["mochigoma"]["aa"] = -1
    with pytest.raises(ValueError):
        final_hands(record)


def test_capture_hand_tuple_is_count_then_owner_not_owner_then_count():
    from training.shogitter import apply_delta, convert_move

    move = [0, [7, 24, [1, "aa"], [0, "ag"]], [7, 25, [0, "ag"], []], [1, 0, "aa"]]
    assert convert_move(move) == "773763"
    board, hands = [0] * 729, [0] * 14
    board[213] = 15
    board[222] = 7
    apply_delta(board, hands, move)
    assert hands == [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
