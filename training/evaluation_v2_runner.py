"""External Linux evaluation v2 runner; Rust is the only rule implementation."""

import argparse
import json
import platform
import random
import subprocess
import sys
import time
from pathlib import Path

from training.checkpoint import atomic_json
from training.evaluation import classify_result
from training.evaluation_v2 import (
    NEURAL_POLICIES,
    RULESET,
    fingerprint,
    summarize_matches,
    validate_match_rows,
    validate_protocol,
)
from training.feature_cache import file_hash

ROOT = Path(__file__).resolve().parents[1]


def position_identity(vsfen, *, ruleset=RULESET):
    """Fingerprint trusted Rust-canonical VSFEN without its move counter.

    This function does not validate a board. The producer must supply a Rust
    snapshot or a previously hash-verified, replay-audited corpus row.
    """
    parts = vsfen.split() if isinstance(vsfen, str) else []
    if (
        ruleset != RULESET
        or len(parts) != 4
        or parts[1] not in ("b", "w")
        or not parts[3].isascii()
        or not parts[3].isdigit()
        or int(parts[3]) < 1
    ):
        raise ValueError("invalid evaluation position identity")
    return fingerprint({"ruleset_id": ruleset, "position": " ".join(parts[:3])})


def _play_case(
    case,
    game,
    *,
    model_side,
    choose_model,
    choose_opponent,
    stop_requested=lambda: False,
    clock=time.monotonic,
):
    """Orchestrate a supplied port; only fake ports are used in Mac unit tests."""
    started = clock()
    prefix_length = len(case["opening"]["moves"])
    while True:
        snapshot = game.snapshot()
        if snapshot["finished"]:
            record = game.record()
            break  # A natural terminal result wins over the last-ply limit.
        if len(game.record()["moves"]) - prefix_length >= case["max_additional_plies"]:
            record = game.record()
            record.update(
                termination="MaxPlies", result={"Draw": {"reason": "MaxPlies"}}
            )
            break
        if stop_requested():
            raise InterruptedError("evaluation interrupted; no adjudicated result")
        legal = game.legal_actions()
        if not legal:
            raise ValueError("unfinished evaluation has no legal actions")
        chooser = choose_model if snapshot["side"] == model_side else choose_opponent
        action = chooser(game)
        if type(action) is not int or action not in legal:
            raise ValueError("evaluation player returned an illegal action")
        game.play(legal[action])
    return {
        "case_id": case["id"],
        "model_side": model_side,
        "seed": case["seed"],
        "opening_sha256": fingerprint(case["opening"]),
        "record": record,
        "outcome": classify_result(record["result"], model_side),
        "elapsed_seconds": clock() - started,
    }


def rust_policy_identity(policy, source_commit, limits):
    if policy not in ("alphabeta-v1", "random-canonical-v1"):
        raise ValueError("unknown native evaluation policy")
    return fingerprint(
        {
            "source_commit": source_commit,
            "policy": policy,
            "search_limits": limits,
            "random_seed": "100000 + case.seed",
        }
    )


def _native_player(policy, limits, seed):
    if policy == "random-canonical-v1":
        rng = random.Random(100000 + seed)
        return lambda game: rng.choice(sorted(game.legal_actions()))

    def choose(game):
        text = game.search(**limits)["best_move"]
        return next(
            (action for action, move in game.legal_actions().items() if move == text),
            None,
        )

    return choose


def _observed_player(player, role, observer):
    if observer is None:
        return player

    def choose(game):
        observer(role, game)
        return player(game)

    return choose


def _prepare_players(
    protocol, artifacts, *, stop_requested=lambda: False, observe_input=None
):
    players = {}
    for role, participant in protocol["participants"].items():
        if participant["policy"] not in NEURAL_POLICIES:
            if participant["artifact_sha256"] != rust_policy_identity(
                participant["policy"],
                protocol["source_commit"],
                protocol["search_limits"],
            ):
                raise ValueError("native policy identity differs")
            players[role] = None  # Recreate per case/side with its preregistered seed.
            continue
        path = Path(artifacts[role])
        if (
            path.is_symlink()
            or not path.is_file()
            or file_hash(path) != participant["artifact_sha256"]
        ):
            raise ValueError("evaluation model artifact hash differs")
        if participant["backend"] not in ("torch-cpu", "torch-cuda"):
            raise ValueError("this runner supports selected M6 Torch weights only")
        if participant["policy"] == "puct32-v1":
            from training.evaluation_puct import load_puct_player

            players[role] = load_puct_player(
                path,
                expected_sha256=participant["artifact_sha256"],
                device="cuda" if participant["backend"] == "torch-cuda" else "cpu",
                stop_requested=stop_requested,
                observe_input=(
                    (lambda game, role=role: observe_input(role, game))
                    if observe_input is not None
                    else None
                ),
            )
            continue
        import torch
        from safetensors.torch import load_file

        from export.model import make_model
        from training.checkpoint import seed_all
        from training.students import TorchStudent

        device = "cuda" if participant["backend"] == "torch-cuda" else "cpu"
        if device == "cuda" and not torch.cuda.is_available():
            raise ValueError("CUDA unavailable; no hidden CPU fallback")
        torch.set_num_threads(1)
        seed_all(314159)
        model = make_model(314159)
        model.load_state_dict(load_file(path, device="cpu"), strict=True)
        players[role] = _observed_player(
            TorchStudent(model, device=device), role, observe_input
        )
    return players


def verify_record(row, case):
    """Replay every move and claimed termination with the native Rust engine."""
    if sys.platform != "linux":
        raise ValueError("evaluation replay requires external Linux")
    from voxelshogi import Game

    opening = Game.from_record(case["opening"])
    replay = Game.from_record(row["record"])
    if opening.snapshot()["finished"] or not replay.snapshot()["finished"]:
        raise ValueError("invalid evaluation opening or unfinished result")
    if replay.record() != row["record"]:
        raise ValueError("evaluation record is not Rust canonical")
    if (
        row["case_id"] != case["id"]
        or row["record"]["initial"] != case["opening"]["initial"]
        or row["record"]["moves"][: len(case["opening"]["moves"])]
        != case["opening"]["moves"]
    ):
        raise ValueError("evaluation replay differs from assigned opening")
    if (
        classify_result(replay.snapshot()["result"], row["model_side"])
        != row["outcome"]
    ):
        raise ValueError("evaluation result differs from Rust replay")


def _descriptors(folder, rows):
    result = []
    for row in rows:
        name = f"{row['case_id']}-{row['model_side']}.json"
        path = folder / name
        result.append(
            {"path": name, "sha256": file_hash(path), "bytes": path.stat().st_size}
        )
    return result


def _read_metadata(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 32 * 1024**2:
        raise ValueError("invalid saved evaluation metadata")
    return json.loads(path.read_text())


def read_partial_run(folder, protocol):
    """Read a committed prefix; native replay is still required before reuse."""
    folder = Path(folder)
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("missing or symlink evaluation folder")
    if _read_metadata(folder / "protocol.json") != protocol:
        raise ValueError("saved evaluation protocol differs")
    saved = _read_metadata(folder / "run.json")
    files = saved.get("files", [])
    expected = [
        f"{case['id']}-{side}.json" for case in protocol["cases"] for side in ("b", "w")
    ]
    if (
        type(saved.get("complete")) is not bool
        or saved.get("protocol_sha256") != validate_protocol(protocol)
        or type(files) is not list
        or type(saved.get("games")) is not int
        or saved["games"] != len(files)
        or len(files) > len(expected)
        or any(
            type(f) is not dict or set(f) != {"path", "bytes", "sha256"} for f in files
        )
        or [f["path"] for f in files] != expected[: len(files)]
    ):
        raise ValueError("saved evaluation inventory/protocol differs")
    allowed = {"protocol.json", "run.json", "summary.json", *(f["path"] for f in files)}
    if {p.name for p in folder.glob("*.json")} - allowed:
        raise ValueError("uncommitted evaluation game inventory requires inspection")
    rows = []
    for descriptor in files:
        path = folder / descriptor["path"]
        row = _read_metadata(path)
        if (
            type(descriptor["bytes"]) is not int
            or path.stat().st_size != descriptor["bytes"]
            or file_hash(path) != descriptor["sha256"]
        ):
            raise ValueError("saved evaluation match bytes/hash differs")
        rows.append(row)
    validate_match_rows(rows, protocol, require_complete=saved["complete"])
    return rows, saved


def run_protocol(
    protocol,
    artifacts,
    folder,
    *,
    stop_requested=lambda: False,
    resume=False,
    observe_input=None,
):
    if sys.platform != "linux":
        raise ValueError("evaluation/model/search execution requires external Linux")
    if type(resume) is not bool:
        raise ValueError("explicit evaluation resume flag required")
    import fcntl

    folder = Path(folder)
    folder.parent.mkdir(parents=True, exist_ok=True)
    lock = folder.parent / f".{folder.name}.evaluation.lock"
    if folder.is_symlink() or lock.is_symlink():
        raise ValueError("symlink evaluation output/lock")
    with lock.open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("evaluation already has a running owner") from None
        return _execute_protocol(
            protocol,
            artifacts,
            folder,
            stop_requested=stop_requested,
            resume=resume,
            observe_input=observe_input,
        )


def checked_execution(protocol, artifacts):
    """Check the full immutable protocol and every root before player allocation."""
    if sys.platform != "linux":
        raise ValueError("evaluation/model/search execution requires external Linux")
    from voxelshogi import Game

    validate_protocol(protocol)
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True
    )
    if commit != protocol["source_commit"] or dirty:
        raise ValueError("evaluation requires the preregistered clean source commit")
    required = {
        role
        for role, p in protocol["participants"].items()
        if p["policy"] in NEURAL_POLICIES
    }
    if set(artifacts) != required:
        raise ValueError("unexpected or missing evaluation artifact")
    # Validate all roots before model allocation or output creation.
    for case in protocol["cases"]:
        opening = Game.from_record(case["opening"])
        if opening.snapshot()["finished"] or opening.record() != case["opening"]:
            raise ValueError("evaluation opening must be unfinished and Rust canonical")
    return Game, required, commit


def execution_runtime(protocol, required, commit):
    """Capture the same execution binding for sequential and assigned-case jobs."""
    runtime = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "source_commit": commit,
        "uv_lock_sha256": file_hash(ROOT / "uv.lock"),
    }
    if required:
        import torch

        runtime["torch"] = str(torch.__version__)
        if any(p["backend"] == "torch-cuda" for p in protocol["participants"].values()):
            runtime.update(
                cuda=torch.version.cuda,
                gpu=torch.cuda.get_device_name(0),
                cuda_lock_sha256=file_hash(ROOT / "infrastructure/cuda/uv.lock"),
            )
    return runtime


def _execute_protocol(
    protocol, artifacts, folder, *, stop_requested, resume, observe_input=None
):
    Game, required, commit = checked_execution(protocol, artifacts)
    digest = validate_protocol(protocol)
    folder = Path(folder)
    saved, rows = None, []
    if resume:
        rows, saved = read_partial_run(folder, protocol)
        cases = {c["id"]: c for c in protocol["cases"]}
        for row in rows:
            verify_record(row, cases[row["case_id"]])
        if saved["complete"]:
            return verify_run(folder)
    else:
        folder.mkdir(parents=True, exist_ok=False)
        atomic_json(folder / "protocol.json", protocol)
        atomic_json(
            folder / "run.json",
            {"complete": False, "protocol_sha256": digest, "games": 0, "files": []},
        )
    players = _prepare_players(
        protocol, artifacts, stop_requested=stop_requested, observe_input=observe_input
    )
    runtime = execution_runtime(protocol, required, commit)
    if saved and saved.get("runtime", runtime) != runtime:
        raise ValueError("resumed evaluation runtime differs from saved environment")

    def save_partial():
        atomic_json(
            folder / "run.json",
            {
                "complete": False,
                "protocol_sha256": digest,
                "runtime": runtime,
                "games": len(rows),
                "files": _descriptors(folder, rows),
            },
        )

    save_partial()
    completed = {(row["case_id"], row["model_side"]) for row in rows}
    for case in protocol["cases"]:
        for side in ("b", "w"):
            if (case["id"], side) in completed:
                continue
            choose = {
                role: player
                or _native_player(
                    protocol["participants"][role]["policy"],
                    protocol["search_limits"],
                    case["seed"],
                )
                for role, player in players.items()
            }
            row = _play_case(
                case,
                Game.from_record(case["opening"]),
                model_side=side,
                choose_model=choose["model"],
                choose_opponent=choose["opponent"],
                stop_requested=stop_requested,
            )
            row.update(
                protocol_sha256=digest,
                model_sha256=protocol["participants"]["model"]["artifact_sha256"],
                opponent_sha256=protocol["participants"]["opponent"]["artifact_sha256"],
            )
            verify_record(row, case)
            atomic_json(folder / f"{case['id']}-{side}.json", row)
            rows.append(row)
            save_partial()
    result = summarize_matches(
        rows,
        protocol,
        model_sha256=protocol["participants"]["model"]["artifact_sha256"],
        opponent_sha256=protocol["participants"]["opponent"]["artifact_sha256"],
    )
    result["verification_scope"] = (
        "all match records Rust replayed; full-corpus leakage audit is separate"
    )
    atomic_json(folder / "summary.json", result)
    atomic_json(
        folder / "run.json",
        {
            "complete": True,
            "protocol_sha256": digest,
            "summary_sha256": file_hash(folder / "summary.json"),
            "games": len(rows),
            "runtime": runtime,
            "files": [
                {
                    "path": f"{row['case_id']}-{row['model_side']}.json",
                    "sha256": file_hash(
                        folder / f"{row['case_id']}-{row['model_side']}.json"
                    ),
                    "bytes": (folder / f"{row['case_id']}-{row['model_side']}.json")
                    .stat()
                    .st_size,
                }
                for row in rows
            ],
        },
    )
    return result


def verify_run(folder):
    if sys.platform != "linux":
        raise ValueError("evaluation verification requires external Linux")
    folder = Path(folder)
    protocol = json.loads((folder / "protocol.json").read_text())
    receipt = json.loads((folder / "run.json").read_text())
    digest = validate_protocol(protocol)
    expected = {
        f"{case['id']}-{side}.json": case
        for case in protocol["cases"]
        for side in ("b", "w")
    }
    descriptors = receipt.get("files", [])
    if (
        receipt.get("complete") is not True
        or receipt.get("protocol_sha256") != digest
        or receipt.get("games") != len(expected)
        or len(descriptors) != len(expected)
        or {item["path"] for item in descriptors} != set(expected)
        or file_hash(folder / "summary.json") != receipt.get("summary_sha256")
    ):
        raise ValueError("incomplete or changed evaluation receipt/hash")
    rows = []
    for item in descriptors:
        path = folder / item["path"]
        if (
            path.is_symlink()
            or path.stat().st_size != item["bytes"]
            or file_hash(path) != item["sha256"]
        ):
            raise ValueError("evaluation game file hash differs")
        row = json.loads(path.read_text())
        verify_record(row, expected[item["path"]])
        rows.append(row)
    summary = summarize_matches(
        rows,
        protocol,
        model_sha256=protocol["participants"]["model"]["artifact_sha256"],
        opponent_sha256=protocol["participants"]["opponent"]["artifact_sha256"],
    )
    summary["verification_scope"] = (
        "all match records Rust replayed; full-corpus leakage audit is separate"
    )
    if summary != json.loads((folder / "summary.json").read_text()):
        raise ValueError("evaluation summary differs from replayed games")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("protocol", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--opponent", type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    artifacts = {
        name: getattr(args, name)
        for name in ("model", "opponent")
        if getattr(args, name) is not None
    }
    result = run_protocol(
        json.loads(args.protocol.read_text()),
        artifacts,
        args.output,
        resume=args.resume,
    )
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
