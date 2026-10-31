"""FP32 learning from verified selfplay visits and explicit value origins."""

import hashlib
import json
import os
import random
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from training.checkpoint import (
    atomic_json,
    deterministic_runtime,
    load_checkpoint,
    save_checkpoint,
    seed_all,
)
from training.feature_cache import file_hash
from training.fit import RunConfig, runtime_environment
from training.research_data import canonical, fingerprint, input_identity
from training.research_learning import loss_terms
from training.research_targets import ACTIONS


def _linux():
    if sys.platform != "linux":
        raise ValueError("selfplay feature encoding/learning requires external Linux")


@dataclass(frozen=True)
class TrainConfig(RunConfig):
    learning_rate: float = 0.0001
    save_every: int = 128
    batch_size: int = 4

    def value(self):
        return {
            **asdict(self),
            "precision": "float32",
            "optimizer": super().value()["optimizer"],
            "sampling": "seeded permutation, homogeneous value-origin batches",
            "selection": "fixed epochs; no holdout selection",
        }


def epoch_indices(kinds, batch_size, *, seed, epoch, start_batch=0):
    if (
        type(kinds) not in (list, tuple)
        or not kinds
        or any(k not in ("terminal-v1", "bootstrap-v1") for k in kinds)
        or any(type(x) is not int for x in (batch_size, seed, epoch, start_batch))
        or not 1 <= batch_size <= 64
        or seed < 0
        or epoch < 0
        or start_batch < 0
    ):
        raise ValueError("invalid selfplay sampler configuration")
    batches = []
    for kind in sorted(set(kinds)):
        group = [i for i, k in enumerate(kinds) if k == kind]
        mixed = hashlib.sha256(
            f"selfplay-learning:{seed}:{epoch}:{kind}".encode()
        ).hexdigest()
        random.Random(int(mixed, 16)).shuffle(group)
        batches.extend(
            group[i : i + batch_size] for i in range(0, len(group), batch_size)
        )
    random.Random(
        int(hashlib.sha256(f"selfplay-batches:{seed}:{epoch}".encode()).hexdigest(), 16)
    ).shuffle(batches)
    if start_batch > len(batches):
        raise ValueError("invalid selfplay batch cursor")
    return batches[start_batch:]


@dataclass
class Samples:
    features: list
    rows: list
    provenance: dict

    @property
    def sha256(self):
        _linux()
        digest = hashlib.sha256(
            canonical({"provenance": self.provenance, "rows": self.rows}).encode()
        )
        for feature in self.features:
            if feature.shape != (729, 43) or str(feature.dtype) != "float32":
                raise ValueError("invalid feature hash input")
            digest.update(feature.tobytes(order="C"))
        return digest.hexdigest()

    @property
    def kinds(self):
        return [row["value"]["kind"] for row in self.rows]


def replay_samples(buffer, *, protected):
    _linux()
    import numpy as np
    from voxelshogi import Game

    if (
        type(protected) is not set
        or not protected
        or any(
            not isinstance(x, str) or re.fullmatch(r"[0-9a-f]{64}", x) is None
            for x in protected
        )
    ):
        raise ValueError("nonempty verified protected inputs are required")
    before = file_hash(buffer.folder / "buffer.json")
    features, rows, seen, excluded, repeated = [], [], set(), 0, 0
    for episode in buffer.episodes():
        game = Game.from_record(episode["opening"])
        for sample in episode["samples"]:
            identity = input_identity(game.snapshot())
            if identity in protected:
                excluded += 1
            else:
                if len(rows) >= 16384:
                    raise ValueError("selfplay sample memory limit exceeded")
                encoded = game.features()
                if (
                    encoded.shape != (729, 43)
                    or encoded.dtype != np.float32
                    or not np.isfinite(encoded).all()
                ):
                    raise ValueError("invalid selfplay features")
                features.append(encoded)
                rows.append(
                    {
                        "id": episode["episode_id"] + ":" + str(sample["ply"]),
                        "policy": sample["policy"],
                        "value": sample["value"],
                        "legal_actions": sample["legal_actions"],
                        "input_id": identity,
                    }
                )
                repeated += identity in seen
                seen.add(identity)
            game.play(sample["move"])
    if not rows or len({r["id"] for r in rows}) != len(rows):
        raise ValueError("no eligible selfplay samples or repeated sample IDs")
    if file_hash(buffer.folder / "buffer.json") != before:
        raise ValueError("replay changed during feature encoding")
    return Samples(
        features,
        rows,
        {
            "buffer_sha256": before,
            "protected_sha256": fingerprint(sorted(protected)),
            "excluded_protected": excluded,
            "repeated_train_inputs": repeated,
            "duplicate_policy": "retain within-train occurrences; exclude protected inputs",
        },
    )


def update_step(model, optimizer, data, indices, *, device):
    _linux()
    import numpy as np
    import torch

    if (
        not indices
        or len(set(indices)) != len(indices)
        or any(type(i) is not int or not 0 <= i < len(data.rows) for i in indices)
    ):
        raise ValueError("invalid selfplay batch indices")
    rows = [data.rows[i] for i in indices]
    kinds = {row["value"]["kind"] for row in rows}
    if len(kinds) != 1:
        raise ValueError("selfplay batches must be homogeneous in value origin")
    array = np.stack([data.features[i] for i in indices])
    if (
        array.shape != (len(indices), 729, 43)
        or array.dtype != np.float32
        or not np.isfinite(array).all()
    ):
        raise ValueError("invalid batch feature shape/dtype")
    features = torch.from_numpy(array).to(device)
    model.train()
    optimizer.zero_grad(set_to_none=True)
    logits, values = model(features)
    if logits.shape != (len(indices), ACTIONS) or values.shape != (len(indices), 1):
        raise ValueError("model selfplay output shape differs")
    kind = next(iter(kinds))
    terms = loss_terms(
        logits,
        values,
        [r["policy"] for r in rows],
        [r["value"] for r in rows],
        [r["legal_actions"] for r in rows],
        value_kind=kind,
    )
    terms["total"].backward()
    parameters = [p for p in model.parameters() if p.grad is not None]
    if not parameters or any(
        not torch.isfinite(p.grad).all().item() for p in parameters
    ):
        raise ValueError("nonfinite/missing selfplay gradients")
    try:
        norm = torch.nn.utils.clip_grad_norm_(parameters, 1.0, error_if_nonfinite=True)
    except RuntimeError as error:
        raise ValueError("nonfinite selfplay gradient norm") from error
    optimizer.step()
    return {
        "examples": len(indices),
        "policy_loss": terms["policy"].item(),
        "value_mse": terms["value"].item(),
        "loss": terms["total"].item(),
        "gradient_norm": norm.item(),
        "value_kind": kind,
    }


def _cursor(progress, kinds, config):
    if not 0 <= progress["epoch"] <= config.epochs:
        raise ValueError("invalid selfplay epoch")
    batches = epoch_indices(
        kinds, config.batch_size, seed=config.seed, epoch=progress["epoch"]
    )
    cursor = progress["next_batch"]
    if (
        not 0 <= cursor <= len(batches)
        or progress["epoch"] == config.epochs
        and cursor != 0
    ):
        raise ValueError("invalid selfplay batch cursor")
    n_batches = len(batches)
    if progress["step"] != progress["epoch"] * n_batches + cursor or progress[
        "examples"
    ] != progress["epoch"] * len(kinds) + sum(map(len, batches[:cursor])):
        raise ValueError("selfplay sampler progress differs")


def fit_samples(
    model,
    optimizer,
    data,
    folder,
    *,
    config,
    input_binding,
    resume=False,
    max_new_steps=None,
    stop_requested=lambda: False,
):
    _linux()
    import torch

    if (
        not isinstance(config, TrainConfig)
        or not isinstance(data, Samples)
        or not data.rows
        or len(data.rows) != len(data.features)
        or len({r["id"] for r in data.rows}) != len(data.rows)
        or max_new_steps is not None
        and (type(max_new_steps) is not int or max_new_steps < 1)
    ):
        raise ValueError("invalid selfplay training inputs")
    if (
        set(input_binding)
        != {"source_commit", "parent_model_sha256", "generation", "architecture"}
        or re.fullmatch(r"[0-9a-f]{40}", input_binding["source_commit"]) is None
        or re.fullmatch(r"[0-9a-f]{64}", input_binding["parent_model_sha256"]) is None
        or type(input_binding["generation"]) is not int
        or not 0 <= input_binding["generation"] < 64
        or not isinstance(input_binding["architecture"], str)
        or not input_binding["architecture"]
    ):
        raise ValueError("invalid generation/parent/source binding")
    if not isinstance(optimizer, torch.optim.AdamW) or any(
        group["lr"] != config.learning_rate
        or group["weight_decay"] != config.weight_decay
        or group["betas"] != (0.9, 0.999)
        or group["eps"] != 1e-8
        or group["foreach"] is not False
        or group["fused"] is not False
        for group in optimizer.param_groups
    ):
        raise ValueError("optimizer differs from selfplay config")
    torch.set_num_threads(config.threads)
    deterministic_runtime()
    binding = {
        "source_commit": input_binding["source_commit"],
        "cache_sha256": data.sha256,
        "config": config.value(),
        "contract": {"schema": "voxelshogi-selfplay-training-v1", **input_binding},
        "environment": runtime_environment(config),
    }
    folder = Path(folder)
    run = {"schema": "voxelshogi-training-run-v1", "binding": binding}
    if resume:
        if json.loads((folder / "run.json").read_text()) != run:
            raise ValueError("selfplay training binding differs")
        progress = load_checkpoint(
            folder / "checkpoints", model, optimizer, binding=binding
        )
    else:
        folder.mkdir(parents=True, exist_ok=False)
        atomic_json(folder / "run.json", run)
        seed_all(config.seed)
        progress = {
            "epoch": 0,
            "next_batch": 0,
            "step": 0,
            "examples": 0,
            "best_val_loss": None,
        }
        save_checkpoint(
            folder / "checkpoints", model, optimizer, progress=progress, binding=binding
        )
    _cursor(progress, data.kinds, config)
    saved = dict(progress)
    new_steps, started = 0, time.monotonic()

    def checkpoint():
        nonlocal saved
        if progress != saved:
            save_checkpoint(
                folder / "checkpoints",
                model,
                optimizer,
                progress=progress,
                binding=binding,
            )
            saved = dict(progress)

    def finish(reason):
        checkpoint()
        result = {
            "reason": reason,
            "progress": dict(progress),
            "new_steps": new_steps,
            "elapsed_seconds": time.monotonic() - started,
            "binding": binding,
        }
        atomic_json(folder / "last-attempt.json", result)
        return result

    while progress["epoch"] < config.epochs:
        batches = epoch_indices(
            data.kinds,
            config.batch_size,
            seed=config.seed,
            epoch=progress["epoch"],
            start_batch=progress["next_batch"],
        )
        for indices in batches:
            if stop_requested():
                return finish("stopped")
            if max_new_steps is not None and new_steps >= max_new_steps:
                return finish("max_steps")
            metrics = update_step(model, optimizer, data, indices, device=config.device)
            progress["next_batch"] += 1
            progress["step"] += 1
            progress["examples"] += metrics["examples"]
            new_steps += 1
            event = {
                "event": "train",
                "step": progress["step"],
                "epoch": progress["epoch"],
                "ids": [data.rows[i]["id"] for i in indices],
                "elapsed_seconds": time.monotonic() - started,
                **{k: v for k, v in metrics.items() if k != "value_kind"},
            }
            with (folder / "events.jsonl").open("a") as stream:
                stream.write(canonical(event) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            if progress["step"] % config.save_every == 0:
                checkpoint()
        progress["epoch"] += 1
        progress["next_batch"] = 0
        checkpoint()
    return finish("complete")
