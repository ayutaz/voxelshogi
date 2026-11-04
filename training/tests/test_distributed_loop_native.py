"""Real fixed-loop AdamW/DDP and fresh-object checkpoint continuation on Linux."""

import json
import sys
from datetime import timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="external Linux only")


def _worker(rank, directory):
    import numpy as np
    import torch
    import torch.distributed as dist
    from torch.nn.parallel import DistributedDataParallel

    from training.distributed_loop import communication_probe, fit_schedule
    from training.distributed_training import DistributedConfig
    from training.research_targets import ACTIONS, visit_policy
    from training.selfplay_training import Samples
    from training.tests.test_checkpoint import assert_state_equal

    root = Path(directory)
    dist.init_process_group(
        "gloo",
        init_method="file://" + str(root / "rendezvous"),
        rank=rank,
        world_size=2,
        timeout=timedelta(seconds=60),
    )
    config = DistributedConfig(
        global_batch=4,
        updates=4,
        warmup_updates=1,
        resume_at=2,
        device="cpu",
        threads=1,
        learning_rate=0.01,
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
        optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=config.learning_rate,
            weight_decay=config.weight_decay,
            foreach=False,
            fused=False,
        )
        return model, optimizer

    features, rows = [], []
    for i, x in enumerate((0.1, 0.2, 0.3, 0.4)):
        encoded = np.zeros((729, 43), dtype=np.float32)
        encoded[0, 0] = x
        features.append(encoded)
        rows.append(
            {
                "id": str(i),
                "policy": visit_policy([0, 1], {0: 1, 1: 1}),
                "value": {"kind": "terminal-v1", "value": 2 * x},
                "legal_actions": [0, 1],
            }
        )
    data = Samples(features, rows, {})
    input_binding = {
        "source_commit": "a" * 40,
        "initial_model_sha256": "d" * 64,
        "architecture": "fixture-v1",
    }
    continuous, optimizer = setup()
    full = fit_schedule(
        continuous,
        optimizer,
        data,
        root / "continuous",
        config=config,
        input_binding=input_binding,
        rank=rank,
        world_size=2,
    )
    expected_rng = torch.rand(3)
    first, first_optimizer = setup()
    partial = fit_schedule(
        first,
        first_optimizer,
        data,
        root / "resumed",
        config=config,
        input_binding=input_binding,
        rank=rank,
        world_size=2,
        max_new_steps=2,
    )
    assert partial["reason"] == "max_steps" and partial["progress"]["step"] == 2
    restored, restored_optimizer = setup()
    resumed = fit_schedule(
        restored,
        restored_optimizer,
        data,
        root / "resumed",
        config=config,
        input_binding=input_binding,
        rank=rank,
        world_size=2,
        resume=True,
    )
    assert_state_equal(continuous.module.state_dict(), restored.module.state_dict())
    assert_state_equal(optimizer.state_dict(), restored_optimizer.state_dict())
    torch.testing.assert_close(torch.rand(3), expected_rng, rtol=0, atol=0)
    assert full["progress"]["examples"] == resumed["progress"]["examples"] == 16
    assert full["measured_updates"] == 3 and full["measured_examples"] == 12
    assert (
        full["continuous_primary_eligible"] is True and full["examples_per_second"] > 0
    )
    assert (
        resumed["continuous_primary_eligible"] is False
        and resumed["examples_per_second"] is None
    )
    assert full["binding"] == resumed["binding"]
    assert len(full["rank_memory"]) == 2
    stopped, stopped_optimizer = setup()
    stop = fit_schedule(
        stopped,
        stopped_optimizer,
        data,
        root / "stopped",
        config=config,
        input_binding=input_binding,
        rank=rank,
        world_size=2,
        stop_requested=lambda: rank == 1,
    )
    assert stop["reason"] == "stopped" and stop["progress"]["step"] == 0
    communication = communication_probe(
        stopped, device="cpu", rank=rank, world_size=2, warmup=1, repeats=3
    )
    assert communication["tensor_bytes"] == 12  # two logits and one value weight, FP32
    assert (
        communication["verified_sum"] == 2
        and len(communication["timings_seconds"]) == 3
    )
    assert communication["max_rank_mean_seconds"] > 0
    (root / f"rank-{rank}.json").write_text(
        json.dumps({"exact_resume": True, "collective_stop": True})
    )
    dist.destroy_process_group()


def test_two_rank_full_loop_matches_fresh_resume_and_collectively_stops(tmp_path):
    import torch.multiprocessing as mp

    mp.spawn(_worker, args=(str(tmp_path),), nprocs=2, join=True)
    assert [
        json.loads((tmp_path / f"rank-{rank}.json").read_text()) for rank in range(2)
    ] == [
        {"exact_resume": True, "collective_stop": True},
        {"exact_resume": True, "collective_stop": True},
    ]
