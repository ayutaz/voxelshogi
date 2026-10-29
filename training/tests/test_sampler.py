"""Pure metadata checks; no tensors, search, or training on Mac."""

import pytest


def test_epoch_sampler_covers_every_example_and_keeps_partial_final_batch():
    from training.learning import epoch_batches

    batches = list(epoch_batches(7, 3, seed=314159, epoch=0))
    assert [len(part) for part in batches] == [3, 3, 1]
    assert sorted(item for part in batches for item in part) == list(range(7))
    assert list(epoch_batches(7, 3, seed=314159, epoch=0)) == batches
    assert list(epoch_batches(7, 3, seed=314159, epoch=1)) != batches
    assert list(epoch_batches(7, 3, seed=1, epoch=0)) != batches
    for cursor in range(4):
        assert (
            list(epoch_batches(7, 3, seed=314159, epoch=0, start_batch=cursor))
            == batches[cursor:]
        )


@pytest.mark.parametrize(
    "args",
    [
        (0, 1, 0, 0, 0),
        (2, 0, 0, 0, 0),
        (2, 1, -1, 0, 0),
        (2, 1, 0, -1, 0),
        (2, 1, 0, 0, 3),
        (True, 1, 0, 0, 0),
    ],
)
def test_sampler_rejects_empty_or_invalid_resume_state(args):
    from training.learning import epoch_batches

    n, size, seed, epoch, start = args
    with pytest.raises(ValueError):
        list(epoch_batches(n, size, seed=seed, epoch=epoch, start_batch=start))
