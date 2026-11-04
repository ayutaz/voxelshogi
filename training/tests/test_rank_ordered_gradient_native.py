"""Real four-rank transport must preserve a literal, cancellation-sensitive FP32 mean."""

import json
import sys
from datetime import timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="external Linux only")


def _worker(rank, directory):
    import torch
    import torch.distributed as dist
    from torch.nn.parallel import DistributedDataParallel

    from training.distributed_training import enable_rank_ordered_reduction

    torch.set_num_threads(1)
    root = Path(directory)
    dist.init_process_group(
        "gloo",
        init_method="file://" + str(root / "rendezvous"),
        rank=rank,
        world_size=4,
        timeout=timedelta(seconds=60),
    )
    try:

        class Scalar(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.weight = torch.nn.Parameter(torch.tensor(0.0))

            def forward(self, coefficient):
                return self.weight * coefficient

        model = DistributedDataParallel(Scalar())
        calls = []
        original_register = model.register_comm_hook

        def record_registration(state, hook):
            calls.append(hook.__name__)
            return original_register(state, hook)

        model.register_comm_hook = record_registration
        enable_rank_ordered_reduction(model, rank=rank, world_size=4)
        enable_rank_ordered_reduction(model, rank=rank, world_size=4)
        assert calls == ["_rank_ordered_hook"]
        assert model._voxelshogi_gradient_reduction == "rank-ordered-float32-v1"
        optimizer = torch.optim.SGD(model.parameters(), lr=0.5)
        model((100_000_000.0, 1.0, -100_000_000.0, 1.0)[rank]).backward()
        assert model.module.weight.grad.item() == 0.25
        optimizer.step()
        assert model.module.weight.item() == -0.125
        optimizer.zero_grad(set_to_none=True)
        model(float(rank + 1)).backward()
        assert model.module.weight.grad.item() == 2.5
        optimizer.step()
        assert model.module.weight.item() == -1.375
        (root / f"rank-{rank}.json").write_text(
            json.dumps({"mean": 0.25, "after_two_steps": -1.375})
        )
    finally:
        dist.destroy_process_group()


def test_four_rank_hook_uses_the_hand_fp32_mean_and_registers_once(tmp_path):
    import torch.multiprocessing as mp

    mp.spawn(_worker, args=(str(tmp_path),), nprocs=4, join=True)
    assert [
        json.loads((tmp_path / f"rank-{rank}.json").read_text()) for rank in range(4)
    ] == [{"mean": 0.25, "after_two_steps": -1.375}] * 4
