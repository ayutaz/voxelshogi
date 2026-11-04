"""Hand-enumerated global schedule and equal, disjoint rank ownership."""

import pytest

from training.distributed_benchmark import global_schedule, rank_indices


def test_rank_partition_covers_exactly_the_same_global_update():
    batch = [7, 2, 9, 0, 4, 6, 1, 8]
    assert rank_indices(batch, world_size=1, rank=0) == batch
    assert [rank_indices(batch, world_size=2, rank=r) for r in range(2)] == [
        [7, 2, 9, 0],
        [4, 6, 1, 8],
    ]
    assert [rank_indices(batch, world_size=4, rank=r) for r in range(4)] == [
        [7, 2],
        [9, 0],
        [4, 6],
        [1, 8],
    ]


@pytest.mark.parametrize(
    "batch,world,rank",
    [
        ([], 1, 0),
        ([1, 1, 2, 3], 2, 0),
        ([0, 1, 2], 2, 0),
        ([0, 1, 2, 3], 3, 0),
        ([0, 1, 2, 3], 2, 2),
        ([0, 1, 2, 3], True, 0),
        ([0, 1, 2, 3], 2, -1),
    ],
)
def test_rank_partition_rejects_unequal_or_invalid_assignments(batch, world, rank):
    with pytest.raises(ValueError):
        rank_indices(batch, world_size=world, rank=rank)


def test_global_schedule_never_mixes_value_origins_or_pads_rank_data():
    # Each epoch has exactly one full batch per origin and two omitted rows.
    kinds = ["terminal-v1"] * 5 + ["bootstrap-v1"] * 5
    schedule = global_schedule(kinds, global_batch=4, updates=5, seed=37)
    batches = schedule["batches"]
    assert len(batches) == 5 and schedule["examples"] == 20
    assert schedule["epochs_entered"] == 3
    assert schedule["dropped_in_entered_epochs"] == 6
    for batch in batches:
        assert len(batch) == len(set(batch)) == 4
        assert len({kinds[i] for i in batch}) == 1
    # A caller's batch or update budget cannot depend on GPU count.
    assert global_schedule(kinds, global_batch=4, updates=5, seed=37) == schedule
    assert global_schedule(kinds, global_batch=4, updates=5, seed=38) != schedule


def test_schedule_records_actual_order_and_rejects_zero_complete_batches():
    only = ["terminal-v1"] * 4
    schedule = global_schedule(only, global_batch=4, updates=2, seed=5)
    assert [sorted(b) for b in schedule["batches"]] == [[0, 1, 2, 3]] * 2
    assert schedule["dropped_in_entered_epochs"] == 0
    with pytest.raises(ValueError, match="complete"):
        global_schedule(["terminal-v1"] * 3, global_batch=4, updates=2, seed=5)


@pytest.mark.parametrize("batch,updates,seed", [(3, 2, 1), (4, 0, 1), (4, 2, -1)])
def test_schedule_rejects_non_comparable_configuration(batch, updates, seed):
    with pytest.raises(ValueError):
        global_schedule(
            ["terminal-v1"] * 8, global_batch=batch, updates=updates, seed=seed
        )
