"""One-rank group metadata must not turn an ordinary model into DDP."""

import pytest


@pytest.mark.parametrize("initialized", [False, True])
def test_single_rank_validates_assignment_and_model_without_registering_ddp_hook(
    monkeypatch, initialized
):
    from training import distributed_training as module

    events = []
    model = object()  # Deliberately has no DDP registration method.
    group = object() if initialized else None

    def process(rank, size):
        events.append(("assignment", rank, size))
        return group

    def raw(value, size):
        assert value is model
        events.append(("model", size))
        return value

    monkeypatch.setattr(module, "_process_group", process)
    monkeypatch.setattr(module, "_raw_model", raw)
    module.enable_rank_ordered_reduction(model, rank=0, world_size=1)
    assert events == [("assignment", 0, 1), ("model", 1)]


def test_single_rank_still_rejects_an_invalid_process_assignment(monkeypatch):
    from training import distributed_training as module

    def reject(*_):
        raise ValueError("invalid assignment fixture")

    monkeypatch.setattr(module, "_process_group", reject)
    with pytest.raises(ValueError, match="invalid assignment fixture"):
        module.enable_rank_ordered_reduction(object(), rank=0, world_size=1)
