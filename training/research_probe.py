"""P6 real-shape operator feasibility; metadata/fake clocks are safe on Mac.

Real model execution requires external Linux CUDA. Synthetic optimizer loads
are discarded and are never presented as training, strength, or total FLOPs.
"""

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

from export.research_contract import (
    ARCHITECTURES,
    architecture_config,
    forward_matmul_flops,
    parameter_count,
)
from training.evaluation_v2 import fingerprint

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "export/fixtures/positions.json"


def _linux():
    if sys.platform != "linux":
        raise ValueError("real operator probe requires external Linux CUDA")


def probe_protocol(source_commit):
    if (
        not isinstance(source_commit, str)
        or re.fullmatch(r"[0-9a-f]{40}", source_commit) is None
    ):
        raise ValueError("immutable research probe source required")
    return {
        "schema": "voxelshogi-research-operator-probe-v1",
        "source_commit": source_commit,
        "architectures": {
            name: asdict(architecture_config(name)) for name in ARCHITECTURES
        },
        "model_seed": 66001,
        "batch_sizes": [1, 4, 8, 16],
        "warmup_steps": 8,
        "measured_steps": 32,
        "precision": "float32",
        "tf32": False,
        "fixture_indices": [0, 3],
        "fixtures_sha256": hashlib.sha256(FIXTURES.read_bytes()).hexdigest(),
        "numeric": {
            "policy_atol": 1e-4,
            "policy_rtol": 1e-4,
            "value_atol": 1e-5,
            "value_rtol": 1e-5,
        },
        "maximum_seconds": 1800,
        "measurement_scope": "synthetic operator load: first legal action dense cross-entropy plus zero-value MSE and AdamW; discarded optimizer copies; not teacher training throughput, strength or total training FLOPs",
    }


def validate_probe(protocol):
    if type(protocol) is not dict or fingerprint(protocol) != fingerprint(
        probe_protocol(protocol.get("source_commit"))
    ):
        raise ValueError("research probe differs from fixed conditions")
    return protocol


def measure_steps(
    step,
    synchronize,
    *,
    batch_size,
    warmup_steps,
    measured_steps,
    clock=time.monotonic,
    stop_requested=lambda: False,
):
    if (
        type(batch_size) is not int
        or not 1 <= batch_size <= 256
        or type(warmup_steps) is not int
        or not 0 <= warmup_steps <= 10000
        or type(measured_steps) is not int
        or not 1 <= measured_steps <= 10000
    ):
        raise ValueError("invalid operator measurement counts")
    for _ in range(warmup_steps):
        if stop_requested():
            raise InterruptedError("operator warmup interrupted")
        step()
    synchronize()
    started = clock()
    for _ in range(measured_steps):
        if stop_requested():
            raise InterruptedError("operator measurement interrupted")
        step()
    synchronize()
    elapsed = clock() - started
    if stop_requested():
        raise InterruptedError("operator measurement interrupted at synchronization")
    if not math.isfinite(elapsed) or elapsed <= 0:
        raise ValueError("invalid measured operator elapsed time")
    return {
        "warmup_steps": warmup_steps,
        "measured_steps": measured_steps,
        "batch_size": batch_size,
        "measured_examples": measured_steps * batch_size,
        "elapsed_seconds": elapsed,
        "examples_per_second": measured_steps * batch_size / elapsed,
    }


def _descriptor(folder, path):
    from training.feature_cache import file_hash

    return {
        "path": str(path.relative_to(folder)),
        "bytes": path.stat().st_size,
        "sha256": file_hash(path),
    }


def _inputs(protocol):
    _linux()
    from voxelshogi import Game

    from export.contract import encode_position

    fixtures = json.loads(FIXTURES.read_text())
    result = []
    for index in protocol["fixture_indices"]:
        record = fixtures[index]["record"]
        game = Game.from_record(record)
        if game.record() != record or game.snapshot()["finished"]:
            raise ValueError("operator fixture must be Rust canonical and unfinished")
        snapshot = game.snapshot()
        features = encode_position(
            snapshot["board"], snapshot["hands"], side=snapshot["side"]
        )
        result.append((index, features[0], sorted(game.legal_actions())))
    return result


def _export_and_check(config, protocol, inputs, folder, *, device="cuda"):
    _linux()
    import numpy as np
    import onnx
    import onnxruntime as ort
    import torch
    from safetensors.torch import save_file

    from export.research_model import make_research_model

    network = make_research_model(config, seed=protocol["model_seed"])
    assert sum(p.numel() for p in network.parameters()) == parameter_count(config)
    weights = folder / "model.safetensors"
    save_file(network.state_dict(), weights)
    references, tensors = {}, {}
    if device not in ("cpu", "cuda"):
        raise ValueError("unknown operator reference device")
    network.to(device)
    with torch.inference_mode():
        for index, array, _ in inputs:
            features = torch.from_numpy(array[None]).to(device)
            outputs = network(features)
            references[index] = [value.cpu().numpy().copy() for value in outputs]
            tensors[f"fixture{index}.features"] = features.cpu().contiguous()
            for name, value in zip(("policy", "value"), outputs, strict=True):
                tensors[f"fixture{index}.{name}"] = value.cpu().contiguous()
    network.cpu()
    if device == "cuda":
        torch.cuda.empty_cache()
    path = folder / "fp32.onnx"
    features = torch.from_numpy(inputs[0][1][None])
    torch.onnx.export(
        network,
        (features,),
        path,
        input_names=["features"],
        output_names=["policy", "value"],
        dynamo=True,
        opset_version=18,
        external_data=False,
    )
    onnx.checker.check_model(onnx.load(path), full_check=True)
    options = ort.SessionOptions()
    options.intra_op_num_threads = options.inter_op_num_threads = 1
    session = ort.InferenceSession(path, options, providers=["CPUExecutionProvider"])
    numeric = []
    with torch.inference_mode():
        for index, array, legal in inputs:
            cpu = [value.numpy() for value in network(torch.from_numpy(array[None]))]
            actual = session.run(None, {"features": array[None]})
            for backend, outputs in (("torch-cpu", cpu), ("ort-cpu", actual)):
                for name, expected, observed in zip(
                    ("policy", "value"), references[index], outputs, strict=True
                ):
                    if (
                        expected.shape != observed.shape
                        or not np.isfinite(observed).all()
                    ):
                        raise ValueError("invalid real-shape operator output")
                    np.testing.assert_allclose(
                        observed,
                        expected,
                        atol=protocol["numeric"][name + "_atol"],
                        rtol=protocol["numeric"][name + "_rtol"],
                    )
                    numeric.append(
                        {
                            "fixture": index,
                            "backend": backend,
                            "output": name,
                            "elements": observed.size,
                            "max_abs": float(np.max(np.abs(observed - expected))),
                        }
                    )
                if int(outputs[0][0, legal].argmax()) != int(
                    references[index][0][0, legal].argmax()
                ):
                    raise ValueError("ONNX legal argmax differs from CUDA")
    reference_path = folder / "references.safetensors"
    save_file(tensors, reference_path)
    return {
        "passed": True,
        "reference_backend": "torch-" + device,
        "parameter_count": parameter_count(config),
        "forward_dense_matmul_flops_per_example": forward_matmul_flops(config),
        "numeric": numeric,
        "files": [
            _descriptor(folder, file) for file in (weights, path, reference_path)
        ],
        "weight_scope": "untrained seed66001 weights; synthetic benchmark updates occur only in separate discarded models",
    }


def _measure_model(config, protocol, sample, *, batch_size, stopping):
    _linux()
    import torch
    from torch import nn

    from export.research_model import make_research_model

    network = make_research_model(config, seed=protocol["model_seed"]).cuda().train()
    features = torch.from_numpy(sample[1][None]).cuda().repeat(batch_size, 1, 1)
    target = torch.full((batch_size,), sample[2][0], dtype=torch.long, device="cuda")
    optimizer = torch.optim.AdamW(network.parameters(), lr=1e-4)
    torch.cuda.reset_peak_memory_stats()

    def step():
        optimizer.zero_grad(set_to_none=True)
        policy, value = network(features)
        loss = nn.functional.cross_entropy(policy, target) + value.square().mean()
        if not torch.isfinite(loss):
            raise ValueError("nonfinite synthetic operator loss")
        loss.backward()
        optimizer.step()

    result = measure_steps(
        step,
        torch.cuda.synchronize,
        batch_size=batch_size,
        warmup_steps=protocol["warmup_steps"],
        measured_steps=protocol["measured_steps"],
        stop_requested=stopping,
    )
    result.update(
        status="success",
        peak_allocated_bytes=torch.cuda.max_memory_allocated(),
        peak_reserved_bytes=torch.cuda.max_memory_reserved(),
    )
    return result


def run_probe(protocol, folder, *, stop_requested=lambda: False):
    _linux()
    validate_probe(protocol)
    started = time.monotonic()
    import platform

    import torch

    from training.checkpoint import atomic_json, deterministic_runtime

    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise ValueError("operator probe requires exactly one real CUDA GPU")
    if subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip() != protocol["source_commit"] or subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True
    ):
        raise ValueError("operator source must be its admitted clean commit")
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(1)
    deterministic_runtime()
    atomic_json(folder / "config.json", protocol)
    inputs = _inputs(protocol)
    results = {}
    report = {
        "schema": "voxelshogi-research-operator-results-v1",
        "protocol_sha256": fingerprint(protocol),
        "complete": False,
        "source_commit": protocol["source_commit"],
        "python": platform.python_version(),
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(0),
        "driver": subprocess.check_output(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            text=True,
        ).strip(),
        "architectures": results,
        "measurement_scope": protocol["measurement_scope"],
    }

    def stopping():
        return (
            stop_requested()
            or time.monotonic() - started >= protocol["maximum_seconds"]
        )

    try:
        for name in ARCHITECTURES:
            if stopping():
                raise InterruptedError("operator probe fixed deadline")
            config = architecture_config(name)
            target = folder / name
            target.mkdir()
            row = {"config": asdict(config), "export": None, "measurements": []}
            results[name] = row
            begin = time.monotonic()
            try:
                row["export"] = _export_and_check(config, protocol, inputs, target)
            except InterruptedError:
                raise
            except Exception as error:
                row["export"] = {
                    "passed": False,
                    "error_type": type(error).__name__,
                    "error_message": str(error)[:1024],
                }
            row["export_check_seconds"] = time.monotonic() - begin
            torch.cuda.empty_cache()
            for batch in protocol["batch_sizes"]:
                if stopping():
                    raise InterruptedError("operator probe fixed deadline")
                begin = time.monotonic()
                try:
                    value = _measure_model(
                        config, protocol, inputs[0], batch_size=batch, stopping=stopping
                    )
                except torch.OutOfMemoryError:
                    value = {"status": "out-of-memory", "batch_size": batch}
                value["preparation_and_measurement_seconds"] = time.monotonic() - begin
                row["measurements"].append(value)
                torch.cuda.empty_cache()
                report["elapsed_seconds"] = time.monotonic() - started
                atomic_json(folder / "manifest.json", report)
        report["complete"] = (
            all(
                row["export"]["passed"]
                and any(m["status"] == "success" for m in row["measurements"])
                for row in results.values()
            )
            and len(results) == 4
        )
        report["all_batches_fit"] = all(
            m["status"] == "success"
            for row in results.values()
            for m in row["measurements"]
        )
        return report
    finally:
        report["elapsed_seconds"] = time.monotonic() - started
        atomic_json(folder / "manifest.json", report)


def main():
    import signal
    import threading

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    report = run_probe(
        json.loads(args.protocol.read_text()), args.output, stop_requested=stop.is_set
    )
    print(
        json.dumps(
            {
                "complete": report["complete"],
                "elapsed_seconds": report["elapsed_seconds"],
            }
        )
    )
    if not report["complete"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
