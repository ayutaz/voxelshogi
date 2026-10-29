"""Sparse legal-policy supervision. Tensor execution belongs on external Linux.

Importing this module does not initialize Torch, CUDA, the engine, or a dataset.
"""

import hashlib
import random
from dataclasses import dataclass
from typing import Any


def epoch_batches(size, batch_size, *, seed, epoch, start_batch=0):
    """An epoch permutation independent of ambient RNG; cursor counts batches."""
    if (
        any(type(x) is not int for x in (size, batch_size, seed, epoch, start_batch))
        or size < 1
        or batch_size < 1
        or seed < 0
        or epoch < 0
        or not 0 <= start_batch <= (size + batch_size - 1) // batch_size
    ):
        raise ValueError("invalid sampler dimensions or cursor")
    indices = list(range(size))
    mixed_seed = int.from_bytes(
        hashlib.sha256(f"m6:{seed}:{epoch}".encode()).digest(), "big"
    )
    random.Random(mixed_seed).shuffle(indices)
    for offset in range(start_batch * batch_size, size, batch_size):
        yield indices[offset : offset + batch_size]


@dataclass(frozen=True)
class Batch:
    features: Any
    actions: Any
    values: Any
    legal_actions: list[list[int]]
    ids: tuple[str, ...]
    split: str

    def to(self, device):
        return Batch(
            self.features.to(device),
            self.actions.to(device),
            self.values.to(device),
            self.legal_actions,
            self.ids,
            self.split,
        )


def _validate_batch(batch, split):
    if (
        batch.split != split
        or not batch.ids
        or len(batch.ids) != len(batch.features)
        or len(set(batch.ids)) != len(batch.ids)
        or any(not isinstance(item, str) or not item for item in batch.ids)
    ):
        raise ValueError("empty, repeated, or wrong-split batch")


def _legal_indices(logits, actions, legal_actions):
    import torch

    if len(legal_actions) != len(logits):
        raise ValueError("legal set batch shape differs")
    indices = []
    for action, legal in zip(actions.tolist(), legal_actions, strict=True):
        if (
            not legal
            or any(
                type(item) is not int or not 0 <= item < logits.shape[1]
                for item in legal
            )
            or len(set(legal)) != len(legal)
            or action not in legal
        ):
            raise ValueError("invalid legal set or illegal target")
        indices.append(
            torch.tensor(sorted(legal), device=logits.device, dtype=torch.long)
        )
    return indices


def loss_terms(logits, values, actions, target_values, legal_actions):
    import torch
    from torch.nn import functional as F

    if (
        logits.ndim != 2
        or not len(logits)
        or not logits.shape[1]
        or values.shape != (len(logits), 1)
        or actions.shape != (len(logits),)
        or target_values.shape != (len(logits),)
        or actions.dtype != torch.long
        or any(not torch.is_floating_point(x) for x in (logits, values, target_values))
        or any(
            not torch.isfinite(x).all().item() for x in (logits, values, target_values)
        )
        or (target_values.abs() > 1).any().item()
        or any(x.device != logits.device for x in (values, actions, target_values))
    ):
        raise ValueError("empty, nonfinite, or invalid loss tensors")
    indices = _legal_indices(logits, actions, legal_actions)
    # Gather the sparse legal choices before softmax. Illegal logits receive no
    # gradient; a very large illegal logit cannot destabilize the distribution.
    policy = torch.stack(
        [
            F.cross_entropy(
                logits[i, legal].unsqueeze(0),
                (legal == actions[i]).long().argmax().reshape(1),
            )
            for i, legal in enumerate(indices)
        ]
    ).mean()
    value = F.mse_loss(values[:, 0], target_values, reduction="mean")
    return {"policy": policy, "value": value, "total": policy + value}


def _scalars(terms, count):
    return {
        "examples": count,
        "policy_loss": terms["policy"].item(),
        "value_mse": terms["value"].item(),
        "loss": terms["total"].item(),
    }


def train_step(model, optimizer, batch):
    import torch

    _validate_batch(batch, "train")
    model.train()
    optimizer.zero_grad(set_to_none=True)
    logits, values = model(batch.features)
    terms = loss_terms(logits, values, batch.actions, batch.values, batch.legal_actions)
    terms["total"].backward()
    parameters = [
        parameter for parameter in model.parameters() if parameter.grad is not None
    ]
    if not parameters or any(
        not torch.isfinite(p.grad).all().item() for p in parameters
    ):
        raise ValueError("nonfinite or missing gradient; optimizer not stepped")
    try:
        norm = torch.nn.utils.clip_grad_norm_(
            parameters, max_norm=1.0, error_if_nonfinite=True
        )
    except RuntimeError as error:
        raise ValueError("nonfinite gradient norm; optimizer not stepped") from error
    optimizer.step()
    return {**_scalars(terms, len(batch.ids)), "gradient_norm": norm.item()}


def evaluate_model(model, batches, *, split="val"):
    import torch

    if split not in ("val", "test"):
        raise ValueError("evaluation requires val or explicitly requested test")
    sums = dict.fromkeys(
        (
            "policy_loss",
            "value_mse",
            "loss",
            "value_mae",
            "policy_top1",
            "policy_top5",
            "raw_legal_rate",
        ),
        0.0,
    )
    seen = set()
    was_training = model.training
    model.eval()
    try:
        with torch.inference_mode():
            for batch in batches:
                _validate_batch(batch, split)
                if seen.intersection(batch.ids):
                    raise ValueError("repeated evaluation example")
                seen.update(batch.ids)
                logits, values = model(batch.features)
                terms = loss_terms(
                    logits, values, batch.actions, batch.values, batch.legal_actions
                )
                count = len(batch.ids)
                for key, value in _scalars(terms, count).items():
                    if key != "examples":
                        sums[key] += value * count
                sums["value_mae"] += (values[:, 0] - batch.values).abs().sum().item()
                for i, legal in enumerate(
                    _legal_indices(logits, batch.actions, batch.legal_actions)
                ):
                    # legal is sorted, stable ordering resolves ties by smallest ID.
                    ranked = legal[
                        torch.argsort(logits[i, legal], descending=True, stable=True)
                    ]
                    sums["policy_top1"] += (ranked[0] == batch.actions[i]).item()
                    sums["policy_top5"] += (ranked[:5] == batch.actions[i]).any().item()
                    sums["raw_legal_rate"] += (logits[i].argmax() == legal).any().item()
    finally:
        model.train(was_training)
    if not seen:
        raise ValueError("empty evaluation")
    return {
        "examples": len(seen),
        **{k: v / len(seen) for k, v in sums.items()},
        "masked_legal_rate": 1.0,
    }
