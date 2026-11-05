"""Fixed-update four-structure training from admitted legal visit distributions.

Execution is external Linux only. This is a training consumer, not corpus
admission or a claim that bootstrap labels are game outcomes. The driver must
verify fixed Hub bytes, replay and admission before supplying these samples.
"""

import hashlib
import json
import math
import os
import re
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from export.research_contract import ResearchConfig, architecture_config
from training.checkpoint import atomic_json, load_checkpoint, save_checkpoint, seed_all
from training.fit import RunConfig, runtime_environment
from training.research_data import canonical
from training.selfplay_training import Samples, epoch_indices

SCHEMA = "voxelshogi-research-visit-training-config-v1"


def _linux():
    if sys.platform != "linux":
        raise ValueError("research visit training requires external Linux")


def _sha(value, length=64):
    return (
        isinstance(value, str)
        and re.fullmatch(f"[0-9a-f]{{{length}}}", value) is not None
    )


@dataclass(frozen=True)
class VisitRunConfig:
    architecture: ResearchConfig = field(
        default_factory=lambda: architecture_config("full")
    )
    seed: int = 67003
    total_updates: int = 128
    batch_size: int = 4
    learning_rate: float = 0.0001
    weight_decay: float = 0.01
    save_every: int = 128
    validate_every: int = 128
    threads: int = 1
    device: str = "cuda"

    def __post_init__(self):
        RunConfig(
            **{
                k: getattr(self, k)
                for k in (
                    "seed",
                    "batch_size",
                    "learning_rate",
                    "weight_decay",
                    "save_every",
                    "threads",
                    "device",
                )
            }
        )
        if type(self.architecture) is not ResearchConfig or any(
            type(n) is not int or not 1 <= n <= 1_000_000
            for n in (self.total_updates, self.validate_every)
        ):
            raise ValueError("invalid research visit architecture/update limits")

    def value(self):
        return {
            **asdict(self),
            "schema": SCHEMA,
            "precision": "float32",
            "policy_target": "completed legal visit distribution",
            "selection": "fixed val at update intervals and final update",
            "optimizer": RunConfig().value()["optimizer"],
        }

    @classmethod
    def from_value(cls, value):
        try:
            c = cls(
                **{
                    k: value[k] for k in cls.__dataclass_fields__ if k != "architecture"
                },
                architecture=ResearchConfig(**value["architecture"]),
            )
            if c.value() != value:
                raise ValueError("visit config differs")
            return c
        except (KeyError, TypeError) as error:
            raise ValueError("visit config differs") from error


def validate_binding(binding):
    if (
        type(binding) is not dict
        or set(binding)
        != {"source_commit", "cache_sha256", "config", "contract", "environment"}
        or not _sha(binding["source_commit"], 40)
        or not _sha(binding["cache_sha256"])
        or type(binding["contract"]) is not dict
        or set(binding["contract"]) != {"schema", "admission_sha256"}
        or binding["contract"]["schema"] != "voxelshogi-research-visit-training-v1"
        or not _sha(binding["contract"]["admission_sha256"])
        or type(binding["environment"]) is not dict
    ):
        raise ValueError("visit resume source/admission binding differs")
    c = VisitRunConfig.from_value(binding["config"])
    if binding["environment"].get("device") != c.device:
        raise ValueError("visit resume environment binding differs")


@dataclass
class VisitCorpus:
    train: Samples
    val: Samples
    admission_sha256: str

    def digest(self, config):
        _linux()
        import numpy as np

        if not _sha(self.admission_sha256):
            raise ValueError("verified admission hash required")
        digest = hashlib.sha256(self.admission_sha256.encode())
        inputs, families = set(), set()
        for name in ("train", "val"):
            part = getattr(self, name)
            if (
                not isinstance(part, Samples)
                or not part.rows
                or len(part.rows) != len(part.features)
            ):
                raise ValueError("nonempty admitted visit splits required")
            here, here_families, ids = set(), set(), set()
            digest.update(
                canonical(
                    {"split": name, "rows": part.rows, "provenance": part.provenance}
                ).encode()
            )
            for row, features in zip(part.rows, part.features, strict=True):
                if (
                    set(row)
                    != {"id", "input_id", "family", "policy", "value", "legal_actions"}
                    or not isinstance(row["id"], str)
                    or not row["id"]
                    or row["id"] in ids
                    or not _sha(row["input_id"])
                    or row["input_id"] in here
                    or row["input_id"] in inputs
                    or not _sha(row["family"])
                    or row["family"] in families
                    or row["value"].get("kind") not in ("terminal-v1", "bootstrap-v1")
                    or features.shape != (config.architecture.side**3, 43)
                    or features.dtype != np.float32
                    or not np.isfinite(features).all()
                ):
                    raise ValueError(
                        "visit samples/feature shape or split isolation differ"
                    )
                ids.add(row["id"])
                here.add(row["input_id"])
                here_families.add(row["family"])
                digest.update(features.tobytes(order="C"))
            inputs.update(here)
            families.update(here_families)
        return digest.hexdigest()


def validate_progress(progress, kinds, config):
    batches = epoch_indices(kinds, config.batch_size, seed=config.seed, epoch=0)
    n = len(batches)
    step = progress["step"]
    epoch, cursor = divmod(step, n)
    current = epoch_indices(kinds, config.batch_size, seed=config.seed, epoch=epoch)
    expected = epoch * len(kinds) + sum(map(len, current[:cursor]))
    if (
        type(step) is not int
        or not 0 <= step <= config.total_updates
        or progress["epoch"] != epoch
        or progress["next_batch"] != cursor
        or progress["examples"] != expected
    ):
        raise ValueError("fixed-update sampler progress differs")


def validate_history(events, config, progress):
    """Allow only typed metrics/IDs, and require all scheduled validation events."""
    c = VisitRunConfig.from_value(config)
    step, validations = 0, set()
    if type(events) is not list:
        raise ValueError("visit history must be a list")
    for event in events:
        if type(event) is not dict:
            raise ValueError("visit history event must be an object")
        kind = event.get("event")
        if kind == "train":
            if (
                set(event) != {"event", "step", "ids", "loss"}
                or type(event["step"]) is not int
                or event["step"] != step + 1
                or event["step"] > c.total_updates
                or type(event["ids"]) is not list
                or not 1 <= len(event["ids"]) <= c.batch_size
                or any(not isinstance(x, str) or not x for x in event["ids"])
                or len(set(event["ids"])) != len(event["ids"])
                or type(event["loss"]) not in (int, float)
                or not math.isfinite(event["loss"])
                or event["loss"] < 0
            ):
                raise ValueError("visit training history differs")
            step += 1
        elif kind == "val":
            if (
                set(event)
                != {
                    "event",
                    "step",
                    "policy_ce",
                    "value_mse",
                    "loss",
                    "examples",
                    "value_origins",
                }
                or type(event["step"]) is not int
                or event["step"] != step
                or step in validations
                or step == 0
                or step % c.validate_every != 0
                and step != c.total_updates
                or type(event["examples"]) is not int
                or event["examples"] < 1
                or type(event["value_origins"]) is not dict
                or not event["value_origins"]
                or any(
                    k not in ("terminal-v1", "bootstrap-v1")
                    or type(v) is not int
                    or v < 1
                    for k, v in event["value_origins"].items()
                )
                or sum(event["value_origins"].values()) != event["examples"]
                or any(
                    type(event[k]) not in (int, float)
                    or not math.isfinite(event[k])
                    or event[k] < 0
                    for k in ("policy_ce", "value_mse", "loss")
                )
                or not math.isclose(
                    event["loss"],
                    event["policy_ce"] + event["value_mse"],
                    rel_tol=1e-6,
                    abs_tol=1e-7,
                )
            ):
                raise ValueError("visit validation history differs")
            validations.add(step)
        else:
            raise ValueError("unknown visit history event")
    expected = set(range(c.validate_every, step + 1, c.validate_every))
    if step == c.total_updates:
        expected.add(step)
    if validations != expected or progress is not None and progress["step"] != step:
        raise ValueError("visit history checkpoint/scheduled validation differs")


def _terms(model, data, indices, config):
    import numpy as np
    import torch

    from training.research_learning import loss_terms

    rows = [data.rows[i] for i in indices]
    features = torch.from_numpy(np.stack([data.features[i] for i in indices])).to(
        config.device
    )
    logits, values = model(features)
    tokens = config.architecture.side**3
    if logits.shape != (
        len(indices),
        2 * tokens * tokens + 7 * tokens,
    ) or values.shape != (len(indices), 1):
        raise ValueError("research visit output shape differs")
    kinds = {r["value"]["kind"] for r in rows}
    if len(kinds) != 1:
        raise ValueError("visit batch mixes value origins")
    return loss_terms(
        logits,
        values,
        [r["policy"] for r in rows],
        [r["value"] for r in rows],
        [r["legal_actions"] for r in rows],
        value_kind=next(iter(kinds)),
    )


def evaluate_visits(model, data, config):
    _linux()
    import torch

    totals = {"policy_ce": 0.0, "value_mse": 0.0, "loss": 0.0}
    model.eval()
    with torch.no_grad():
        for indices in epoch_indices(data.kinds, config.batch_size, seed=0, epoch=0):
            terms = _terms(model, data, indices, config)
            for name, key in (
                ("policy_ce", "policy"),
                ("value_mse", "value"),
                ("loss", "total"),
            ):
                totals[name] += terms[key].item() * len(indices)
    totals = {k: v / len(data.rows) for k, v in totals.items()}
    if any(not math.isfinite(v) for v in totals.values()):
        raise ValueError("nonfinite visit validation")
    return {
        **totals,
        "examples": len(data.rows),
        "value_origins": dict(Counter(data.kinds)),
    }


def fit_visits(
    data,
    folder,
    *,
    config,
    source_commit,
    resume=False,
    max_new_steps=None,
    stop_requested=lambda: False,
):
    _linux()
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    import torch

    from export.research_model import make_research_model

    if (
        type(config) is not VisitRunConfig
        or type(data) is not VisitCorpus
        or not _sha(source_commit, 40)
    ):
        raise ValueError("research visit config/corpus/source required")
    if max_new_steps is not None and (
        type(max_new_steps) is not int or max_new_steps < 1
    ):
        raise ValueError("max_new_steps bounds one attempt only")
    torch.set_num_threads(config.threads)
    seed_all(config.seed)
    binding = {
        "source_commit": source_commit,
        "cache_sha256": data.digest(config),
        "config": config.value(),
        "contract": {
            "schema": "voxelshogi-research-visit-training-v1",
            "admission_sha256": data.admission_sha256,
        },
        "environment": runtime_environment(config),
    }
    validate_binding(binding)
    folder = Path(folder)
    run = {"schema": "voxelshogi-training-run-v1", "binding": binding}
    if resume and json.loads((folder / "run.json").read_text()) != run:
        raise ValueError("visit training binding differs")
    model = make_research_model(config.architecture, seed=config.seed).to(config.device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
        betas=(0.9, 0.999),
        eps=1e-8,
        foreach=False,
        fused=False,
    )
    if resume:
        progress = load_checkpoint(
            folder / "checkpoints", model, optimizer, binding=binding
        )
    else:
        folder.mkdir(parents=True, exist_ok=False)
        atomic_json(folder / "run.json", run)
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
    validate_progress(progress, data.train.kinds, config)
    new_steps, started = 0, time.monotonic()

    def event(value):
        with (folder / "events.jsonl").open("a") as stream:
            stream.write(canonical(value) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def checkpoint(best=False):
        save_checkpoint(
            folder / "checkpoints",
            model,
            optimizer,
            progress=progress,
            binding=binding,
            best=best,
        )

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

    while progress["step"] < config.total_updates:
        if stop_requested():
            return finish("stopped")
        if max_new_steps is not None and new_steps >= max_new_steps:
            return finish("max_new_steps")
        batches = epoch_indices(
            data.train.kinds,
            config.batch_size,
            seed=config.seed,
            epoch=progress["epoch"],
        )
        indices = batches[progress["next_batch"]]
        model.train()
        optimizer.zero_grad(set_to_none=True)
        terms = _terms(model, data.train, indices, config)
        terms["total"].backward()
        parameters = [p for p in model.parameters() if p.grad is not None]
        if not parameters or any(
            not torch.isfinite(p.grad).all().item() for p in parameters
        ):
            raise ValueError("nonfinite/missing research visit gradients")
        torch.nn.utils.clip_grad_norm_(parameters, 1.0, error_if_nonfinite=True)
        optimizer.step()
        progress["step"] += 1
        progress["examples"] += len(indices)
        progress["epoch"], progress["next_batch"] = divmod(
            progress["step"], len(batches)
        )
        new_steps += 1
        event(
            {
                "event": "train",
                "step": progress["step"],
                "ids": [data.train.rows[i]["id"] for i in indices],
                "loss": terms["total"].item(),
            }
        )
        if (
            progress["step"] % config.validate_every == 0
            or progress["step"] == config.total_updates
        ):
            metrics = evaluate_visits(model, data.val, config)
            improved = (
                progress["best_val_loss"] is None
                or metrics["loss"] < progress["best_val_loss"]
            )
            if improved:
                progress["best_val_loss"] = metrics["loss"]
            event({"event": "val", "step": progress["step"], **metrics})
            checkpoint(best=improved)
        elif progress["step"] % config.save_every == 0:
            checkpoint()
    return finish("complete")
