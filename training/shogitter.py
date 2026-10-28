"""Independent import of public Shogitter 166 deltas; no foreign engine code."""

import hashlib
import json
import re
from pathlib import Path

KINDS = "abcdefghijklmn"
PROMOTIONS = {0: 8, 1: 9, 2: 10, 3: 11, 5: 12, 6: 13}
BASE = {value: key for key, value in PROMOTIONS.items()}
HAND = {kind: index for index, kind in enumerate((0, 1, 2, 3, 4, 5, 6))}


def extract_record(page, record_id):
    if len(page) > 4 * 1024**2:
        raise ValueError("source page too large")
    match = re.search(r'streamController\.enqueue\(("(?:\\.|[^"\\])*")\)', page)
    if not match:
        raise ValueError("unsupported source transport")
    pool = json.loads(json.loads(match[1]))
    if not isinstance(pool, list) or len(pool) > 250000:
        raise ValueError("unsupported source references")

    def fields(value):
        if not isinstance(value, dict):
            return {}
        return {pool[int(key[1:])]: ref for key, ref in value.items()}

    def decode(index, ancestors=()):
        if index == -5:  # An absent optional property, not executable JavaScript.
            return None
        if (
            type(index) is not int
            or not 0 <= index < len(pool)
            or index in ancestors
            or len(ancestors) > 100
        ):
            raise ValueError("invalid source reference")
        value = pool[index]
        if isinstance(value, dict):
            return {
                key: decode(ref, (*ancestors, index))
                for key, ref in fields(value).items()
            }
        if isinstance(value, list):
            return [decode(ref, (*ancestors, index)) for ref in value]
        return value

    candidates = []
    for value in pool:
        keys = fields(value)
        if {"id", "ruleId", "data"} <= keys.keys() and decode(keys["id"]) == record_id:
            if decode(keys["ruleId"]) != 166:
                raise ValueError("source rule must be 166")
            candidates.append(keys["data"])
    if len(candidates) != 1:
        raise ValueError("requested source record missing or ambiguous")
    return decode(candidates[0])


def square(x, packed_y):
    if (
        type(x) is not int
        or type(packed_y) is not int
        or not 1 <= x <= 9
        or not 1 <= packed_y <= 81
    ):
        raise ValueError("invalid source coordinate")
    return x - 1, (packed_y - 1) % 9, (packed_y - 1) // 9


def piece(cell):
    if cell == []:
        return 0
    if (
        not isinstance(cell, list)
        or len(cell) != 2
        or type(cell[0]) is not int
        or cell[0] not in (0, 1)
        or not re.fullmatch(r"a[a-n]", cell[1])
    ):
        raise ValueError("unsupported source piece")
    return 1 + 14 * cell[0] + KINDS.index(cell[1][1])


def index(x, packed_y):
    file, rank, layer = square(x, packed_y)
    return layer * 81 + rank * 9 + file


def notation(change):
    return "".join(str(value + 1) for value in square(*change[:2]))


def convert_move(move):
    if (
        not isinstance(move, list)
        or not move
        or type(move[0]) is not int
        or move[0] not in (0, 1)
    ):
        raise ValueError("unsupported source move")
    side = move[0]
    changes = [item for item in move[1:] if isinstance(item, list) and len(item) == 4]
    hands = [item for item in move[1:] if isinstance(item, list) and len(item) == 3]
    if len(changes) + len(hands) != len(move) - 1:
        raise ValueError("unsupported source delta")
    for cell in changes:
        square(*cell[:2])
        piece(cell[2])
        piece(cell[3])
    origins = [cell for cell in changes if cell[2] and not cell[3]]
    targets = [cell for cell in changes if cell[3]]
    if len(targets) != 1 or targets[0][3][0] != side:
        raise ValueError("source destination owner differs")
    target = targets[0]
    after = piece(target[3]) - 1 - side * 14
    if len(changes) == 1 and not origins and not target[2] and after in HAND:
        if hands != [[side, -1, target[3][1]]]:
            raise ValueError("drop does not consume its hand piece")
        return "PLNSGBR"[HAND[after]] + "*" + notation(target)
    if len(changes) != 2 or len(origins) != 1 or origins[0][2][0] != side:
        raise ValueError("source origin differs")
    before = piece(origins[0][2]) - 1 - side * 14
    promoted = after != before
    if promoted and PROMOTIONS.get(before) != after:
        raise ValueError("invalid source promotion")
    expected = []
    if target[2]:
        captured = piece(target[2]) - 1
        if captured // 14 == side or captured % 14 == 7:
            raise ValueError("invalid source capture")
        base = BASE.get(captured % 14, captured % 14)
        expected = [[side, 1, "a" + KINDS[base]]]
    if hands != expected:
        raise ValueError("capture hand delta differs")
    return notation(origins[0]) + notation(target) + ("+" if promoted else "")


def apply_delta(board, hands, move):
    convert_move(move)
    updated_board, updated_hands = board.copy(), hands.copy()
    for change in move[1:]:
        if len(change) == 4:
            at = index(*change[:2])
            if updated_board[at] != piece(change[2]):
                raise ValueError("source old board differs")
            updated_board[at] = piece(change[3])
        else:
            side, amount, kind = change
            base = KINDS.index(kind[1])
            at = 7 * side + HAND[base]
            updated_hands[at] += amount
            if updated_hands[at] < 0:
                raise ValueError("source hand became negative")
    board[:], hands[:] = updated_board, updated_hands


def final_board(record):
    if len(record["ban"]) != 9 or any(len(column) != 81 for column in record["ban"]):
        raise ValueError("source board dimensions differ")
    board = [0] * 729
    for file, column in enumerate(record["ban"], 1):
        for rank, cell in enumerate(column, 1):
            board[index(file, rank)] = piece(cell)
    return board


def final_hands(record):
    if len(record["players"]) != 2:
        raise ValueError("source must have two players")
    hands = [0] * 14
    for side, player in enumerate(record["players"]):
        for kind, count in player["mochigoma"].items():
            if not re.fullmatch(r"a[a-g]", kind) or type(count) is not int or count < 0:
                raise ValueError("invalid source holding")
            hands[side * 7 + HAND[KINDS.index(kind[1])]] = count
    return hands


def replay_record(record):
    """Run only on Linux. Preserve every move, board, hand and terminal check."""
    from voxelshogi import Game

    if record["ruleid"] != 166 or record["date"]["start"] < "2026-10-18":
        raise ValueError("source predates the selected rules revision")
    entries = record["kifu"]
    if not entries or not isinstance(entries[-1]["move"], str):
        raise ValueError("source is not a completed annotated game")
    ending = entries[-1]
    if ending["disp"] not in ("☗投了", "☖投了", "☗詰み", "☖詰み"):
        raise ValueError("unsupported source termination; do not relabel a clock loss")
    board = final_board(record)
    for entry in reversed(entries[:-1]):
        for delta in entry["move"][1:]:
            if len(delta) == 4:
                at = index(*delta[:2])
                if board[at] != piece(delta[3]):
                    raise ValueError("source reverse delta differs")
                board[at] = piece(delta[2])
    game = Game()
    initial = game.snapshot()
    if board != initial["board"]:
        raise ValueError("source does not use the standard initial position")
    hands = [0] * 14
    metrics = {"captures": 0, "drops": 0, "promotions": 0, "layer_changes": 0}
    for ply, entry in enumerate(entries[:-1]):
        move = entry["move"]
        if move[0] != ply % 2:
            raise ValueError(f"source turn mismatch at ply {ply}")
        text = convert_move(move)
        apply_delta(board, hands, move)
        try:
            game.play(text)
        except ValueError as error:
            raise ValueError(f"illegal source move at ply {ply}") from error
        actual = game.snapshot()
        if actual["board"] != board or actual["hands"] != hands:
            raise ValueError(f"source board/hand mismatch at ply {ply}")
        metrics["drops"] += text[1] == "*"
        metrics["promotions"] += text.endswith("+")
        metrics["layer_changes"] += text[1] != "*" and text[2] != text[5]
        metrics["captures"] += any(len(x) == 3 and x[1] == 1 for x in move[1:])
    if hands != final_hands(record):
        raise ValueError("source final hands differ")
    lost = ending["status"]["lost"]
    winner = "White" if lost == 0 else "Black"
    if (
        lost not in (0, 1)
        or record["status"]["lost"] != lost
        or ending["status"]["ranking"] != [1 - lost, lost]
    ):
        raise ValueError("source final ranking differs")
    claim = game.record()
    reason = "Resignation" if ending["disp"].endswith("投了") else "Checkmate"
    if reason == "Resignation":
        if actual["finished"] or actual["side"] != ("b" if lost == 0 else "w"):
            raise ValueError("source resignation side differs")
        claim.update(
            termination="Resignation",
            result={"Win": {"winner": winner, "reason": reason}},
        )
    else:
        if actual["result"] != {"Win": {"winner": winner, "reason": reason}}:
            raise ValueError("source board termination differs")
    verified = Game.from_record(claim).snapshot()
    if verified["result"] != {"Win": {"winner": winner, "reason": reason}}:
        raise ValueError("replayed terminal result differs")
    return {
        "complete": True,
        "plies": len(entries) - 1,
        "terminal": reason,
        "winner": winner,
        "final_hash": verified["hash"],
        **metrics,
    }


def main():
    import argparse
    import platform
    import urllib.request

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--ids", type=int, nargs="+", default=[21377, 21292, 21205])
    args = parser.parse_args()
    if (
        platform.system() != "Linux"
        or not 1 <= len(args.ids) <= 10
        or len(set(args.ids)) != len(args.ids)
    ):
        parser.error(
            "run a fixed nonempty set of at most ten records on external Linux"
        )
    root = Path(__file__).resolve().parents[1]
    if not args.output.resolve().is_relative_to(root / "runs"):
        parser.error("source records must remain under ignored runs/")
    args.output.mkdir(parents=True, exist_ok=True)
    collected = []
    # Fix and retain the whole source set before running the engine. Never replace
    # an incompatible game with a different game to improve the success rate.
    for record_id in args.ids:
        url = f"https://shogitter.com/kifu/{record_id}"
        request = urllib.request.Request(
            url, headers={"User-Agent": "VoxelShogi compatibility research"}
        )
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read(4 * 1024**2 + 1)
        if len(raw) > 4 * 1024**2:
            raise ValueError("source exceeds size limit")
        (args.output / f"source-{record_id}.html").write_bytes(raw)
        record = extract_record(raw.decode(), record_id)
        collected.append((record_id, url, raw, record))
    rows = []
    for record_id, url, raw, record in collected:
        row = {
            "id": record_id,
            "source_url": url,
            "source_sha256": hashlib.sha256(raw).hexdigest(),
            "record_sha256": hashlib.sha256(
                json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "source_started_at": record["date"]["start"],
            "rule_id": record["ruleid"],
        }
        try:
            row.update(replay_record(record))
        except (ValueError, KeyError, TypeError, IndexError) as error:
            row.update(
                complete=False, error_type=type(error).__name__, error=str(error)[:180]
            )
        rows.append(row)
    summary = {
        "schema": "voxelshogi-shogitter-validation-v1",
        "complete": all(row["complete"] for row in rows),
        "selection": "Three completed public rule166 resignation games after 2026-10-17, selected by source metadata before replay; no substitution after failures. Clock losses and unfinished games are outside this cohort.",
        "ruleset_id": "voxelshogi-standard-v1",
        "records": rows,
        "limitations": "Selected public games only; this is not proof for all rules or all Shogitter games. Raw sources remain private and are not training data.",
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))
    raise SystemExit(0 if summary["complete"] else 1)


if __name__ == "__main__":
    main()
