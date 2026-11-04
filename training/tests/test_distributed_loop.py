"""Hand-counted update cursors/times; fake ports only, no tensors on Mac."""

import pytest

from training.distributed_benchmark import global_schedule
from training.distributed_training import DistributedConfig


def fixture():
    config = DistributedConfig(
        global_batch=4, updates=4, warmup_updates=1, resume_at=2, device="cpu"
    )
    schedule = global_schedule(
        ["terminal-v1"] * 4, global_batch=4, updates=4, seed=config.seed
    )
    progress = {
        "epoch": 0,
        "next_batch": 0,
        "step": 0,
        "examples": 0,
        "best_val_loss": None,
    }
    return config, schedule, progress


def test_fixed_loop_counts_global_work_excludes_warmup_and_saves_at_frozen_boundary():
    from training.distributed_loop import execute_updates

    config, schedule, progress = fixture()
    seen, saved, events = [], [], []

    def update(batch, step):
        seen.append((list(batch), step))
        return {"examples": 4, "elapsed_seconds": 2.0 * step, "loss": 0.5}

    result = execute_updates(
        schedule,
        progress,
        config=config,
        update=update,
        save=lambda p: saved.append(dict(p)),
        record=events.append,
    )
    assert [step for _, step in seen] == [1, 2, 3, 4]
    assert [p["step"] for p in saved] == [2, 4]
    assert result["progress"]["examples"] == 16 and result["new_steps"] == 4
    assert result["measured_updates"] == 3 and result["measured_examples"] == 12
    assert result["measured_seconds"] == 18.0
    assert result["continuous_primary_eligible"] is True
    assert result["examples_per_second"] == pytest.approx(2 / 3)
    assert [e["global_step"] for e in events] == [1, 2, 3, 4]
    assert progress["step"] == 0  # a caller's initial proof is immutable


def test_resume_reads_only_remaining_global_updates_and_does_not_claim_primary_speed():
    from training.distributed_loop import execute_updates

    config, schedule, progress = fixture()

    def update(batch, step):
        return {"examples": 4, "elapsed_seconds": 1.0, "loss": 0.25}

    first = execute_updates(
        schedule,
        progress,
        config=config,
        update=update,
        save=lambda p: None,
        record=lambda e: None,
        max_new_steps=2,
    )
    assert first["reason"] == "max_steps" and first["progress"]["step"] == 2
    assert (
        first["continuous_primary_eligible"] is False
        and first["examples_per_second"] is None
    )
    seen = []

    def remaining(batch, step):
        seen.append(step)
        return update(batch, step)

    second = execute_updates(
        schedule,
        first["progress"],
        config=config,
        update=remaining,
        save=lambda p: None,
        record=lambda e: None,
    )
    assert seen == [3, 4] and second["progress"]["examples"] == 16
    assert second["measured_updates"] == 2 and second["reason"] == "complete"
    assert (
        second["continuous_primary_eligible"] is False
        and second["examples_per_second"] is None
    )


@pytest.mark.parametrize(
    "change", ["cursor", "examples", "order", "count", "metric", "loss"]
)
def test_loop_rejects_changed_work_cursor_and_nonfinite_measurement(change):
    from training.distributed_loop import execute_updates

    config, schedule, progress = fixture()
    metrics = {"examples": 4, "elapsed_seconds": 1.0, "loss": 0.25}
    if change == "cursor":
        progress["next_batch"] = 1
    elif change == "examples":
        progress["examples"] = 4
    elif change == "order":
        schedule["batches"][0].reverse()
    elif change == "count":
        metrics["examples"] = 2
    elif change == "metric":
        metrics["elapsed_seconds"] = float("nan")
    else:
        metrics["loss"] = float("nan")
    with pytest.raises(ValueError):
        execute_updates(
            schedule,
            progress,
            config=config,
            update=lambda *a: metrics,
            save=lambda p: None,
            record=lambda e: None,
        )


def test_fit_rejects_mac_before_importing_torch(monkeypatch):
    from types import SimpleNamespace

    from training import distributed_loop as loop

    monkeypatch.setattr(loop, "sys", SimpleNamespace(platform="darwin"), raising=False)
    with pytest.raises(ValueError, match="Linux"):
        loop.fit_schedule(
            None,
            None,
            None,
            "unused",
            config=None,
            input_binding={},
            rank=0,
            world_size=1,
        )
    with pytest.raises(ValueError, match="Linux"):
        loop.communication_probe(None, device="cuda", rank=0, world_size=1)


def test_stop_after_an_update_saves_that_global_cursor_without_emitting_more_work():
    from training.distributed_loop import execute_updates

    config, schedule, progress = fixture()
    seen, saved = [], []

    def update(batch, step):
        seen.append(step)
        return {"examples": 4, "elapsed_seconds": 1.0, "loss": 0.25}

    result = execute_updates(
        schedule,
        progress,
        config=config,
        update=update,
        save=lambda p: saved.append(dict(p)),
        record=lambda e: None,
        stop_requested=lambda: bool(seen),
    )
    assert seen == [1] and [p["step"] for p in saved] == [1]
    assert result["reason"] == "stopped" and result["progress"]["examples"] == 4
    assert result["measured_updates"] == 0 and result["examples_per_second"] is None


@pytest.mark.parametrize("device_type", ["cuda", "cpu"])
def test_rank_seed_targets_its_own_cuda_device_without_seeding_other_devices(
    device_type,
):
    from contextlib import contextmanager
    from types import SimpleNamespace

    from training.distributed_loop import seed_rank

    calls, active = [], [0]

    @contextmanager
    def device(target):
        previous = active[0]
        active[0] = target.index
        try:
            yield
        finally:
            active[0] = previous

    torch = SimpleNamespace(
        random=SimpleNamespace(
            default_generator=SimpleNamespace(
                manual_seed=lambda seed: calls.append(("cpu-torch", seed))
            )
        ),
        cuda=SimpleNamespace(
            device=device,
            manual_seed=lambda seed: calls.append(("cuda", active[0], seed)),
        ),
    )
    seed_rank(
        63001,
        1,
        SimpleNamespace(type=device_type, index=1),
        random=SimpleNamespace(seed=lambda seed: calls.append(("python", seed))),
        np=SimpleNamespace(
            random=SimpleNamespace(seed=lambda seed: calls.append(("numpy", seed)))
        ),
        torch=torch,
    )
    expected = [("python", 63002), ("numpy", 63002), ("cpu-torch", 63002)]
    if device_type == "cuda":
        expected.append(("cuda", 1, 63002))
    assert calls == expected and active[0] == 0
