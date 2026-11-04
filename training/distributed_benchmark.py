"""Pure scheduling contracts shared by the 1/2/4 GPU training comparison."""

from training.research_data import fingerprint
from training.selfplay_training import epoch_indices


def rank_indices(batch, *, world_size, rank):
    """Partition a fixed global update; never pad, repeat, or discard rank rows."""
    if (
        type(world_size) is not int
        or world_size not in (1, 2, 4)
        or type(rank) is not int
        or not 0 <= rank < world_size
        or type(batch) is not list
        or not batch
        or any(type(i) is not int or i < 0 for i in batch)
        or len(set(batch)) != len(batch)
        or len(batch) % world_size
    ):
        raise ValueError("equal, unique rank partitions for 1/2/4 GPUs required")
    width = len(batch) // world_size
    return batch[rank * width : (rank + 1) * width]


def global_schedule(kinds, *, global_batch, updates, seed):
    """Freeze the full update order independently of the number of GPUs.

    Incomplete homogeneous batches are omitted globally, never per rank. The
    omission count covers each epoch entered, including an unfinished last one.
    """
    if (
        type(global_batch) is not int
        or not 4 <= global_batch <= 64
        or global_batch % 4
        or type(updates) is not int
        or not 1 <= updates <= 100000
        or type(seed) is not int
        or seed < 0
    ):
        raise ValueError("fixed global batch divisible by four and updates required")
    order, epoch, dropped = [], 0, 0
    while len(order) < updates:
        candidates = epoch_indices(kinds, global_batch, seed=seed, epoch=epoch)
        complete = [batch for batch in candidates if len(batch) == global_batch]
        if not complete:
            raise ValueError("no complete homogeneous global batches")
        dropped += sum(len(batch) for batch in candidates if len(batch) < global_batch)
        order.extend(complete[: updates - len(order)])
        epoch += 1
    return {
        "schema": "voxelshogi-distributed-global-schedule-v1",
        "global_batch": global_batch,
        "updates": updates,
        "seed": seed,
        "batches": order,
        "order_sha256": fingerprint(order),
        "examples": global_batch * updates,
        "epochs_entered": epoch,
        "dropped_in_entered_epochs": dropped,
    }
