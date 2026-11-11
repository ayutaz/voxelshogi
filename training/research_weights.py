"""Hash-bound FP32 M weights and evaluation players; no Mac model execution.

Research metadata is inside the safetensors file, so the existing protocol's
artifact SHA binds architecture, training source, selection and actual weights.
Legacy S artifacts retain their existing loader when no research tag exists.
"""

import json
import os
import re
import struct
import sys
from dataclasses import asdict
from pathlib import Path

from export.research_contract import (
    ResearchConfig,
    architecture_config,
    parameter_count,
)
from training.evaluation_v2 import fingerprint
from training.feature_cache import file_hash

SCHEMA = "voxelshogi-research-weights-v1"
TAG = "voxelshogi.research"


def require_linux():
    if sys.platform != "linux":
        raise ValueError("research model execution requires external Linux")


def _sha(value, length):
    return (
        isinstance(value, str)
        and re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is not None
    )


def validate_metadata(value):
    try:
        if (
            type(value) is not dict
            or set(value)
            != {
                "schema",
                "architecture",
                "seed",
                "source_commit",
                "training_binding_sha256",
                "checkpoint_role",
                "step",
            }
            or value["schema"] != SCHEMA
            or type(value["architecture"]) is not dict
        ):
            raise ValueError("research weight metadata schema differs")
        config = ResearchConfig(**value["architecture"])
        if config != architecture_config(config.architecture):
            raise ValueError("research weights require a fixed M profile")
        if (
            type(value["seed"]) is not int
            or not 0 <= value["seed"] < 2**63
            or not _sha(value["source_commit"], 40)
            or not _sha(value["training_binding_sha256"], 64)
            or value["checkpoint_role"] not in ("latest", "best")
            or type(value["step"]) is not int
            or not 1 <= value["step"] <= 1_000_000
        ):
            raise ValueError("research weights require bound source/selection/cursor")
        return {**value, "architecture": asdict(config)}
    except (KeyError, TypeError) as error:
        raise ValueError("research weight metadata differs") from error


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("repeated metadata key")
        result[key] = value
    return result


def research_metadata(path):
    """Read only a bounded header; no Torch import or tensor materialization.

    An absent research tag delegates to the unchanged legacy loader. That
    loader remains responsible for validating legacy safetensors bytes.
    An explicit invalid research tag is rejected instead of delegated.
    """
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("research artifact must be a regular file")
    with path.open("rb") as stream:
        prefix = stream.read(8)
        if len(prefix) != 8:
            return None
        length = struct.unpack("<Q", prefix)[0]
        if not 2 <= length <= min(1024**2, path.stat().st_size - 8):
            return None
        try:
            header = json.loads(stream.read(length), object_pairs_hook=_unique_object)
        except UnicodeDecodeError, json.JSONDecodeError:
            return None
    if not isinstance(header, dict) or "__metadata__" not in header:
        return None
    metadata = header["__metadata__"]
    if type(metadata) is not dict:
        raise ValueError("invalid safetensors metadata object")
    if TAG not in metadata:
        return None
    try:
        value = json.loads(metadata[TAG], object_pairs_hook=_unique_object)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("invalid research metadata JSON") from error
    return validate_metadata(value)


def write_research_weights(state, path, *, metadata):
    require_linux()
    metadata = validate_metadata(metadata)
    import torch
    from safetensors.torch import save_file

    path = Path(path)
    if path.exists() or path.is_symlink() or path.suffix != ".safetensors":
        raise ValueError("research weights need a fresh safetensors path")
    if (
        not isinstance(state, dict)
        or not state
        or any(
            not isinstance(k, str)
            or type(v) is not torch.Tensor
            or v.dtype != torch.float32
            or not torch.isfinite(v).all()
            for k, v in state.items()
        )
    ):
        raise ValueError("research weights must contain finite FP32 tensors")
    config = ResearchConfig(**metadata["architecture"])
    if sum(t.numel() for t in state.values()) != parameter_count(config):
        raise ValueError("research weight parameter count differs")
    path.parent.mkdir(parents=True, exist_ok=True)
    save_file(
        {k: v.detach().cpu().contiguous() for k, v in state.items()},
        str(path),
        metadata={TAG: json.dumps(metadata, sort_keys=True, separators=(",", ":"))},
    )
    if research_metadata(path) != metadata:
        raise ValueError("research metadata changed during weight writing")
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": file_hash(path),
        "metadata": metadata,
    }


def load_research_network(path, *, expected_sha256, device):
    """The same checked fixed-M model for val diagnostics and move adapters."""
    require_linux()
    path = Path(path)
    if (
        not _sha(expected_sha256, 64)
        or path.is_symlink()
        or not path.is_file()
        or path.suffix != ".safetensors"
        or not 0 < path.stat().st_size <= 512 * 1024**2
        or file_hash(path) != expected_sha256
    ):
        raise ValueError("research model artifact hash/format differs")
    if device not in ("cpu", "cuda"):
        raise ValueError("unsupported research backend")
    if device == "cuda" and os.environ.get("CUBLAS_WORKSPACE_CONFIG") != ":4096:8":
        raise ValueError("CUDA deterministic workspace must be set before loading")
    metadata = research_metadata(path)
    if metadata is None:
        raise ValueError("explicit research architecture metadata required")
    import torch
    from safetensors.torch import load_file

    from export.research_model import make_research_model
    from training.checkpoint import seed_all

    if device == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA unavailable; no hidden CPU fallback")
    torch.set_num_threads(1)
    seed_all(metadata["seed"])
    state = load_file(path, device="cpu")
    if not state or any(
        t.dtype != torch.float32 or not torch.isfinite(t).all() for t in state.values()
    ):
        raise ValueError("research inference weights must be finite FP32")
    config = ResearchConfig(**metadata["architecture"])
    model = make_research_model(config, seed=metadata["seed"]).float()
    try:
        model.load_state_dict(state, strict=True)
    except RuntimeError as error:
        raise ValueError("research architecture and stored weights differ") from error
    if file_hash(path) != expected_sha256 or research_metadata(path) != metadata:
        raise ValueError("research model artifact changed while loading")
    return model.to(device).eval(), metadata


def load_research_player(
    path,
    *,
    expected_sha256,
    device,
    policy,
    stop_requested=lambda: False,
    observe_input=None,
):
    require_linux()
    if policy not in ("legal-argmax-v1", "puct32-v1"):
        raise ValueError("unsupported research policy")
    model, metadata = load_research_network(
        path, expected_sha256=expected_sha256, device=device
    )
    from training.evaluation_puct import PuctPlayer
    from training.policy_value import TorchPolicyValue
    from training.students import TorchStudent

    if policy == "puct32-v1":
        evaluate = TorchPolicyValue(model, device=device)
        evaluate._binding = {
            "artifact_sha256": expected_sha256,
            "architecture": metadata["architecture"],
            "backend": "torch-" + device,
            "compute_dtype": "float32",
            "research_metadata_sha256": fingerprint(metadata),
        }
        return PuctPlayer(
            evaluate, stop_requested=stop_requested, observe_input=observe_input
        )
    player = TorchStudent(model, device=device)

    def choose(game):
        if stop_requested():
            raise InterruptedError("research evaluation interrupted")
        if observe_input is not None:
            observe_input(game)
        return player(game)

    return choose
