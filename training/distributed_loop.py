"""Fixed global updates and measured work; tensor execution is Linux-only."""

import json
import math
import os
import sys
import time
from copy import deepcopy
from pathlib import Path

from training.distributed_training import DistributedConfig
from training.research_data import fingerprint


def seed_rank(seed, rank, device, *, random, np, torch):
    random.seed(seed + rank)
    np.random.seed((seed + rank) % 2**32)
    torch.random.default_generator.manual_seed(seed + rank)
    if device.type == "cuda":
        with torch.cuda.device(device):
            torch.cuda.manual_seed(seed + rank)


def check_cursor(progress, config):
    if (
        type(progress) is not dict
        or set(progress) != {"epoch", "next_batch", "step", "examples", "best_val_loss"}
        or any(
            type(progress[k]) is not int
            for k in ("epoch", "next_batch", "step", "examples")
        )
        or progress["epoch"] != 0
        or not 0 <= progress["step"] <= config.updates
        or progress["next_batch"] != progress["step"]
        or progress["examples"] != progress["step"] * config.global_batch
        or progress["best_val_loss"] is not None
    ):
        raise ValueError("distributed global cursor differs")


def execute_updates(
    schedule,
    progress,
    *,
    config,
    update,
    save,
    record,
    max_new_steps=None,
    stop_requested=lambda: False,
):
    """Drive supplied update/save ports; this layer never imports Torch."""
    if (
        not isinstance(config, DistributedConfig)
        or max_new_steps is not None
        and (type(max_new_steps) is not int or max_new_steps < 1)
        or schedule.get("schema") != "voxelshogi-distributed-global-schedule-v1"
        or schedule.get("global_batch") != config.global_batch
        or schedule.get("updates") != config.updates
        or schedule.get("seed") != config.seed
        or type(schedule.get("batches")) is not list
        or len(schedule["batches"]) != config.updates
        or schedule.get("order_sha256") != fingerprint(schedule["batches"])
        or any(
            type(batch) is not list
            or len(batch) != config.global_batch
            or any(type(i) is not int or i < 0 for i in batch)
            or len(set(batch)) != len(batch)
            for batch in schedule["batches"]
        )
    ):
        raise ValueError("fixed distributed work/order differs")
    check_cursor(progress, config)
    progress = deepcopy(progress)
    start_step, saved_step = progress["step"], progress["step"]
    measured_steps, measured_seconds = 0, 0.0

    def checkpoint():
        nonlocal saved_step
        if progress["step"] != saved_step:
            save(deepcopy(progress))
            saved_step = progress["step"]

    def finish(reason):
        checkpoint()
        eligible = (
            start_step == 0
            and reason == "complete"
            and progress["step"] == config.updates
        )
        return {
            "reason": reason,
            "progress": deepcopy(progress),
            "new_steps": progress["step"] - start_step,
            "measured_updates": measured_steps,
            "measured_examples": measured_steps * config.global_batch,
            "measured_seconds": measured_seconds,
            "continuous_primary_eligible": eligible,
            "examples_per_second": measured_steps
            * config.global_batch
            / measured_seconds
            if eligible
            else None,
        }

    for index in range(start_step, config.updates):
        if stop_requested():
            return finish("stopped")
        if max_new_steps is not None and progress["step"] - start_step >= max_new_steps:
            return finish("max_steps")
        metrics = update(list(schedule["batches"][index]), index + 1)
        if (
            type(metrics) is not dict
            or type(metrics.get("examples")) is not int
            or metrics["examples"] != config.global_batch
            or type(metrics.get("elapsed_seconds")) not in (int, float)
            or not math.isfinite(metrics["elapsed_seconds"])
            or metrics["elapsed_seconds"] <= 0
            or type(metrics.get("loss")) not in (int, float)
            or not math.isfinite(metrics["loss"])
        ):
            raise ValueError("distributed update work or measurement differs")
        progress.update(
            step=index + 1,
            next_batch=index + 1,
            examples=(index + 1) * config.global_batch,
        )
        measured = index + 1 > config.warmup_updates
        if measured:
            measured_steps += 1
            measured_seconds += metrics["elapsed_seconds"]
        record(
            {
                "global_step": index + 1,
                "indices": list(schedule["batches"][index]),
                "measured": measured,
                **metrics,
            }
        )
        if progress["step"] in (config.resume_at, config.updates):
            checkpoint()
    return finish("complete")


def fit_schedule(
    model,
    optimizer,
    data,
    folder,
    *,
    config,
    input_binding,
    rank,
    world_size,
    resume=False,
    max_new_steps=None,
    stop_requested=lambda: False,
):
    """Run actual FP32 updates with collective stop, timing and state boundaries."""
    if sys.platform != "linux":
        raise ValueError("distributed training requires external Linux")
    import fcntl
    import random

    import numpy as np
    import torch

    from training.checkpoint import atomic_json, deterministic_runtime
    from training.distributed_benchmark import global_schedule
    from training.distributed_training import (
        REDUCTION,
        _process_group,
        _raw_model,
        distributed_update,
        enable_rank_ordered_reduction,
        load_distributed_checkpoint,
        save_distributed_checkpoint,
        validate_distributed_binding,
    )
    from training.fit import runtime_environment
    from training.selfplay_training import Samples

    dist = _process_group(rank, world_size)

    def rank0_io(call):
        status = [None]
        if rank == 0:
            try:
                call()
                status[0] = {"success": True}
            except Exception as error:
                status[0] = {"error_type": type(error).__name__}
        if dist is not None:
            dist.broadcast_object_list(status, src=0)
        if status[0] != {"success": True}:
            raise ValueError("rank0 distributed IO failed: " + status[0]["error_type"])

    def collective_check(call):
        try:
            value, error = call(), None
        except Exception as problem:
            value, error = None, type(problem).__name__
        errors = [error]
        if dist is not None:
            errors = [None] * world_size
            dist.all_gather_object(errors, error)
        if any(e is not None for e in errors):
            raise ValueError("distributed preflight failed: " + str(errors))
        return value

    def preflight():
        if (
            not isinstance(config, DistributedConfig)
            or type(resume) is not bool
            or not isinstance(data, Samples)
            or not data.rows
            or len(data.rows) != len(data.features)
            or len({r["id"] for r in data.rows}) != len(data.rows)
            or type(input_binding) is not dict
            or set(input_binding)
            != {"source_commit", "initial_model_sha256", "architecture"}
            or max_new_steps is not None
            and (type(max_new_steps) is not int or max_new_steps < 1)
        ):
            raise ValueError("invalid distributed input/configuration")
        raw = _raw_model(model, world_size)
        enable_rank_ordered_reduction(model, rank=rank, world_size=world_size)
        parameters = list(raw.parameters())
        if not parameters or any(
            p.dtype != torch.float32 or p.device.type != config.device
            for p in parameters
        ):
            raise ValueError("distributed model precision/device differs")
        device = parameters[0].device
        if (
            any(p.device != device for p in parameters)
            or device.type == "cuda"
            and device.index != rank
        ):
            raise ValueError("model device differs from assigned local rank")
        if not isinstance(optimizer, torch.optim.AdamW) or any(
            group["lr"] != config.learning_rate
            or group["weight_decay"] != config.weight_decay
            or group["betas"] != (0.9, 0.999)
            or group["eps"] != 1e-8
            or group["foreach"] is not False
            or group["fused"] is not False
            for group in optimizer.param_groups
        ):
            raise ValueError("optimizer differs from explicit distributed config")
        torch.set_num_threads(config.threads)
        deterministic_runtime()
        schedule = global_schedule(
            data.kinds,
            global_batch=config.global_batch,
            updates=config.updates,
            seed=config.seed,
        )
        binding = {
            "source_commit": input_binding["source_commit"],
            "cache_sha256": data.sha256,
            "config": config.value(),
            "environment": runtime_environment(config),
            "contract": {
                "schema": "voxelshogi-distributed-training-v2",
                "gradient_reduction": REDUCTION,
                **input_binding,
                "world_size": world_size,
                "schedule_sha256": schedule["order_sha256"],
            },
        }
        validate_distributed_binding(binding)
        return device, schedule, binding

    device, schedule, binding = collective_check(preflight)
    fingerprints = [fingerprint(binding)]
    if dist is not None:
        fingerprints = [None] * world_size
        dist.all_gather_object(fingerprints, fingerprint(binding))
    if len(set(fingerprints)) != 1:
        raise ValueError("distributed rank input/configuration bindings differ")
    folder = Path(folder)
    lease = None

    def acquire():
        nonlocal lease
        folder.parent.mkdir(parents=True, exist_ok=True)
        path = folder.parent / ("." + folder.name + ".distributed.lock")
        if folder.is_symlink() or path.is_symlink():
            raise ValueError("symlink distributed run/lock")
        lease = path.open("a")
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)

    try:
        rank0_io(acquire)
        run = {"schema": "voxelshogi-training-run-v1", "binding": binding}
        if resume:

            def check_saved():
                if json.loads((folder / "run.json").read_text()) != run:
                    raise ValueError("distributed saved run binding differs")

            rank0_io(check_saved)
            progress = collective_check(
                lambda: load_distributed_checkpoint(
                    folder / "checkpoints",
                    model,
                    optimizer,
                    binding=binding,
                    rank=rank,
                    world_size=world_size,
                )
            )
        else:

            def create():
                folder.mkdir(exist_ok=False)
                atomic_json(folder / "run.json", run)
                atomic_json(folder / "schedule.json", schedule)

            rank0_io(create)
            seed_rank(config.seed, rank, device, random=random, np=np, torch=torch)
            progress = {
                "epoch": 0,
                "next_batch": 0,
                "step": 0,
                "examples": 0,
                "best_val_loss": None,
            }
            save_distributed_checkpoint(
                folder / "checkpoints",
                model,
                optimizer,
                progress=progress,
                binding=binding,
                rank=rank,
                world_size=world_size,
            )
        collective_check(lambda: check_cursor(progress, config))

        def save(progress):
            save_distributed_checkpoint(
                folder / "checkpoints",
                model,
                optimizer,
                progress=progress,
                binding=binding,
                rank=rank,
                world_size=world_size,
            )

        def synchronize():
            if device.type == "cuda":
                torch.cuda.synchronize(device)

        def maximum(value):
            tensor = torch.tensor(value, device=device, dtype=torch.float64)
            if dist is not None:
                dist.all_reduce(tensor, op=dist.ReduceOp.MAX)
            return tensor.item()

        def stopped():
            return maximum(float(bool(stop_requested()))) != 0

        def update(batch, _step):
            if dist is not None:
                dist.barrier()
            synchronize()
            started = time.monotonic()
            metrics = distributed_update(
                model,
                optimizer,
                data,
                batch,
                device=device,
                rank=rank,
                world_size=world_size,
            )
            synchronize()
            return {**metrics, "elapsed_seconds": maximum(time.monotonic() - started)}

        synchronize()
        if device.type == "cuda":
            torch.cuda.reset_peak_memory_stats(device)
        window = {
            "start": time.monotonic()
            if progress["step"] >= config.warmup_updates
            else None,
            "end": None,
        }

        def record(event):
            def write():
                with (folder / "events.jsonl").open("a") as stream:
                    stream.write(
                        json.dumps(event, sort_keys=True, allow_nan=False) + "\n"
                    )
                    stream.flush()
                    os.fsync(stream.fileno())

            rank0_io(write)
            if event["global_step"] == config.warmup_updates:
                synchronize()
                if device.type == "cuda":
                    torch.cuda.reset_peak_memory_stats(device)
                window["start"] = time.monotonic()
            if event["global_step"] == config.updates:
                window["end"] = time.monotonic()

        started = time.monotonic()
        result = execute_updates(
            schedule,
            progress,
            config=config,
            update=update,
            save=save,
            record=record,
            max_new_steps=max_new_steps,
            stop_requested=stopped,
        )
        wall = maximum(time.monotonic() - started)
        window_seconds = (
            maximum(window["end"] - window["start"])
            if window["start"] is not None and window["end"] is not None
            else None
        )
        memory = {
            "rank": rank,
            "device": str(device),
            "peak_allocated_bytes": torch.cuda.max_memory_allocated(device)
            if device.type == "cuda"
            else None,
            "peak_reserved_bytes": torch.cuda.max_memory_reserved(device)
            if device.type == "cuda"
            else None,
        }
        memories = [memory]
        if dist is not None:
            memories = [None] * world_size
            dist.all_gather_object(memories, memory)
        result.update(
            binding=binding,
            rank_memory=memories,
            attempt_wall_seconds=wall,
            measured_window_seconds=window_seconds,
            update_examples_per_second=result["examples_per_second"],
            examples_per_second=result["measured_examples"] / window_seconds
            if result["continuous_primary_eligible"]
            else None,
            timing_scope="max-rank synchronized update intervals separately from the post-warmup wall window; wall includes interior checkpoint and event IO, excludes final checkpoint; resume-check attempts are not primary throughput",
            memory_scope="per-rank Torch peak allocation/reservation for this attempt, reset after warmup when crossed; not whole-device VRAM",
        )
        rank0_io(lambda: atomic_json(folder / "last-attempt.json", result))
        return result
    finally:
        if lease is not None:
            lease.close()


def communication_probe(model, *, device, rank, world_size, warmup=5, repeats=20):
    """Time an isolated gradient-sized collective, never a DDP time fraction."""
    if sys.platform != "linux":
        raise ValueError("communication probe requires external Linux")
    import torch

    from training.distributed_training import _process_group, _raw_model

    if (
        type(warmup) is not int
        or not 0 <= warmup <= 100
        or type(repeats) is not int
        or not 1 <= repeats <= 1000
    ):
        raise ValueError("bounded communication probe counts required")
    dist = _process_group(rank, world_size)
    parameters = list(_raw_model(model, world_size).parameters())
    requested = torch.device(device)
    if not parameters:
        raise ValueError("model parameters required for communication size")
    actual = parameters[0].device
    count = sum(p.numel() for p in parameters)
    if (
        not 1 <= count <= 100_000_000
        or requested.type != actual.type
        or requested.index is not None
        and requested.index != actual.index
        or any(p.device != actual or p.dtype != torch.float32 for p in parameters)
    ):
        raise ValueError("communication model/device/precision differs")
    result = {
        "world_size": world_size,
        "tensor_bytes": count * 4,
        "warmup": warmup,
        "repeats": repeats,
        "collective": "all-reduce-sum" if world_size > 1 else "none-single-rank",
        "timings_seconds": [],
        "max_rank_mean_seconds": None,
        "verified_sum": world_size,
        "scope": "isolated synchronous FP32 all-reduce with model-gradient byte count; excludes fill/check/barrier/measurement-reduction; not end-to-end DDP communication fraction",
    }
    if world_size == 1:
        return result
    buffer = torch.empty(count, dtype=torch.float32, device=actual)

    def synchronize():
        if actual.type == "cuda":
            torch.cuda.synchronize(actual)

    for step in range(warmup + repeats):
        buffer.fill_(1)
        synchronize()
        dist.barrier()
        started = time.monotonic()
        dist.all_reduce(buffer, op=dist.ReduceOp.SUM)
        synchronize()
        elapsed = time.monotonic() - started
        if not torch.all(buffer == float(world_size)).item():
            raise ValueError("collective differs from independent sum of rank ones")
        maximum = torch.tensor(elapsed, dtype=torch.float64, device=actual)
        dist.all_reduce(maximum, op=dist.ReduceOp.MAX)
        if step >= warmup:
            result["timings_seconds"].append(maximum.item())
    result["max_rank_mean_seconds"] = sum(result["timings_seconds"]) / repeats
    return result
