"""Deterministic FP32 supervised learning and resumable val selection on Linux."""

import argparse
import json
import math
import os
import platform
import re
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from training.checkpoint import (
    atomic_json,
    deterministic_runtime,
    load_checkpoint,
    save_checkpoint,
    seed_all,
)
from training.feature_cache import FeatureCache, canonical, file_hash
from training.learning import evaluate_model, train_step
from training.supervision import ROOT, label_contract


@dataclass(frozen=True)
class RunConfig:
    seed: int = 314159
    epochs: int = 1
    batch_size: int = 1
    learning_rate: float = 0.0003
    weight_decay: float = 0.01
    save_every: int = 100
    threads: int = 2
    device: str = "cuda"

    def __post_init__(self):
        for key, low, high in (
            ("seed", 0, 2**63 - 1),
            ("epochs", 1, 1000),
            ("batch_size", 1, 64),
            ("save_every", 1, 100000),
            ("threads", 1, 64),
        ):
            value = getattr(self, key)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"invalid training {key}")
        for key, low, high in (("learning_rate", 0, 1), ("weight_decay", 0, 1)):
            value = getattr(self, key)
            if (
                type(value) not in (int, float)
                or not math.isfinite(value)
                or not low <= value <= high
                or (key == "learning_rate" and value == 0)
            ):
                raise ValueError(f"invalid training {key}")
        if self.device not in ("cpu", "cuda"):
            raise ValueError("only external Linux CPU/CUDA is supported")

    def value(self):
        return {
            **asdict(self),
            "precision": "float32",
            "selection_split": "val",
            "optimizer": {
                "name": "AdamW",
                "betas": [0.9, 0.999],
                "eps": 1e-8,
                "foreach": False,
                "fused": False,
            },
        }


def runtime_environment(config):
    import torch

    environment = {
        "python": platform.python_version(),
        "machine": platform.machine(),
        "torch": str(torch.__version__),
        "device": config.device,
        "lock_sha256": file_hash(ROOT / "uv.lock"),
        "deterministic": True,
        "tf32": False,
    }
    if config.device == "cuda":
        if not torch.cuda.is_available():
            raise ValueError("CUDA requested but unavailable; do not fall back to CPU")
        environment["cuda_lock_sha256"] = file_hash(
            ROOT / "infrastructure/cuda/uv.lock"
        )
        environment.update(
            cuda=torch.version.cuda,
            cudnn=torch.backends.cudnn.version(),
            gpu=torch.cuda.get_device_name(0),
            capability=list(torch.cuda.get_device_capability(0)),
        )
    else:
        environment["cpu"] = next(
            (
                line.split(":", 1)[1].strip()
                for line in Path("/proc/cpuinfo").read_text().splitlines()
                if line.startswith("model name")
            ),
            "unknown",
        )
    return environment


def _check_cursor(progress, count, config):
    batches = (count + config.batch_size - 1) // config.batch_size
    epoch, cursor = progress["epoch"], progress["next_batch"]
    if (
        not 0 <= epoch <= config.epochs
        or not 0 <= cursor <= batches
        or (epoch == config.epochs and cursor != 0)
        or progress["step"] != epoch * batches + cursor
        or progress["examples"]
        != epoch * count + min(cursor * config.batch_size, count)
    ):
        raise ValueError("checkpoint sampler cursor/step differs")


def fit(
    model,
    optimizer,
    cache,
    folder,
    *,
    config,
    source_commit,
    resume=False,
    max_new_steps=None,
    stop_requested=lambda: False,
):
    if sys.platform != "linux":
        raise ValueError("learning runs require external Linux")
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    import torch

    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("source must be a full commit")
    if max_new_steps is not None and (
        type(max_new_steps) is not int or max_new_steps < 1
    ):
        raise ValueError("max_new_steps must be positive")
    if not isinstance(optimizer, torch.optim.AdamW) or any(
        group["lr"] != config.learning_rate
        or group["weight_decay"] != config.weight_decay
        or group["betas"] != (0.9, 0.999)
        or group["eps"] != 1e-8
        or group["foreach"] is not False
        or group["fused"] is not False
        for group in optimizer.param_groups
    ):
        raise ValueError("optimizer differs from explicit run config")
    torch.set_num_threads(config.threads)
    deterministic_runtime()
    binding = {
        "source_commit": source_commit,
        "cache_sha256": cache.sha256,
        "config": config.value(),
        "contract": label_contract(),
        "environment": runtime_environment(config),
    }
    folder = Path(folder)
    if resume:
        if json.loads((folder / "run.json").read_text()) != {
            "schema": "voxelshogi-training-run-v1",
            "binding": binding,
        }:
            raise ValueError("run binding differs")
        progress = load_checkpoint(
            folder / "checkpoints", model, optimizer, binding=binding
        )
    else:
        folder.mkdir(parents=True, exist_ok=False)
        atomic_json(
            folder / "run.json",
            {"schema": "voxelshogi-training-run-v1", "binding": binding},
        )
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
    count = cache.manifest["audit"]["counts"]["teacher_splits"]["train"]
    _check_cursor(progress, count, config)
    saved = dict(progress)
    started, new_steps, attempt = time.monotonic(), 0, uuid.uuid4().hex

    def event(kind, **fields):
        with (folder / "events.jsonl").open("a") as stream:
            stream.write(
                canonical(
                    {
                        "event": kind,
                        "attempt": attempt,
                        "step": progress["step"],
                        "elapsed_seconds": time.monotonic() - started,
                        **fields,
                    }
                )
                + "\n"
            )
            stream.flush()
            os.fsync(stream.fileno())

    def checkpoint(best=False):
        nonlocal saved
        if progress != saved or best:
            save_checkpoint(
                folder / "checkpoints",
                model,
                optimizer,
                progress=progress,
                binding=binding,
                best=best,
            )
            saved = dict(progress)

    def finish(reason):
        checkpoint()
        report = {
            "reason": reason,
            "progress": dict(progress),
            "new_steps": new_steps,
            "elapsed_seconds": time.monotonic() - started,
        }
        atomic_json(folder / "last-attempt.json", report)
        event("finish", reason=reason)
        return report

    if stop_requested():
        return finish("stopped")
    while progress["epoch"] < config.epochs:
        for batch in cache.batches(
            "train",
            batch_size=config.batch_size,
            seed=config.seed,
            epoch=progress["epoch"],
            start_batch=progress["next_batch"],
        ):
            if stop_requested():
                return finish("stopped")
            if max_new_steps is not None and new_steps >= max_new_steps:
                return finish("max_steps")
            metrics = train_step(model, optimizer, batch.to(config.device))
            progress["next_batch"] += 1
            progress["step"] += 1
            progress["examples"] += metrics["examples"]
            new_steps += 1
            event("train", epoch=progress["epoch"], ids=list(batch.ids), **metrics)
            if progress["step"] % config.save_every == 0:
                checkpoint()

        def validation_batches():
            for batch in cache.batches(
                "val", batch_size=config.batch_size, seed=config.seed
            ):
                if stop_requested():
                    raise InterruptedError("validation interrupted before completion")
                yield batch.to(config.device)

        try:
            metrics = evaluate_model(model, validation_batches(), split="val")
        except InterruptedError:
            return finish("stopped")
        event("validation", epoch=progress["epoch"], **metrics)
        improved = (
            progress["best_val_loss"] is None
            or metrics["loss"] < progress["best_val_loss"]
        )
        if improved:
            progress["best_val_loss"] = metrics["loss"]
        progress["epoch"] += 1
        progress["next_batch"] = 0
        checkpoint(best=improved)
    return finish("complete")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cache", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-new-steps", type=int)
    parser.add_argument("--max-seconds", type=float, required=True)
    args = parser.parse_args()
    if sys.platform != "linux":
        parser.error("run only on external Linux")
    if not math.isfinite(args.max_seconds) or args.max_seconds < 1:
        parser.error("positive finite --max-seconds is required")
    if not args.output.resolve().is_relative_to(ROOT / "runs"):
        parser.error("private run output must remain under ignored runs/ on Linux")
    started = time.monotonic()
    config = RunConfig(**json.loads(args.config.read_text()))
    if subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip():
        parser.error("training requires clean, committed source")
    source = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    import torch

    from export.model import make_model

    seed_all(config.seed)
    torch.set_num_threads(config.threads)
    cache = FeatureCache(args.cache)
    model = make_model(config.seed).to(config.device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
        betas=(0.9, 0.999),
        eps=1e-8,
        foreach=False,
        fused=False,
    )
    stopping = False

    def request_stop(_signal, _frame):
        nonlocal stopping
        stopping = True

    previous = {
        sig: signal.signal(sig, request_stop) for sig in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        report = fit(
            model,
            optimizer,
            cache,
            args.output,
            config=config,
            source_commit=source,
            resume=args.resume,
            max_new_steps=args.max_new_steps,
            stop_requested=lambda: (
                stopping or time.monotonic() - started >= args.max_seconds
            ),
        )
        print(canonical(report), flush=True)
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    main()
