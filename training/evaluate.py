"""Final test and fixed paired matches for val-selected weights and ONNX variants."""

import argparse
import json
import math
import os
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import fields
from pathlib import Path

from training.checkpoint import atomic_json, checkpoint_receipt, seed_all
from training.evaluation import evaluate_matches
from training.feature_cache import FeatureCache, canonical, file_hash
from training.fit import RunConfig, _check_cursor, runtime_environment
from training.learning import evaluate_model
from training.students import TorchStudent, make_ort_model
from training.supervision import ROOT, label_contract


def validate_selected(binding, receipt, *, cache_sha256, source_commit, train_count):
    try:
        config = RunConfig(
            **{field.name: binding["config"][field.name] for field in fields(RunConfig)}
        )
        progress = receipt["progress"]
        if (
            receipt["binding"] != binding
            or binding["cache_sha256"] != cache_sha256
            or binding["source_commit"] != source_commit
            or binding["contract"] != label_contract()
            or binding["config"] != config.value()
            or type(train_count) is not int
            or train_count < 1
            or progress["epoch"] < 1
            or progress["next_batch"] != 0
            or type(progress["best_val_loss"]) not in (int, float)
            or not math.isfinite(progress["best_val_loss"])
            or progress["best_val_loss"] < 0
        ):
            raise ValueError(
                "final evaluation requires matching input/source and a val-selected epoch"
            )
        _check_cursor(progress, train_count, config)
        return progress
    except (KeyError, TypeError) as error:
        raise ValueError("invalid selected training metadata") from error


def _write_weights(path, state):
    from safetensors.torch import save_file

    if path.is_symlink():
        raise ValueError("evaluation weights must be a regular file")
    temporary = path.with_name(f"student-{uuid.uuid4().hex}.safetensors")
    save_file(
        {name: value.detach().cpu().contiguous() for name, value in state.items()},
        temporary,
    )
    if path.exists() and (
        path.stat().st_size != temporary.stat().st_size
        or file_hash(path) != file_hash(temporary)
    ):
        temporary.unlink()
        raise ValueError("evaluation weights differ on resume")
    temporary.replace(path)
    return {"path": path.name, "bytes": path.stat().st_size, "sha256": file_hash(path)}


def prepare_torch_student(folder, *, cache, source_commit, device, training_run=None):
    if sys.platform != "linux":
        raise ValueError("model preparation requires external Linux")
    import torch

    from export.model import make_model

    lineage = None
    if training_run is None:
        config = RunConfig(device=device)
        seed_all(config.seed)
        model = make_model(config.seed)
        model_id = f"voxelshogi-transformer-s-m6-initial-{config.seed}-v1"
    else:
        binding = json.loads((Path(training_run) / "run.json").read_text())["binding"]
        state_path, receipt = checkpoint_receipt(
            Path(training_run) / "checkpoints", binding=binding, which="best"
        )
        progress = validate_selected(
            binding,
            receipt,
            cache_sha256=cache.sha256,
            source_commit=source_commit,
            train_count=cache.manifest["audit"]["counts"]["teacher_splits"]["train"],
        )
        config = RunConfig(
            **{field.name: binding["config"][field.name] for field in fields(RunConfig)}
        )
        seed_all(config.seed)
        state = torch.load(state_path, map_location="cpu", weights_only=True)
        if state["binding"] != binding or state["progress"] != progress:
            raise ValueError("selected checkpoint payload differs from receipt")
        model = make_model(config.seed)
        model.load_state_dict(state["model"], strict=True)
        model_id = f"voxelshogi-transformer-s-m6-{config.seed}-v1"
        lineage = {
            "checkpoint_sha256": receipt["sha256"],
            "source_commit": source_commit,
            "cache_sha256": cache.sha256,
            "selection_split": "val",
            "selected_progress": progress,
            "binding": binding,
            "receipt": receipt,
        }
    torch.set_num_threads(config.threads)
    descriptor = _write_weights(
        Path(folder) / "student.safetensors", model.state_dict()
    )
    info = {
        "model_id": model_id,
        "artifact_sha256": descriptor["sha256"],
        "trained": training_run is not None,
        "precision": "fp32",
        "backend": "torch-" + device,
    }
    return (
        TorchStudent(model, device=device),
        info,
        {"weights": descriptor, "lineage": lineage},
        config.batch_size,
    )


def prepare_ort_student(bundle, *, precision, source_commit, cache_sha256, train_count):
    if sys.platform != "linux":
        raise ValueError("ONNX evaluation requires external Linux")
    from export.generate import validate_package

    seed_all(314159)
    bundle = Path(bundle)
    manifest = validate_package(bundle)
    if (
        manifest.get("sourceDirty") is not False
        or manifest.get("sourceCommit") != source_commit
        or type(manifest.get("trained")) is not bool
    ):
        raise ValueError("ONNX source/provenance differs from evaluation source")
    if manifest.get("seed") != 314159 or manifest.get("parameters") != 5021064:
        raise ValueError("ONNX differs from the fixed M6 representative model")
    if manifest["trained"]:
        training = manifest.get("training", {})
        validate_selected(
            training.get("binding", {}),
            training.get("receipt", {}),
            cache_sha256=cache_sha256,
            source_commit=source_commit,
            train_count=train_count,
        )
        if training.get("evaluated_weights_sha256") != manifest["checkpoint"]["sha256"]:
            raise ValueError(
                "ONNX was not exported from the evaluated selected weights"
            )
    variant = next(
        (variant for variant in manifest["variants"] if variant["id"] == precision),
        None,
    )
    if variant is None:
        raise ValueError("requested ONNX variant is absent")
    network = make_ort_model(bundle / variant["model"]["path"], precision=precision)
    info = {
        "model_id": manifest["id"],
        "artifact_sha256": variant["model"]["sha256"],
        "trained": manifest["trained"],
        "precision": precision,
        "backend": "ort-cpu",
    }
    return (
        TorchStudent(network, device="cpu"),
        info,
        {
            "weights": variant["model"],
            "manifest_sha256": file_hash(bundle / "manifest.json"),
        },
        1,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cache", type=Path)
    parser.add_argument("output", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--training-run", type=Path)
    mode.add_argument("--baseline", action="store_true")
    mode.add_argument("--bundle", type=Path)
    parser.add_argument("--precision", choices=("fp32", "fp16", "int8"), default="fp32")
    parser.add_argument("--device", choices=("cpu", "cuda"))
    parser.add_argument("--max-seconds", type=float, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if (
        sys.platform != "linux"
        or not args.output.resolve().is_relative_to(ROOT / "runs")
        or args.output.is_symlink()
    ):
        parser.error("evaluate only on external Linux with private output under runs/")
    if not math.isfinite(args.max_seconds) or args.max_seconds < 1:
        parser.error("evaluation requires a positive finite time limit")
    if not args.bundle and args.precision != "fp32":
        parser.error("FP16/INT8 evaluation requires the actual converted ONNX bundle")
    device = args.device or ("cpu" if args.bundle else "cuda")
    if args.bundle and device != "cpu":
        parser.error("this ONNX reference evaluator explicitly uses ORT CPU")
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if status:
        parser.error("evaluation requires clean, committed source")
    source = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    started = time.monotonic()
    stopping = False

    def request_stop(_signal, _frame):
        nonlocal stopping
        stopping = True

    previous = {
        sig: signal.signal(sig, request_stop) for sig in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        cache = FeatureCache(args.cache)
        args.output.mkdir(parents=True, exist_ok=args.resume)
        if args.bundle:
            student, info, lineage, batch_size = prepare_ort_student(
                args.bundle,
                precision=args.precision,
                source_commit=source,
                cache_sha256=cache.sha256,
                train_count=cache.manifest["audit"]["counts"]["teacher_splits"][
                    "train"
                ],
            )
        else:
            student, info, lineage, batch_size = prepare_torch_student(
                args.output,
                cache=cache,
                source_commit=source,
                device=device,
                training_run=args.training_run,
            )
        binding = {
            "schema": "voxelshogi-final-evaluation-v1",
            "source_commit": source,
            "cache_sha256": cache.sha256,
            "counts": cache.manifest["audit"]["counts"],
            "contract": label_contract(),
            "model": info,
            "lineage": lineage,
            "test_batch_size": batch_size,
            "runtime": runtime_environment(RunConfig(device=device)),
        }
        input_path = args.output / "input.json"
        if args.resume:
            if json.loads(input_path.read_text()) != binding:
                raise ValueError("final evaluation binding differs on resume")
        else:
            atomic_json(input_path, binding)

        def stop_requested():
            return stopping or time.monotonic() - started >= args.max_seconds

        def test_batches():
            for batch in cache.batches("test", batch_size=batch_size, seed=314159):
                if stop_requested():
                    raise InterruptedError(
                        "test interrupted; not a complete test result"
                    )
                yield batch.to(student.device)

        test_path, test_receipt = (
            args.output / "test.json",
            args.output / "test-receipt.json",
        )
        if args.resume and test_path.exists() and test_receipt.exists():
            if json.loads(test_receipt.read_text()) != {"sha256": file_hash(test_path)}:
                raise ValueError("completed test report hash differs")
            test = json.loads(test_path.read_text())
        else:
            try:
                metrics = evaluate_model(student.model, test_batches(), split="test")
            except InterruptedError:
                print(
                    canonical(
                        {"complete": False, "stage": "test", "reason": "interrupted"}
                    ),
                    flush=True,
                )
                return
            if (
                metrics["examples"]
                != cache.manifest["audit"]["counts"]["teacher_splits"]["test"]
            ):
                raise ValueError("final test count differs from audited split")
            test = {
                "input_sha256": file_hash(input_path),
                "split": "test",
                "metrics": metrics,
            }
            atomic_json(test_path, test)
            atomic_json(test_receipt, {"sha256": file_hash(test_path)})
        if test["input_sha256"] != file_hash(input_path):
            raise ValueError("test belongs to another model/input")
        matches = evaluate_matches(
            student,
            args.output / "matches",
            model=info,
            source_commit=source,
            stop_requested=stop_requested,
            resume=args.resume and (args.output / "matches").exists(),
        )
        report = {
            **binding,
            "test": test,
            "matches": matches,
            "complete": matches["complete"],
        }
        atomic_json(args.output / "evaluation.json", report)
        print(
            canonical(
                {
                    "complete": report["complete"],
                    "model": info,
                    "test": test["metrics"],
                    "cohorts": matches.get("cohorts"),
                }
            ),
            flush=True,
        )
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    main()
