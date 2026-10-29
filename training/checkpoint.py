"""Private, atomic training checkpoints with input/config binding and RNG state."""

import json
import math
import os
import random
import re
import sys
import uuid
from pathlib import Path

from training.feature_cache import canonical, file_hash

SCHEMA = "voxelshogi-checkpoint-v1"


def _linux():
    if sys.platform != "linux":
        raise ValueError("checkpoint/training execution requires external Linux")


def seed_all(seed):
    _linux()
    import numpy as np
    import torch

    random.seed(seed)
    np.random.seed(seed % 2**32)
    torch.manual_seed(seed)
    deterministic_runtime()


def deterministic_runtime():
    _linux()
    import torch

    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.set_float32_matmul_precision("highest")


def _rng_state():
    import numpy as np
    import torch

    numpy_state = np.random.get_state()
    return {
        "python": random.getstate(),
        "numpy": [numpy_state[0], numpy_state[1].tolist(), *numpy_state[2:]],
        "torch": torch.get_rng_state(),
        "cuda": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else [],
    }


def _restore_rng(state):
    import numpy as np
    import torch

    random.setstate(state["python"])
    name, keys, position, has_gauss, cached_gauss = state["numpy"]
    np.random.set_state(
        (name, np.asarray(keys, dtype=np.uint32), position, has_gauss, cached_gauss)
    )
    torch.set_rng_state(state["torch"].cpu())
    if state["cuda"]:
        if (
            not torch.cuda.is_available()
            or len(state["cuda"]) != torch.cuda.device_count()
        ):
            raise ValueError("checkpoint CUDA RNG device count differs")
        torch.cuda.set_rng_state_all([item.cpu() for item in state["cuda"]])


def _progress(progress):
    if (
        set(progress) != {"epoch", "next_batch", "step", "examples", "best_val_loss"}
        or any(
            type(progress[key]) is not int or progress[key] < 0
            for key in ("epoch", "next_batch", "step", "examples")
        )
        or (
            progress["best_val_loss"] is not None
            and (
                type(progress["best_val_loss"]) not in (int, float)
                or not math.isfinite(progress["best_val_loss"])
                or progress["best_val_loss"] < 0
            )
        )
    ):
        raise ValueError("invalid training progress")


def _sync_directory(folder):
    handle = os.open(folder, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(handle)
    finally:
        os.close(handle)


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("x") as stream:
        stream.write(canonical(value) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    _sync_directory(path.parent)


def save_checkpoint(folder, model, optimizer, *, progress, binding, best=False):
    _linux()
    payload = {
        "model": model.state_dict(),
        "optimizer": optimizer.state_dict(),
        "rng": _rng_state(),
        "progress": progress,
        "binding": binding,
    }
    return _save_payload(folder, payload, best=best)


def _save_payload(folder, payload, *, best=False):
    """Internal writer shared by normal saves and decoded safe archives."""
    _linux()
    if set(payload) != {"model", "optimizer", "rng", "progress", "binding"}:
        raise ValueError("checkpoint payload fields differ")
    progress, binding = payload["progress"], payload["binding"]
    _progress(progress)
    if best and progress["best_val_loss"] is None:
        raise ValueError("best checkpoint requires validation selection")
    canonical(binding)  # Reject non-JSON/nonfinite metadata before writing.
    import torch

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    directory = folder / f"step-{progress['step']:08d}-{uuid.uuid4().hex}"
    directory.mkdir()
    state_path = directory / "state.pt"
    with state_path.open("xb") as stream:
        torch.save(payload, stream)
        stream.flush()
        os.fsync(stream.fileno())
    receipt = {
        "schema": SCHEMA,
        "verified": True,
        "step": progress["step"],
        "binding": binding,
        "progress": progress,
        "bytes": state_path.stat().st_size,
        "sha256": file_hash(state_path),
    }
    atomic_json(directory / "receipt.json", receipt)
    pointer = {
        "directory": directory.name,
        "receipt_sha256": file_hash(directory / "receipt.json"),
    }
    previous = folder / "latest.json"
    selected = (
        dict(pointer)
        if best
        else (
            json.loads(previous.read_text()).get("best") if previous.exists() else None
        )
    )
    # latest and best commit together, so interruption cannot mix generations.
    atomic_json(previous, {**pointer, "best": selected})
    prune_checkpoints(folder, binding=binding)
    return receipt


def prune_checkpoints(folder, *, binding):
    """Keep latest/best; only remove complete, hash-verified owned generations."""
    folder = Path(folder)
    index = json.loads((folder / "latest.json").read_text())
    keep = {index["directory"]}
    if index["best"] is not None:
        keep.add(index["best"]["directory"])
    for directory in folder.iterdir():
        if (
            directory.name in keep
            or not re.fullmatch(r"step-[0-9]{8}-[0-9a-f]{32}", directory.name)
            or directory.is_symlink()
            or not directory.is_dir()
        ):
            continue
        if {path.name for path in directory.iterdir()} != {"state.pt", "receipt.json"}:
            continue  # Never delete partial or unrelated files.
        state, receipt_path = directory / "state.pt", directory / "receipt.json"
        if state.is_symlink() or receipt_path.is_symlink():
            continue
        receipt = json.loads(receipt_path.read_text())
        if (
            receipt.get("schema") != SCHEMA
            or receipt.get("verified") is not True
            or receipt.get("binding") != binding
            or state.stat().st_size != receipt["bytes"]
            or file_hash(state) != receipt["sha256"]
        ):
            raise ValueError("refuse to prune unverified checkpoint")
        state.unlink()
        receipt_path.unlink()
        directory.rmdir()


def checkpoint_receipt(folder, *, binding, which="latest"):
    _linux()
    if which not in ("latest", "best"):
        raise ValueError("unknown checkpoint selector")
    folder = Path(folder)
    try:
        pointer_path = folder / "latest.json"
        if pointer_path.is_symlink():
            raise ValueError("checkpoint pointer must be a regular file")
        pointer = json.loads(pointer_path.read_text())
        if which == "best":
            pointer = pointer.get("best")
            if pointer is None:
                raise ValueError("incomplete checkpoint: no validation-selected model")
        if not re.fullmatch(r"step-[0-9]{8}-[0-9a-f]{32}", pointer["directory"]):
            raise ValueError("invalid checkpoint directory")
        directory = folder / pointer["directory"]
        receipt_path, state_path = directory / "receipt.json", directory / "state.pt"
        if (
            directory.is_symlink()
            or receipt_path.is_symlink()
            or state_path.is_symlink()
        ):
            raise ValueError("checkpoint must contain regular files")
        if file_hash(receipt_path) != pointer["receipt_sha256"]:
            raise ValueError("checkpoint receipt hash differs")
        receipt = json.loads(receipt_path.read_text())
        if receipt["schema"] != SCHEMA or receipt["verified"] is not True:
            raise ValueError("incomplete checkpoint receipt")
        if receipt["binding"] != binding:
            raise ValueError(
                "checkpoint binding differs: source/input/config/environment"
            )
        _progress(receipt["progress"])
        if (
            state_path.stat().st_size != receipt["bytes"]
            or file_hash(state_path) != receipt["sha256"]
        ):
            raise ValueError("checkpoint state size/hash differs")
        return state_path, receipt
    except (OSError, KeyError, json.JSONDecodeError) as error:
        raise ValueError("incomplete checkpoint") from error


def load_checkpoint(folder, model, optimizer, *, binding, which="latest"):
    _linux()
    import torch

    path, receipt = checkpoint_receipt(folder, binding=binding, which=which)
    # Owned files only; never widen the unpickler or load arbitrary Python classes.
    state = torch.load(path, map_location="cpu", weights_only=True)
    if state["binding"] != binding or state["progress"] != receipt["progress"]:
        raise ValueError("checkpoint payload binding/progress differs")
    model.load_state_dict(state["model"], strict=True)
    optimizer.load_state_dict(state["optimizer"])
    _restore_rng(state["rng"])
    return state["progress"]
