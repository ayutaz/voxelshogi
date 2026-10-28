"""Remote limits never turn a local job into an unbounded production run."""

import pytest


def test_remote_budget_requires_linux_and_explicit_positive_approved_duration(
    monkeypatch,
):
    import training.runner as runner

    monkeypatch.setattr(runner.sys, "platform", "darwin")
    with pytest.raises(ValueError, match="Linux"):
        runner.run_remote_bounded(
            [], ledger="unused", seconds=3600, approved_seconds=3600
        )
    monkeypatch.setattr(runner.sys, "platform", "linux")
    for approved, seconds in [(0, 1), (3600, 3601), (True, 1), (86401, 1)]:
        with pytest.raises(ValueError):
            runner.run_remote_bounded(
                [], ledger="unused", seconds=seconds, approved_seconds=approved
            )
