"""Two real Gloo ranks: independent gradient and per-rank RNG resume oracles."""

import json
import math
import sys
from datetime import timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="external Linux only")


def _worker(rank, world_size, directory):
    import random

    import numpy as np
    import torch
    import torch.distributed as dist
    from torch.nn.parallel import DistributedDataParallel

    from training.checkpoint import seed_all
    from training.distributed_training import (
        distributed_update,
        load_distributed_checkpoint,
        save_distributed_checkpoint,
    )
    from training.research_targets import ACTIONS, visit_policy
    from training.selfplay_training import Samples

    torch.set_num_threads(1)
    directory = Path(directory)
    dist.init_process_group(
        "gloo",
        init_method="file://" + str(directory / "rendezvous"),
        rank=rank,
        world_size=world_size,
        timeout=timedelta(seconds=60),
    )

    class Heads(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.logits = torch.nn.Parameter(torch.zeros(2))
            self.weight = torch.nn.Parameter(torch.tensor(0.0))

        def forward(self, features):
            logits = torch.nn.functional.pad(self.logits, (0, ACTIONS - 2))
            return logits.expand(len(features), -1), self.weight * features[:, :1, 0]

    def setup():
        model = DistributedDataParallel(Heads())
        optimizer = torch.optim.SGD(model.parameters(), lr=0.1, momentum=0.5)
        return model, optimizer

    features, rows = [], []
    for i, x in enumerate((0.1, 0.2, 0.3, 0.4)):
        feature = np.zeros((729, 43), dtype=np.float32)
        feature[0, 0] = x
        features.append(feature)
        rows.append(
            {
                "id": str(i),
                "policy": visit_policy([0, 1], {0: 1, 1: 1}),
                "value": {"kind": "terminal-v1", "value": 2 * x},
                "legal_actions": [0, 1],
            }
        )
    data = Samples(features, rows, {})
    from training import selfplay_training

    original_update, seen = selfplay_training.update_step, []

    def recording_update(model, optimizer, data, indices, *, device):
        seen.append(list(indices))
        return original_update(model, optimizer, data, indices, device=device)

    selfplay_training.update_step = recording_update
    binding = {"source_commit": "a" * 40, "contract": {"world_size": world_size}}
    model, optimizer = setup()
    seed_all(71 + rank)
    metrics = distributed_update(
        model,
        optimizer,
        data,
        [0, 1, 2, 3],
        device="cpu",
        rank=rank,
        world_size=world_size,
    )
    # MSE=mean((0*x-2*x)^2)=0.3, grad=-4*mean(x^2)=-0.3.
    assert metrics["examples"] == 4
    assert metrics["value_mse"] == pytest.approx(0.3, abs=1e-6)
    assert metrics["policy_loss"] == pytest.approx(math.log(2), abs=1e-6)
    assert metrics["gradient_norm"] == pytest.approx(0.3, abs=1e-6)
    assert model.module.weight.item() == pytest.approx(0.03, abs=1e-7)
    assert seen[-1] == ([0, 1] if rank == 0 else [2, 3])
    progress = {
        "epoch": 0,
        "next_batch": 1,
        "step": 1,
        "examples": 4,
        "best_val_loss": None,
    }
    save_distributed_checkpoint(
        directory / "checkpoints",
        model,
        optimizer,
        progress=progress,
        binding=binding,
        rank=rank,
        world_size=world_size,
    )
    expected_rng = (random.random(), float(np.random.random()), torch.rand(3))
    restored, restored_optimizer = setup()
    seed_all(999)
    loaded = load_distributed_checkpoint(
        directory / "checkpoints",
        restored,
        restored_optimizer,
        binding=binding,
        rank=rank,
        world_size=world_size,
    )
    assert loaded == progress
    assert random.random() == expected_rng[0]
    assert float(np.random.random()) == expected_rng[1]
    torch.testing.assert_close(torch.rand(3), expected_rng[2], rtol=0, atol=0)
    next_metrics = distributed_update(
        restored,
        restored_optimizer,
        data,
        [0, 1, 2, 3],
        device="cpu",
        rank=rank,
        world_size=world_size,
    )
    # Second gradient=-0.2955; momentum=-0.2955+0.5*(-0.3).
    assert restored.module.weight.item() == pytest.approx(0.07455, abs=1e-7)
    assert next_metrics["gradient_norm"] == pytest.approx(0.2955, abs=1e-6)
    (directory / f"rank-{rank}.json").write_text(
        json.dumps(
            {
                "weight_after_resume": restored.module.weight.item(),
                "examples": next_metrics["examples"],
                "per_rank_rng_restored": True,
            }
        )
    )
    # A real typed archive uses AdamW with the config it declares. The preceding
    # hand calculation deliberately uses SGD and remains a separate oracle.
    from training.checkpoint import atomic_json
    from training.distributed_benchmark import global_schedule
    from training.distributed_training import DistributedConfig
    from training.resume_archive import pack_run, restore_run
    from training.tests.test_checkpoint import assert_state_equal

    config = DistributedConfig(
        global_batch=4,
        updates=2,
        warmup_updates=0,
        resume_at=1,
        device="cpu",
        threads=1,
        learning_rate=0.01,
    )

    def adam():
        model = DistributedDataParallel(Heads())
        optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=config.learning_rate,
            weight_decay=config.weight_decay,
            foreach=False,
            fused=False,
        )
        return model, optimizer

    a, ao = adam()
    schedule = global_schedule(data.kinds, global_batch=4, updates=2, seed=config.seed)
    archive_binding = {
        "source_commit": "a" * 40,
        "cache_sha256": data.sha256,
        "config": config.value(),
        "environment": {"device": "cpu"},
        "contract": {
            "schema": "voxelshogi-distributed-training-v1",
            "source_commit": "a" * 40,
            "initial_model_sha256": "d" * 64,
            "architecture": "fixture-v1",
            "world_size": world_size,
            "schedule_sha256": schedule["order_sha256"],
        },
    }
    run = directory / "adam"
    if rank == 0:
        run.mkdir()
        atomic_json(
            run / "run.json",
            {"schema": "voxelshogi-training-run-v1", "binding": archive_binding},
        )
    dist.barrier()
    distributed_update(
        a,
        ao,
        data,
        schedule["batches"][0],
        device="cpu",
        rank=rank,
        world_size=world_size,
    )
    save_distributed_checkpoint(
        run / "checkpoints",
        a,
        ao,
        progress=progress,
        binding=archive_binding,
        rank=rank,
        world_size=world_size,
    )
    distributed_update(
        a,
        ao,
        data,
        schedule["batches"][1],
        device="cpu",
        rank=rank,
        world_size=world_size,
    )
    if rank == 0:
        pack_run(run, directory / "archive", profile="distributed")
        restore_run(
            directory / "archive",
            directory / "restored",
            expected_binding=archive_binding,
            profile="distributed",
        )
    dist.barrier()
    b, bo = adam()
    load_distributed_checkpoint(
        directory / "restored/checkpoints",
        b,
        bo,
        binding=archive_binding,
        rank=rank,
        world_size=world_size,
    )
    distributed_update(
        b,
        bo,
        data,
        schedule["batches"][1],
        device="cpu",
        rank=rank,
        world_size=world_size,
    )
    assert_state_equal(a.module.state_dict(), b.module.state_dict())
    assert_state_equal(ao.state_dict(), bo.state_dict())
    if rank == 1:
        bo.param_groups[0]["lr"] += 0.01
    with pytest.raises(ValueError, match="diverged"):
        save_distributed_checkpoint(
            directory / "diverged",
            b,
            bo,
            progress=progress,
            binding=archive_binding,
            rank=rank,
            world_size=world_size,
        )
    dist.destroy_process_group()


def test_two_ranks_use_global_mean_and_restore_momentum_and_each_rng(tmp_path):
    import torch.multiprocessing as mp

    mp.spawn(_worker, args=(2, str(tmp_path)), nprocs=2, join=True)
    reports = [
        json.loads((tmp_path / f"rank-{rank}.json").read_text()) for rank in range(2)
    ]
    assert all(r["examples"] == 4 and r["per_rank_rng_restored"] for r in reports)
    assert reports[0]["weight_after_resume"] == reports[1]["weight_after_resume"]
