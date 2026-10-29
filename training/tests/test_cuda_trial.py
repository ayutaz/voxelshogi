"""Independent numeric drift oracles, executed with CPU tensors on Linux CI."""

import pytest


def test_resume_comparison_reports_drift_and_requires_integer_state_identity():
    import torch

    from training.cuda_trial import compare_trees

    first = {
        "weight": torch.tensor([0.0, 1.0]),
        "optimizer": {"step": torch.tensor(3.0)},
    }
    same = {
        "weight": torch.tensor([0.0, 1.0]),
        "optimizer": {"step": torch.tensor(3.0)},
    }
    result = compare_trees(first, same)
    assert result["floating_values"] == 2 and result["maximum_absolute_error"] == 0
    close = {**same, "weight": torch.tensor([5e-7, 1.0])}
    assert compare_trees(first, close)["maximum_absolute_error"] == pytest.approx(5e-7)
    with pytest.raises(ValueError):
        compare_trees(first, {**same, "weight": torch.tensor([2e-6, 1.0])})
    with pytest.raises(ValueError):
        compare_trees(first, {**same, "optimizer": {"step": torch.tensor(3.000001)}})
    with pytest.raises(ValueError):
        compare_trees(first, {**same, "weight": torch.tensor([float("nan"), 1.0])})


def test_resume_comparison_rejects_missing_keys_changed_shapes_or_rng():
    import torch

    from training.cuda_trial import compare_trees

    for first, second in (
        ({"a": 1}, {"b": 1}),
        (torch.zeros(2), torch.zeros(3)),
        (torch.tensor([1, 2]), torch.tensor([1, 3])),
        ([1, 2], [1]),
        (None, 0),
    ):
        with pytest.raises(ValueError):
            compare_trees(first, second)
    with pytest.raises(ValueError):
        compare_trees(torch.tensor([0.0]), torch.tensor([5e-7]), atol=0, rtol=0)
