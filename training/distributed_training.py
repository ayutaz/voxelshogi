"""FP32 distributed-update conditions; execution stays on external Linux."""

import hashlib
import re
import sys
from dataclasses import asdict, dataclass

from training.fit import RunConfig

REDUCTION = "rank-ordered-float32-v1"


def rank_ordered_mean(buffers):
    """Average in rank order; the FP32 caller supplies clones and pointwise ops."""
    if (
        type(buffers) not in (list, tuple)
        or len(buffers) not in (1, 2, 4)
        or any(
            b.shape != buffers[0].shape or b.dtype != buffers[0].dtype for b in buffers
        )
    ):
        raise ValueError("rank count or gradient bucket layout differs")
    result = buffers[0].clone()
    for value in buffers[1:]:
        result.add_(value)
    return result.div_(len(buffers))


def _rank_ordered_hook(state, bucket):
    import torch

    dist, world_size = state
    buffer = bucket.buffer()
    if buffer.dtype != torch.float32:
        raise ValueError("rank-ordered gradients require float32")
    values = [torch.empty_like(buffer) for _ in range(world_size)]
    # The collective transports bytes; only the explicit rank-order loop sums.
    dist.all_gather(values, buffer)
    result = rank_ordered_mean(values)
    future = torch.futures.Future()
    future.set_result(result)
    return future


def enable_rank_ordered_reduction(model, *, rank, world_size):
    dist = _process_group(rank, world_size)
    _raw_model(model, world_size)
    if dist is None:
        return
    installed = getattr(model, "_voxelshogi_gradient_reduction", None)
    if installed == REDUCTION:
        return
    if installed is not None:
        raise ValueError("different gradient reduction already installed")
    model.register_comm_hook((dist, world_size), _rank_ordered_hook)
    model._voxelshogi_gradient_reduction = REDUCTION


@dataclass(frozen=True)
class DistributedConfig:
    seed: int = 63001
    global_batch: int = 16
    updates: int = 128
    warmup_updates: int = 16
    resume_at: int = 64
    learning_rate: float = 0.0001
    weight_decay: float = 0.01
    threads: int = 2
    device: str = "cuda"

    def __post_init__(self):
        RunConfig(
            seed=self.seed,
            batch_size=self.global_batch,
            learning_rate=self.learning_rate,
            weight_decay=self.weight_decay,
            threads=self.threads,
            device=self.device,
        )
        if (
            self.global_batch % 4
            or type(self.updates) is not int
            or not 2 <= self.updates <= 100000
            or type(self.warmup_updates) is not int
            or not 0 <= self.warmup_updates < self.updates
            or type(self.resume_at) is not int
            or not 0 < self.resume_at < self.updates
        ):
            raise ValueError("fixed global work, warmup and interior resume required")

    def value(self):
        return {
            **asdict(self),
            "precision": "float32",
            "tf32": False,
            "optimizer": RunConfig().value()["optimizer"],
        }


def validate_distributed_binding(binding):
    """Validate immutable global work and topology in a portable resume archive."""
    contract = binding["contract"]
    fields = {
        "schema",
        "source_commit",
        "initial_model_sha256",
        "architecture",
        "world_size",
        "schedule_sha256",
    }
    if (
        isinstance(contract, dict)
        and contract.get("schema") == "voxelshogi-distributed-training-v2"
    ):
        fields.add("gradient_reduction")
        if contract.get("gradient_reduction") != REDUCTION:
            raise ValueError("distributed gradient reduction differs")
    if (
        type(contract) is not dict
        or set(contract) != fields
        or contract["schema"]
        not in (
            "voxelshogi-distributed-training-v1",
            "voxelshogi-distributed-training-v2",
        )
        or contract["source_commit"] != binding["source_commit"]
        or not re.fullmatch(r"[0-9a-f]{40}", binding["source_commit"])
        or not re.fullmatch(r"[0-9a-f]{64}", binding["cache_sha256"])
        or not re.fullmatch(r"[0-9a-f]{64}", contract["initial_model_sha256"])
        or not re.fullmatch(r"[0-9a-f]{64}", contract["schedule_sha256"])
        or type(contract["world_size"]) is not int
        or contract["world_size"] not in (1, 2, 4)
        or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,80}", contract["architecture"])
    ):
        raise ValueError(
            "distributed input, source, order or world-size binding differs"
        )
    try:
        config = DistributedConfig(
            **{k: binding["config"][k] for k in DistributedConfig.__dataclass_fields__}
        ).value()
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("distributed configuration differs") from error
    if config != binding["config"]:
        raise ValueError("distributed configuration differs")


def validate_distributed_payload(payload):
    """Check decoded per-rank RNG and the global update cursor before restore."""
    if sys.platform != "linux":
        raise ValueError("distributed state decoding requires external Linux")
    import random

    import numpy as np
    import torch

    binding = payload["binding"]
    validate_distributed_binding(binding)
    config, progress, rng = binding["config"], payload["progress"], payload["rng"]
    if (
        progress["epoch"] != 0
        or not 0 <= progress["step"] <= config["updates"]
        or progress["next_batch"] != progress["step"]
        or progress["examples"] != progress["step"] * config["global_batch"]
        or progress["best_val_loss"] is not None
        or set(rng) != {"schema", "ranks"}
        or rng["schema"] != "voxelshogi-distributed-rng-v1"
        or type(rng["ranks"]) is not list
        or len(rng["ranks"]) != binding["contract"]["world_size"]
    ):
        raise ValueError("distributed cursor or per-rank RNG inventory differs")
    for state in rng["ranks"]:
        if set(state) != {"python", "numpy", "torch", "cuda"} or len(state["cuda"]) != (
            1 if config["device"] == "cuda" else 0
        ):
            raise ValueError("distributed RNG device/count differs")
        for tensor in [state["torch"], *state["cuda"]]:
            if (
                type(tensor) is not torch.Tensor
                or tensor.dtype != torch.uint8
                or tensor.device.type != "cpu"
                or tensor.ndim != 1
                or not 1 <= tensor.numel() <= 65536
            ):
                raise ValueError("distributed RNG tensor differs")
        try:
            random.Random().setstate(state["python"])
            name, keys, position, has_gauss, cached = state["numpy"]
            np.random.RandomState().set_state(
                (name, np.asarray(keys, dtype=np.uint32), position, has_gauss, cached)
            )
            torch.Generator().set_state(state["torch"])
        except (TypeError, ValueError, RuntimeError) as error:
            raise ValueError("distributed RNG contents differ") from error


def _process_group(rank, world_size):
    if sys.platform != "linux":
        raise ValueError("distributed execution requires external Linux")
    if (
        type(world_size) is not int
        or world_size not in (1, 2, 4)
        or type(rank) is not int
        or not 0 <= rank < world_size
    ):
        raise ValueError("invalid distributed rank/world size")
    import torch.distributed as dist

    if not dist.is_initialized():
        if world_size != 1:
            raise ValueError("distributed process group is missing")
        return None
    if dist.get_world_size() != world_size or dist.get_rank() != rank:
        raise ValueError("distributed process group differs from assignment")
    return dist


def _raw_model(model, world_size):
    from torch.nn.parallel import DistributedDataParallel

    if isinstance(model, DistributedDataParallel):
        return model.module
    if world_size != 1:
        raise ValueError("multiple ranks require DistributedDataParallel")
    return model


def distributed_update(model, optimizer, data, batch, *, device, rank, world_size):
    """Apply one globally fixed update, with DDP averaging equal local means."""
    dist = _process_group(rank, world_size)
    _raw_model(model, world_size)
    enable_rank_ordered_reduction(model, rank=rank, world_size=world_size)
    from training.distributed_benchmark import rank_indices
    from training.selfplay_training import update_step

    indices = rank_indices(batch, rank=rank, world_size=world_size)
    if len({data.rows[i]["value"]["kind"] for i in batch}) != 1:
        raise ValueError("global batch must be homogeneous in value origin")
    metrics = update_step(model, optimizer, data, indices, device=device)
    if dist is not None:
        import torch

        names = ("policy_loss", "value_mse", "loss", "gradient_norm")
        values = torch.tensor(
            [metrics[n] for n in names], dtype=torch.float64, device=device
        )
        dist.all_reduce(values, op=dist.ReduceOp.SUM)
        values /= world_size
        metrics.update(zip(names, values.tolist(), strict=True))
    metrics["examples"] = len(batch)
    return metrics


def _local_rng(device):
    import random

    import numpy as np
    import torch

    state = np.random.get_state()
    return {
        "python": random.getstate(),
        "numpy": [state[0], state[1].tolist(), *state[2:]],
        "torch": torch.get_rng_state(),
        "cuda": [torch.cuda.get_rng_state(device)] if device.type == "cuda" else [],
    }


def _restore_local_rng(state, device):
    import random

    import numpy as np
    import torch

    if set(state) != {"python", "numpy", "torch", "cuda"} or len(state["cuda"]) != (
        1 if device.type == "cuda" else 0
    ):
        raise ValueError("rank RNG device fields differ")
    random.setstate(state["python"])
    name, keys, position, has_gauss, cached = state["numpy"]
    np.random.set_state(
        (name, np.asarray(keys, dtype=np.uint32), position, has_gauss, cached)
    )
    torch.set_rng_state(state["torch"].cpu())
    if state["cuda"]:
        torch.cuda.set_rng_state(state["cuda"][0].cpu(), device)


def _state_fingerprint(state):
    from training.research_data import canonical
    from training.resume_archive import encode_tree

    tree, tensors = encode_tree(state)
    digest = hashlib.sha256(canonical(tree).encode())
    for name, tensor in sorted(tensors.items()):
        digest.update(canonical([name, str(tensor.dtype), list(tensor.shape)]).encode())
        digest.update(tensor.numpy().tobytes(order="C"))
    return digest.hexdigest()


def _checkpoint_context(model, binding, rank, world_size):
    dist = _process_group(rank, world_size)
    if binding.get("contract", {}).get("world_size") != world_size:
        raise ValueError("checkpoint world-size binding differs")
    return dist, _raw_model(model, world_size)


def save_distributed_checkpoint(
    folder, model, optimizer, *, progress, binding, rank, world_size
):
    """Save one shared model/optimizer and every rank's separate RNG state."""
    dist, raw = _checkpoint_context(model, binding, rank, world_size)
    from training.checkpoint import _save_payload
    from training.research_data import fingerprint

    snapshot = {"model": raw.state_dict(), "optimizer": optimizer.state_dict()}
    local = {
        "state_sha256": _state_fingerprint(snapshot),
        "binding_sha256": fingerprint(binding),
        "progress_sha256": fingerprint(progress),
        "rng": _local_rng(next(raw.parameters()).device),
    }
    gathered = [local]
    if dist is not None:
        gathered = [None] * world_size
        dist.all_gather_object(gathered, local)
    if any(
        len({part[k] for part in gathered}) != 1
        for k in ("state_sha256", "binding_sha256", "progress_sha256")
    ):
        raise ValueError("rank model/optimizer, binding or progress diverged")
    result = [None]
    if rank == 0:
        try:
            result[0] = {
                "receipt": _save_payload(
                    folder,
                    {
                        **snapshot,
                        "progress": progress,
                        "binding": binding,
                        "rng": {
                            "schema": "voxelshogi-distributed-rng-v1",
                            "ranks": [part["rng"] for part in gathered],
                        },
                    },
                )
            }
        except Exception as error:
            result[0] = {"error_type": type(error).__name__}
    if dist is not None:
        dist.broadcast_object_list(result, src=0)
    if "receipt" not in result[0]:
        raise ValueError(
            "distributed checkpoint write failed: " + result[0]["error_type"]
        )
    return result[0]["receipt"]


def load_distributed_checkpoint(folder, model, optimizer, *, binding, rank, world_size):
    """Load a hash-verified private checkpoint; select only this rank's RNG."""
    _dist, raw = _checkpoint_context(model, binding, rank, world_size)
    import torch

    from training.checkpoint import checkpoint_receipt

    path, receipt = checkpoint_receipt(folder, binding=binding)
    payload = torch.load(path, map_location="cpu", weights_only=True)
    if (
        set(payload) != {"model", "optimizer", "rng", "progress", "binding"}
        or payload["binding"] != binding
        or payload["progress"] != receipt["progress"]
        or set(payload["rng"]) != {"schema", "ranks"}
        or payload["rng"]["schema"] != "voxelshogi-distributed-rng-v1"
        or len(payload["rng"]["ranks"]) != world_size
    ):
        raise ValueError("distributed payload binding/progress/RNG differs")
    raw.load_state_dict(payload["model"], strict=True)
    optimizer.load_state_dict(payload["optimizer"])
    _restore_local_rng(payload["rng"]["ranks"][rank], next(raw.parameters()).device)
    return payload["progress"]
