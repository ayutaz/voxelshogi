"""Real-data CUDA updates, drift-checked restart, and resource observations."""

import argparse
import gc
import json
import math
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from training.checkpoint import atomic_json, checkpoint_receipt, seed_all
from training.cuda_preflight import (
    collect_facts,
    kernel_probe,
    validate_environment_files,
)
from training.feature_cache import FeatureCache
from training.fit import RunConfig, fit
from training.supervision import ROOT

ATOL, RTOL = 1e-6, 1e-5


def compare_trees(expected, actual, *, atol=ATOL, rtol=RTOL):
    """Floating states within declared tolerance; counters and RNG are exact."""
    import torch

    result = {"floating_values": 0, "maximum_absolute_error": 0.0}

    def visit(left, right, path=()):
        if type(left) is not type(right):
            raise ValueError(f"resume state types differ: {path}")
        if isinstance(left, torch.Tensor):
            if left.shape != right.shape or left.dtype != right.dtype:
                raise ValueError(f"resume tensor shapes/dtypes differ: {path}")
            if not torch.is_floating_point(left) or (path and path[-1] == "step"):
                if not torch.equal(left, right):
                    raise ValueError(f"resume integer/counter/RNG differs: {path}")
            else:
                if (
                    not torch.isfinite(left).all()
                    or not torch.isfinite(right).all()
                    or not torch.allclose(right, left, atol=atol, rtol=rtol)
                ):
                    raise ValueError(f"resume floating tensors differ: {path}")
                result["floating_values"] += left.numel()
                if left.numel():
                    result["maximum_absolute_error"] = max(
                        result["maximum_absolute_error"],
                        (right - left).abs().max().item(),
                    )
        elif isinstance(left, dict):
            if left.keys() != right.keys():
                raise ValueError(f"resume state keys differ: {path}")
            for key in left:
                visit(left[key], right[key], (*path, key))
        elif isinstance(left, (list, tuple)):
            if len(left) != len(right):
                raise ValueError(f"resume state lengths differ: {path}")
            for index, (a, b) in enumerate(zip(left, right, strict=True)):
                visit(a, b, (*path, index))
        elif type(left) is float:
            if (
                not math.isfinite(left)
                or not math.isfinite(right)
                or abs(right - left) > atol + rtol * abs(left)
            ):
                raise ValueError(f"resume scalars differ: {path}")
        elif left != right:
            raise ValueError(f"resume metadata differs: {path}")

    visit(expected, actual)
    return result


class ResourceSamples:
    """Local GPU-process observations; no cloud API polling or credentials."""

    def __init__(self):
        self.stop, self.samples = threading.Event(), []

    def _sample(self):
        import psutil

        while not self.stop.is_set():
            sample = {
                "monotonic": time.monotonic(),
                "rss_bytes": psutil.Process().memory_info().rss,
            }
            try:
                raw = subprocess.run(
                    [
                        "nvidia-smi",
                        "--query-gpu=utilization.gpu,memory.used",
                        "--format=csv,noheader,nounits",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=True,
                ).stdout.strip()
                utilization, memory = (int(part.strip()) for part in raw.split(","))
                sample.update(utilization_percent=utilization, memory_used_mib=memory)
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                sample["observation_error"] = type(error).__name__
            self.samples.append(sample)
            self.stop.wait(2)

    def __enter__(self):
        self.thread = threading.Thread(target=self._sample, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join(timeout=15)
        if self.thread.is_alive():
            raise RuntimeError("GPU observation did not stop")


def run_trial(cache, folder, *, source_commit, batch_size, steps, max_seconds):
    if sys.platform != "linux":
        raise ValueError("CUDA learning trial requires external Linux")
    if (
        type(steps) is not int
        or steps < 2
        or steps % 2
        or not math.isfinite(max_seconds)
        or max_seconds < 1
    ):
        raise ValueError("trial requires even steps >=2 and a finite time limit")
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    import torch

    from export.model import make_model

    config = RunConfig(batch_size=batch_size, threads=3, save_every=steps)
    count = cache.manifest["audit"]["counts"]["teacher_splits"]["train"]
    if (count + batch_size - 1) // batch_size <= steps:
        raise ValueError(
            "trial must remain within train; no epoch selection during timing"
        )
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    deadline = started + max_seconds
    preflight = {
        "environment": validate_environment_files(ROOT),
        "facts": collect_facts(),
        "kernel": kernel_probe("cuda"),
    }
    atomic_json(folder / "preflight.json", preflight)
    torch.cuda.reset_peak_memory_stats()

    def objects():
        seed_all(config.seed)
        torch.set_num_threads(config.threads)
        model = make_model(config.seed).to("cuda")
        optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=config.learning_rate,
            weight_decay=config.weight_decay,
            betas=(0.9, 0.999),
            eps=1e-8,
            foreach=False,
            fused=False,
        )
        return model, optimizer

    def train(path, model, optimizer, new_steps, *, resume=False):
        report = fit(
            model,
            optimizer,
            cache,
            path,
            config=config,
            source_commit=source_commit,
            max_new_steps=new_steps,
            resume=resume,
            stop_requested=lambda: time.monotonic() >= deadline,
        )
        if report["reason"] != "max_steps" or report["new_steps"] != new_steps:
            raise ValueError(
                "trial stopped before the planned updates; preserve failure"
            )
        return report

    def payload(path):
        binding = json.loads((path / "run.json").read_text())["binding"]
        state_path, _ = checkpoint_receipt(path / "checkpoints", binding=binding)
        return torch.load(state_path, map_location="cpu", weights_only=True)

    with ResourceSamples() as resources:
        model, optimizer = objects()
        full = train(folder / "full", model, optimizer, steps)
        expected = payload(folder / "full")
        del model, optimizer
        gc.collect()
        torch.cuda.empty_cache()
        model, optimizer = objects()
        partial = train(folder / "resumed", model, optimizer, steps // 2)
        del model, optimizer
        gc.collect()
        torch.cuda.empty_cache()
        model, optimizer = objects()
        resumed = train(folder / "resumed", model, optimizer, steps // 2, resume=True)
        actual = payload(folder / "resumed")
        if (
            expected["progress"] != actual["progress"]
            or expected["binding"] != actual["binding"]
        ):
            raise ValueError("trial step/input/config metadata differs")
        comparisons = {
            key: compare_trees(expected[key], actual[key])
            for key in ("model", "optimizer")
        }
        comparisons["rng"] = compare_trees(
            expected["rng"], actual["rng"], atol=0, rtol=0
        )
        probe = next(cache.batches("val", batch_size=1, seed=config.seed)).to("cuda")
        model.eval()
        with torch.inference_mode():
            resumed_output = tuple(item.cpu() for item in model(probe.features))
            model.load_state_dict(expected["model"], strict=True)
            full_output = tuple(item.cpu() for item in model(probe.features))
        comparisons["output"] = compare_trees(full_output, resumed_output)
        ids = {}
        for name in ("full", "resumed"):
            events = [
                json.loads(line)
                for line in (folder / name / "events.jsonl").read_text().splitlines()
            ]
            ids[name] = [
                identity
                for event in events
                if event["event"] == "train"
                for identity in event["ids"]
            ]
        if ids["full"] != ids["resumed"] or len(ids["full"]) != steps * batch_size:
            raise ValueError("trial training example order/count differs")
        torch.cuda.synchronize()
        allocated, reserved = (
            torch.cuda.max_memory_allocated(),
            torch.cuda.max_memory_reserved(),
        )
    if not any("utilization_percent" in sample for sample in resources.samples):
        raise ValueError("GPU utilization observation unavailable")
    report = {
        "schema": "voxelshogi-cuda-trial-v1",
        "source_commit": source_commit,
        "cache_sha256": cache.sha256,
        "config": config.value(),
        "steps": steps,
        "verified": True,
        "atol": ATOL,
        "rtol": RTOL,
        "comparisons": comparisons,
        "same_example_order": True,
        "full": full,
        "partial": partial,
        "resumed": resumed,
        "full_steps_per_second_including_logging_save": steps / full["elapsed_seconds"],
        "full_examples_per_second_including_logging_save": steps
        * batch_size
        / full["elapsed_seconds"],
        "peak_allocated_bytes": allocated,
        "peak_reserved_bytes": reserved,
        "resource_samples": resources.samples,
        "elapsed_seconds": time.monotonic() - started,
        "test_used": False,
        "completed_training": False,
    }
    atomic_json(folder / "trial.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cache", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--batch-size", type=int, required=True)
    parser.add_argument("--steps", type=int, default=64)
    parser.add_argument("--max-seconds", type=float, required=True)
    args = parser.parse_args()
    if sys.platform != "linux" or not args.output.resolve().is_relative_to(
        ROOT / "runs"
    ):
        parser.error("run on external Linux with private output under runs/")
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if status:
        parser.error("CUDA trial requires clean, committed source")
    source = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    report = run_trial(
        FeatureCache(args.cache),
        args.output,
        source_commit=source,
        batch_size=args.batch_size,
        steps=args.steps,
        max_seconds=args.max_seconds,
    )
    print(
        json.dumps(
            {key: value for key, value in report.items() if key != "resource_samples"},
            sort_keys=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
