"""Bounded Actor -> verified replay -> FP32 learning -> immutable model updates."""

import argparse
import fcntl
import json
import math
import os
import re
import signal
import sys
import time
from contextlib import contextmanager
from dataclasses import asdict, replace
from pathlib import Path

from training.checkpoint import atomic_json
from training.feature_cache import file_hash
from training.policy_value import load_policy_value
from training.replay import ReplayBuffer
from training.research_data import canonical, fingerprint
from training.research_rental_control import _source_check
from training.selfplay_actor import ActorConfig, play_episode
from training.selfplay_search import SearchConfig
from training.selfplay_training import TrainConfig, fit_samples, replay_samples
from training.supervision import REVISION, ROOT, RULESET

SCHEMA = "voxelshogi-selfplay-generations-v1"


def _integer(value, low, high):
    return type(value) is int and low <= value <= high


def _sha(value, length):
    return (
        isinstance(value, str)
        and re.fullmatch(r"[0-9a-f]{" + str(length) + "}", value) is not None
    )


def _actor(raw):
    try:
        result = ActorConfig(**{**raw, "search": SearchConfig(**raw["search"])})
        if canonical(asdict(result)) != canonical(raw):
            raise ValueError("actor configuration differs")
        return result
    except (KeyError, TypeError) as error:
        raise ValueError("invalid generation actor config") from error


def make_protocol(
    source_commit,
    *,
    base_model_sha256,
    protection_sha256,
    protection_count,
    protection_provenance,
):
    return {
        "schema": SCHEMA,
        "source_commit": source_commit,
        "ruleset_id": RULESET,
        "architecture": "transformer-s-full-v1",
        "base_model_sha256": base_model_sha256,
        "protection_sha256": protection_sha256,
        "protection_count": protection_count,
        "protection_provenance": protection_provenance,
        "generations": 3,
        "episodes_per_generation": 16,
        "replay_capacity": 32,
        "opening_plies": 16,
        "families": [
            {"seed": 10000 + i, "split": "train", "opening": None} for i in range(16)
        ],
        "actor": asdict(ActorConfig()),
        "training": asdict(TrainConfig()),
    }


def validate_protocol(p):
    if (
        type(p) is not dict
        or set(p)
        != {
            "schema",
            "source_commit",
            "ruleset_id",
            "architecture",
            "base_model_sha256",
            "protection_sha256",
            "protection_count",
            "protection_provenance",
            "generations",
            "episodes_per_generation",
            "replay_capacity",
            "opening_plies",
            "families",
            "actor",
            "training",
        }
        or p["schema"] != SCHEMA
        or p["ruleset_id"] != RULESET
        or p["architecture"] != "transformer-s-full-v1"
        or not _sha(p["source_commit"], 40)
        or not _sha(p["base_model_sha256"], 64)
        or not _sha(p["protection_sha256"], 64)
        or not _integer(p["protection_count"], 1, 1000000)
        or not _integer(p["generations"], 1, 64)
        or not _integer(p["episodes_per_generation"], 1, 32)
        or not _integer(p["replay_capacity"], 1, 64)
        or not _integer(p["opening_plies"], 1, 32)
    ):
        raise ValueError("invalid selfplay generation protocol")
    provenance = p["protection_provenance"]
    if (
        type(provenance) is not dict
        or set(provenance)
        != {"m6_dataset_revision", "p5_evaluation_proof_sha256", "p51_dataset_revision"}
        or provenance["m6_dataset_revision"] != REVISION
        or not _sha(provenance["p5_evaluation_proof_sha256"], 64)
        or not _sha(provenance["p51_dataset_revision"], 40)
    ):
        raise ValueError("invalid protected-corpus provenance")
    actor = _actor(p["actor"])
    try:
        train = TrainConfig(**p["training"])
        if canonical(asdict(train)) != canonical(p["training"]):
            raise ValueError("training config differs")
    except (TypeError, KeyError) as error:
        raise ValueError("invalid generation training config") from error
    if actor.max_plies > 512 or actor.search.simulations > 256:
        raise ValueError("selfplay generation workload exceeds initial bounds")
    families = p["families"]
    if type(families) is not list or len(families) != p["episodes_per_generation"]:
        raise ValueError("family count differs")
    seeds = set()
    for family in families:
        if (
            type(family) is not dict
            or set(family) != {"seed", "split", "opening"}
            or not _integer(family["seed"], 0, 2**63 - 1)
            or family["seed"] in seeds
            or family["split"] != "train"
        ):
            raise ValueError(
                "selfplay families must be fixed, distinct and training-only"
            )
        seeds.add(family["seed"])
        record = family["opening"]
        if record is not None and (
            type(record) is not dict
            or set(record)
            != {"ruleset_id", "initial", "moves", "result", "termination"}
            or record["ruleset_id"] != RULESET
            or record["result"] is not None
            or record["termination"] is not None
            or not isinstance(record["initial"], str)
            or not record["initial"]
            or type(record["moves"]) is not list
            or len(record["moves"]) > 512
            or any(not isinstance(move, str) for move in record["moves"])
        ):
            raise ValueError("invalid declared opening record")
    return fingerprint(p)


def episode_settings(p, generation, index):
    validate_protocol(p)
    if not _integer(generation, 0, p["generations"] - 1) or not _integer(
        index, 0, p["episodes_per_generation"] - 1
    ):
        raise ValueError("invalid generation/episode cursor")
    actor = _actor(p["actor"])
    seed = (
        int(
            fingerprint(
                {"run_seed": actor.seed, "generation": generation, "episode": index}
            )[:16],
            16,
        )
        % 2**63
    )
    return replace(actor, seed=seed), p["families"][index]["seed"]


def _protection(path, p):
    path = Path(path)
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_size > 128 * 1024**2
        or file_hash(path) != p["protection_sha256"]
    ):
        raise ValueError("protected-input file/hash differs")
    value = json.loads(path.read_text())
    if (
        type(value) is not dict
        or set(value) != {"schema", "provenance", "ids"}
        or value["schema"] != "voxelshogi-protected-inputs-v1"
        or value["provenance"] != p["protection_provenance"]
        or type(value["ids"]) is not list
        or len(value["ids"]) != p["protection_count"]
        or any(not _sha(i, 64) for i in value["ids"])
        or value["ids"] != sorted(set(value["ids"]))
    ):
        raise ValueError("protected-input identities/provenance differ")
    return set(value["ids"])


@contextmanager
def _lock(folder):
    if folder.is_symlink():
        raise ValueError("symlink generation run")
    folder.mkdir(parents=True, exist_ok=True)
    marker = folder / ".voxelshogi-selfplay-run-v1"
    if not marker.exists():
        if any(folder.iterdir()):
            raise ValueError("unowned nonempty generation directory")
        marker.touch(exist_ok=False)
    if marker.is_symlink() or not marker.is_file() or marker.stat().st_size:
        raise ValueError("invalid generation ownership marker")
    with marker.open("rb") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def _opening(p, index):
    from voxelshogi import Game

    family = p["families"][index]
    if family["opening"] is not None:
        game = Game.from_record(family["opening"])
    else:
        import random

        game = Game()
        rng = random.Random(family["seed"])
        for _ in range(p["opening_plies"]):
            if game.snapshot()["finished"]:
                raise ValueError("seeded opening ended before the declared root")
            game.play(rng.choice(sorted(game.legal_actions().values())))
    if game.snapshot()["finished"]:
        raise ValueError("selfplay opening must be unfinished")
    return game


def _export(model, path):
    import torch
    from safetensors.torch import save_file

    state = {
        name: t.detach().cpu().contiguous()
        for name, t in sorted(model.state_dict().items())
    }
    if any(
        t.dtype != torch.float32 or not torch.isfinite(t).all() for t in state.values()
    ):
        raise ValueError("generation weights must be finite FP32")
    temporary = path.with_name(".model.safetensors.tmp")
    save_file(state, temporary)
    with temporary.open("rb") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    return file_hash(path)


def validate_publication(pair):
    if type(pair) is not dict or set(pair) != {"dataset", "state"}:
        raise ValueError(
            "both verified dataset and training-state receipts are required"
        )
    for kind, repo_type in (("dataset", "dataset"), ("state", "model")):
        receipt = pair[kind]
        if (
            type(receipt) is not dict
            or receipt.get("verified") is not True
            or receipt.get("dry_run") is not False
            or receipt.get("community_disabled") is not True
            or receipt.get("repo_type") != repo_type
            or not isinstance(receipt.get("repo_id"), str)
            or not receipt["repo_id"].startswith("voxelshogi/")
            or not _sha(receipt.get("hub_commit"), 40)
            or not _sha(receipt.get("release_sha256"), 64)
        ):
            raise ValueError("unverified or wrong publication receipt")


def _publish_pending(m, path, callback, folder):
    if callback is None:
        return
    for i in range(len(m["publications"]), len(m["generations"])):
        pair = callback(m["generations"][i], folder)
        validate_publication(pair)
        m["publications"].append({"generation": i, **pair})
        atomic_json(path, m)


def run_generations(
    p,
    base_model,
    protection_file,
    folder,
    *,
    max_new_generations=None,
    stop_requested=lambda: False,
    on_generation=None,
):
    if sys.platform != "linux":
        raise ValueError("selfplay generations require external Linux")
    import torch

    run_id = validate_protocol(p)
    _source_check(p["source_commit"])
    if max_new_generations is not None and not _integer(
        max_new_generations, 1, p["generations"]
    ):
        raise ValueError("invalid generation attempt bound")
    base_model = Path(base_model)
    if (
        base_model.is_symlink()
        or not base_model.is_file()
        or file_hash(base_model) != p["base_model_sha256"]
    ):
        raise ValueError("base model hash differs")
    protected = _protection(protection_file, p)
    folder = Path(folder)
    training = TrainConfig(**p["training"])
    torch.set_num_threads(training.threads)
    with _lock(folder):
        path = folder / "run.json"
        if not path.exists():
            atomic_json(
                path,
                {
                    "schema": SCHEMA,
                    "protocol": p,
                    "run_id": run_id,
                    "generations": [],
                    "publications": [],
                    "complete": False,
                },
            )
        if path.is_symlink():
            raise ValueError("symlink generation manifest")
        m = json.loads(path.read_text())
        if (
            set(m)
            != {
                "schema",
                "protocol",
                "run_id",
                "generations",
                "publications",
                "complete",
            }
            or m["schema"] != SCHEMA
            or canonical(m["protocol"]) != canonical(p)
            or m["run_id"] != run_id
            or type(m["generations"]) is not list
            or len(m["generations"]) > p["generations"]
            or type(m["publications"]) is not list
            or len(m["publications"]) > len(m["generations"])
            or type(m["complete"]) is not bool
            or m["complete"] != (len(m["generations"]) == p["generations"])
        ):
            raise ValueError("generation run binding differs")
        parent_path, parent_sha = base_model, p["base_model_sha256"]
        for i, record in enumerate(m["generations"]):
            file = folder / f"generation-{i:03d}/model.safetensors"
            if (
                record["generation"] != i
                or record["parent_model_sha256"] != parent_sha
                or record["file"] != file.relative_to(folder).as_posix()
                or file.is_symlink()
                or not file.is_file()
                or file_hash(file) != record["model_sha256"]
            ):
                raise ValueError("completed generation lineage/hash differs")
            parent_path, parent_sha = file, record["model_sha256"]
        for i, publication in enumerate(m["publications"]):
            if (
                set(publication) != {"generation", "dataset", "state"}
                or publication["generation"] != i
            ):
                raise ValueError("publication order differs")
            validate_publication({k: publication[k] for k in ("dataset", "state")})
        _publish_pending(m, path, on_generation, folder)
        buffer = ReplayBuffer(
            folder / "replay",
            source_commit=p["source_commit"],
            run_id=run_id,
            capacity=p["replay_capacity"],
        )
        new = 0

        def result(reason):
            return {
                "complete": m["complete"],
                "reason": reason,
                "generations_completed": len(m["generations"]),
                "next_slot": buffer.next_slot,
                "run_id": run_id,
                "published_generations": len(m["publications"]),
                "externally_persisted": bool(m["generations"])
                and len(m["publications"]) == len(m["generations"]),
            }

        for generation in range(len(m["generations"]), p["generations"]):
            if stop_requested():
                return result("stopped")
            if max_new_generations is not None and new >= max_new_generations:
                return result("max_generations")
            start, end = (
                generation * p["episodes_per_generation"],
                (generation + 1) * p["episodes_per_generation"],
            )
            cursor = buffer.next_slot
            if not start <= cursor <= end:
                raise ValueError("replay cursor differs from committed generations")
            evaluator = load_policy_value(
                parent_path, expected_sha256=parent_sha, device=training.device
            )
            if evaluator.binding != {
                "artifact_sha256": parent_sha,
                "architecture": p["architecture"],
                "backend": "torch-" + training.device,
                "compute_dtype": "float32",
            }:
                raise ValueError("actual evaluator binding differs")
            for slot in range(cursor, end):
                index = slot - start
                config, _ = episode_settings(p, generation, index)
                before_calls = evaluator.calls
                try:
                    episode = play_episode(
                        _opening(p, index),
                        evaluator,
                        config,
                        model_sha256=parent_sha,
                        source_commit=p["source_commit"],
                        stop_requested=stop_requested,
                    )
                except InterruptedError:
                    return result("stopped")
                if evaluator.calls - before_calls != episode["model_evaluations"]:
                    raise ValueError("observed model calls differ from episode counter")
                buffer.append(slot, episode, model_sha256=parent_sha, config=config)
            del evaluator
            if stop_requested():
                return result("stopped")
            data = replay_samples(buffer, protected=protected)
            directory = folder / f"generation-{generation:03d}"
            if directory.is_symlink():
                raise ValueError("symlink generation directory")
            directory.mkdir(exist_ok=True)
            learner = load_policy_value(
                parent_path, expected_sha256=parent_sha, device=training.device
            ).model
            learner.requires_grad_(True)
            config = replace(training, seed=training.seed + generation)
            optimizer = torch.optim.AdamW(
                learner.parameters(),
                lr=config.learning_rate,
                weight_decay=config.weight_decay,
                foreach=False,
                fused=False,
            )
            report = fit_samples(
                learner,
                optimizer,
                data,
                directory / "training",
                config=config,
                input_binding={
                    "source_commit": p["source_commit"],
                    "generation": generation,
                    "parent_model_sha256": parent_sha,
                    "architecture": p["architecture"],
                },
                resume=(directory / "training/run.json").exists(),
                stop_requested=stop_requested,
            )
            if report["reason"] != "complete":
                return result(report["reason"])
            file = directory / "model.safetensors"
            child_sha = _export(learner, file)
            record = {
                "generation": generation,
                "parent_model_sha256": parent_sha,
                "model_sha256": child_sha,
                "file": file.relative_to(folder).as_posix(),
                "training_progress": report["progress"],
                "input_sha256": data.sha256,
                "replay_sha256": file_hash(buffer.folder / "buffer.json"),
                "encoded_samples": len(data.rows),
                "sample_audit": data.provenance,
            }
            atomic_json(directory / "generation.json", record)
            m["generations"].append(record)
            m["complete"] = len(m["generations"]) == p["generations"]
            atomic_json(path, m)
            _publish_pending(m, path, on_generation, folder)
            parent_path, parent_sha = file, child_sha
            del learner, optimizer, data
            new += 1
        return result("complete")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("protocol", type=Path)
    parser.add_argument("base_model", type=Path)
    parser.add_argument("protected_inputs", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--max-new-generations", type=int)
    parser.add_argument("--max-seconds", type=float, required=True)
    args = parser.parse_args()
    if not math.isfinite(args.max_seconds) or not 1 <= args.max_seconds <= 14400:
        parser.error("--max-seconds must be between 1 and 14400")
    if not args.output.resolve().is_relative_to(ROOT / "runs"):
        parser.error("generation output must remain under ignored runs/")
    p = json.loads(args.protocol.read_text())
    started, stopped = time.monotonic(), False

    def stop(*_):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    print(
        json.dumps(
            run_generations(
                p,
                args.base_model,
                args.protected_inputs,
                args.output,
                max_new_generations=args.max_new_generations,
                stop_requested=lambda: (
                    stopped or time.monotonic() - started >= args.max_seconds
                ),
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
