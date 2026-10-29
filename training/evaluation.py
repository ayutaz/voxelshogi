"""Fixed paired evaluation; statistics are pure, game/model execution is Linux."""

import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

from training.checkpoint import atomic_json
from training.feature_cache import file_hash
from training.supervision import evaluation_protocol


def classify_result(result, model_side):
    if model_side not in ("b", "w") or not isinstance(result, dict):
        raise ValueError("unfinished/invalid result or model side")
    if set(result) == {"Win"}:
        win = result["Win"]
        if (
            set(win) != {"winner", "reason"}
            or win["winner"] not in ("Black", "White")
            or win["reason"] not in ("Checkmate", "Resignation", "PerpetualCheck")
        ):
            raise ValueError("invalid winning result")
        return (
            "win"
            if win["winner"] == {"b": "Black", "w": "White"}[model_side]
            else "loss"
        )
    if set(result) == {"Draw"} and set(result["Draw"]) == {"reason"}:
        reason = result["Draw"]["reason"]
        if reason == "Repetition":
            return "draw"
        if reason == "MaxPlies":
            return "cutoff"
    raise ValueError("unsupported result")


def summarize_pairs(rows, *, seeds, opponent):
    if (
        not seeds
        or len(set(seeds)) != len(seeds)
        or any(type(seed) is not int or seed < 0 for seed in seeds)
        or opponent not in ("random", "search")
    ):
        raise ValueError("invalid expected evaluation cohort")
    expected = {(seed, side) for seed in seeds for side in ("b", "w")}
    games = {}
    for row in rows:
        key = (row["seed"], row["model_side"])
        if (
            key not in expected
            or key in games
            or row["opponent"] != opponent
            or row["outcome"] not in ("win", "loss", "draw", "cutoff")
        ):
            raise ValueError("invalid, unexpected, or repeated evaluation game")
        games[key] = row
    if set(games) != expected:
        raise ValueError("incomplete paired evaluation")
    pair_wins = []
    for seed in sorted(seeds):
        first, second = games[seed, "b"], games[seed, "w"]
        if first["opening_moves"] != second["opening_moves"]:
            raise ValueError("paired openings differ")
        pair_wins.append(
            int(first["outcome"] == "win") + int(second["outcome"] == "win")
        )
    counts = Counter(row["outcome"] for row in games.values())
    rng = random.Random(314159)
    samples = sorted(
        sum(rng.choice(pair_wins) for _ in pair_wins) / (2 * len(pair_wins))
        for _ in range(10000)
    )
    return {
        "games_started": len(games),
        "pairs": len(pair_wins),
        "wins": counts["win"],
        "losses": counts["loss"],
        "draws": counts["draw"],
        "cutoffs": counts["cutoff"],
        "win_rate": counts["win"] / len(games),
        "paired_bootstrap95": [samples[249], samples[9749]],
        "interval_method": "opening-pair bootstrap; 10000 resamples; seed314159; order statistics 250/9750",
    }


def _linux():
    if sys.platform != "linux":
        raise ValueError("match/search/model execution requires external Linux")


def opening_record(seed, *, plies=8, game_factory=None):
    _linux()
    from voxelshogi import Game

    if (
        type(seed) is not int
        or seed < 0
        or type(plies) is not int
        or not 0 <= plies <= 256
    ):
        raise ValueError("invalid opening seed/length")
    game = (game_factory or Game)()
    rng = random.Random(seed)
    for _ in range(plies):
        legal = game.legal_actions()
        if game.snapshot()["finished"] or not legal:
            raise ValueError("opening terminated before fixed length")
        game.play(legal[rng.choice(sorted(legal))])
    return game.record()


def play_match(
    opening,
    choose_action,
    *,
    model_side,
    opponent,
    seed,
    max_plies=256,
    stop_requested=lambda: False,
):
    _linux()
    from voxelshogi import Game

    if (
        model_side not in ("b", "w")
        or opponent not in ("random", "search")
        or type(seed) is not int
        or seed < 0
        or type(max_plies) is not int
        or not 1 <= max_plies <= 20000
        or len(opening["moves"]) > max_plies
    ):
        raise ValueError("invalid match configuration")
    game = Game.from_record(opening)
    rng = random.Random(100000 + seed)
    while True:
        snapshot = game.snapshot()
        if snapshot["finished"]:
            break  # Natural result on the last allowed ply takes precedence.
        if len(game.record()["moves"]) >= max_plies:
            record = game.record()
            record.update(
                termination="MaxPlies", result={"Draw": {"reason": "MaxPlies"}}
            )
            game = Game.from_record(record)
            break
        if stop_requested():
            raise InterruptedError("match interrupted; no adjudicated result")
        legal = game.legal_actions()
        if not legal:
            raise ValueError("unfinished match has no legal actions")
        if snapshot["side"] == model_side:
            action = choose_action(game)
        elif opponent == "random":
            action = rng.choice(sorted(legal))
        else:
            text = game.search(**evaluation_protocol()["search_limits"])["best_move"]
            action = next((key for key, move in legal.items() if move == text), None)
        if type(action) is not int or action not in legal:
            raise ValueError("model/opponent returned an illegal action")
        game.play(legal[action])
    record = game.record()
    result = {
        "seed": seed,
        "model_side": model_side,
        "opponent": opponent,
        "opening_moves": opening["moves"],
        "record": record,
        "plies": len(record["moves"]),
        "outcome": classify_result(game.snapshot()["result"], model_side),
    }
    verify_match(result, opening, max_plies=max_plies)
    return result


def verify_match(row, opening, *, max_plies=256):
    _linux()
    from voxelshogi import Game

    record = row["record"]
    game = Game.from_record(record)  # Rust revalidates every move and claimed result.
    snapshot = game.snapshot()
    outcome = classify_result(snapshot["result"], row["model_side"])
    if (
        not snapshot["finished"]
        or record["initial"] != opening["initial"]
        or record["ruleset_id"] != opening["ruleset_id"]
        or record["moves"][: len(opening["moves"])] != opening["moves"]
        or row["opening_moves"] != opening["moves"]
        or row["plies"] != len(record["moves"])
        or len(record["moves"]) > max_plies
        or row["outcome"] != outcome
        or (
            outcome == "cutoff"
            and (
                len(record["moves"]) != max_plies or record["termination"] != "MaxPlies"
            )
        )
        or (outcome != "cutoff" and record["termination"] is not None)
    ):
        raise ValueError("evaluation record/outcome differs from replay/opening/limits")
    return outcome


def _evaluation_binding(model, source_commit, protocol, *, custom_opening=False):
    fixed = evaluation_protocol()
    if protocol != fixed:
        changeable = {"schema", "opening_seeds", "opening_plies", "max_plies"}
        if (
            protocol.get("schema") != "voxelshogi-evaluation-smoke-v1"
            or set(protocol) != set(fixed)
            or any(protocol[key] != fixed[key] for key in set(fixed) - changeable)
        ):
            raise ValueError("unknown evaluation protocol")
    if (
        set(protocol["opening_seeds"]) != {"random", "search"}
        or any(
            not seeds
            or len(set(seeds)) != len(seeds)
            or any(type(seed) is not int or seed < 0 for seed in seeds)
            for seeds in protocol["opening_seeds"].values()
        )
        or type(protocol["max_plies"]) is not int
        or not 1 <= protocol["max_plies"] <= 20000
        or type(protocol["opening_plies"]) is not int
        or not 0 <= protocol["opening_plies"] < protocol["max_plies"]
        or set(model)
        != {"model_id", "artifact_sha256", "trained", "precision", "backend"}
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", model["model_id"])
        or not re.fullmatch(r"[0-9a-f]{64}", model["artifact_sha256"])
        or type(model["trained"]) is not bool
        or model["precision"] not in ("fp32", "fp16", "int8")
        or model["backend"] not in ("torch-cpu", "torch-cuda", "ort-cpu", "fixture")
        or (protocol == fixed and (model["backend"] == "fixture" or custom_opening))
        or not re.fullmatch(r"[0-9a-f]{40}", source_commit)
    ):
        raise ValueError("invalid evaluation model/source/profile")
    return {
        "schema": "voxelshogi-match-run-v1",
        "protocol": protocol,
        "model": model,
        "source_commit": source_commit,
    }


def evaluate_matches(
    choose_action,
    folder,
    *,
    model,
    source_commit,
    protocol=None,
    game_factory=None,
    stop_requested=lambda: False,
    resume=False,
):
    _linux()
    protocol = evaluation_protocol() if protocol is None else protocol
    binding = _evaluation_binding(
        model, source_commit, protocol, custom_opening=game_factory is not None
    )
    folder = Path(folder)
    if resume:
        if json.loads((folder / "run.json").read_text()) != binding:
            raise ValueError("evaluation binding differs")
        if (folder / "failure.json").exists():
            raise ValueError("failed cohort must be retained; use a new reviewed run")
    else:
        folder.mkdir(parents=True, exist_ok=False)
        atomic_json(folder / "run.json", binding)
    rows, files = {"random": [], "search": []}, []

    def interrupted():
        report = {
            "complete": False,
            "completed_games": len(files),
            "reason": "interrupted",
        }
        atomic_json(folder / "progress.json", report)
        return report

    try:
        for opponent, seeds in protocol["opening_seeds"].items():
            for seed in seeds:
                if stop_requested():
                    return interrupted()
                opening = opening_record(
                    seed, plies=protocol["opening_plies"], game_factory=game_factory
                )
                for side in ("b", "w"):
                    if stop_requested():
                        return interrupted()
                    path = folder / f"{opponent}-{seed}-{side}.json"
                    if path.exists():
                        if path.is_symlink():
                            raise ValueError("evaluation game must be a regular file")
                        row = json.loads(path.read_text())
                        if any(
                            row[key] != value
                            for key, value in (
                                ("seed", seed),
                                ("opponent", opponent),
                                ("model_side", side),
                            )
                        ):
                            raise ValueError("stored game identity differs")
                        verify_match(row, opening, max_plies=protocol["max_plies"])
                    else:
                        try:
                            row = play_match(
                                opening,
                                choose_action,
                                model_side=side,
                                opponent=opponent,
                                seed=seed,
                                max_plies=protocol["max_plies"],
                                stop_requested=stop_requested,
                            )
                        except InterruptedError:
                            return interrupted()
                        atomic_json(path, row)
                    rows[opponent].append(row)
                    files.append(
                        {
                            "file": path.name,
                            "bytes": path.stat().st_size,
                            "sha256": file_hash(path),
                        }
                    )
                    atomic_json(
                        folder / "progress.json",
                        {"complete": False, "completed_games": len(files)},
                    )
        report = {
            **binding,
            "complete": True,
            "production_profile": protocol == evaluation_protocol(),
            "cohorts": {
                opponent: summarize_pairs(
                    rows[opponent], seeds=seeds, opponent=opponent
                )
                for opponent, seeds in protocol["opening_seeds"].items()
            },
            "files": files,
        }
        atomic_json(folder / "evaluation.json", report)
        atomic_json(
            folder / "progress.json", {"complete": True, "completed_games": len(files)}
        )
        return report
    except Exception as error:
        atomic_json(
            folder / "failure.json",
            {
                "complete": False,
                "completed_games": len(files),
                "error_type": type(error).__name__,
            },
        )
        raise
