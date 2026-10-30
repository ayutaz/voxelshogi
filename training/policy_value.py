"""Checked legal-policy/value inference and immutable FP32 S-weight loading."""

import os
import re
import sys
from pathlib import Path

from training.checkpoint import deterministic_runtime
from training.feature_cache import file_hash
from training.students import TorchStudent


class TorchPolicyValue(TorchStudent):
    def __init__(self, model, *, device):
        if sys.platform != "linux" or device not in ("cpu", "cuda"):
            raise ValueError("policy/value inference requires external Linux CPU/CUDA")
        import torch

        if device == "cuda" and not torch.cuda.is_available():
            raise ValueError("CUDA requested but unavailable; no CPU fallback")
        if device == "cuda" and os.environ.get("CUBLAS_WORKSPACE_CONFIG") != ":4096:8":
            raise ValueError(
                "CUDA deterministic workspace must be :4096:8 before initialization"
            )
        deterministic_runtime()
        super().__init__(model, device=device)
        self.model.requires_grad_(False)
        self._binding = None
        self.calls = 0

    @property
    def binding(self):
        return dict(self._binding) if self._binding is not None else None

    @property
    def model_sha256(self):
        return self._binding["artifact_sha256"] if self._binding is not None else None

    def __call__(self, game):
        import torch

        deterministic_runtime()
        legal, logits, value = self._outputs(game)
        estimate = value.item()
        if not -1 <= estimate <= 1:
            raise ValueError("policy/value output is outside [-1,1]")
        with torch.inference_mode():
            probabilities = logits[0, legal].softmax(dim=0).cpu().tolist()
        self.calls += 1
        return dict(zip(legal, probabilities, strict=True)), estimate


def load_policy_value(path, *, expected_sha256, device):
    """Build an independent inference model; never unpickle public weights."""
    if sys.platform != "linux":
        raise ValueError("model loading requires external Linux")
    path = Path(path)
    if (
        not isinstance(expected_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
        or path.is_symlink()
        or not path.is_file()
        or path.suffix != ".safetensors"
        or not 0 < path.stat().st_size <= 512 * 1024**2
        or file_hash(path) != expected_sha256
    ):
        raise ValueError("model file, size, format, or artifact hash differs")
    import torch
    from safetensors.torch import load_file

    from export.model import make_model

    if device not in ("cpu", "cuda") or (
        device == "cuda" and not torch.cuda.is_available()
    ):
        raise ValueError("requested CPU/CUDA backend is unavailable")
    state = load_file(path, device="cpu")
    if not state or any(
        t.dtype != torch.float32 or not torch.isfinite(t).all() for t in state.values()
    ):
        raise ValueError("training actor weights must be finite FP32 tensors")
    model = make_model(314159).float()
    try:
        model.load_state_dict(state, strict=True)
    except RuntimeError as error:
        raise ValueError("model architecture and stored weights differ") from error
    if file_hash(path) != expected_sha256:
        raise ValueError("model file changed while loading")
    evaluator = TorchPolicyValue(model, device=device)
    evaluator._binding = {
        "artifact_sha256": expected_sha256,
        "architecture": "transformer-s-full-v1",
        "backend": "torch-" + device,
        "compute_dtype": "float32",
    }
    return evaluator
