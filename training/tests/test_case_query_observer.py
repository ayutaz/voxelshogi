"""Fake-port proof that assigned pairs retain neural-query observation."""

from contextlib import nullcontext

import pytest

from training.tests.test_evaluation_v2 import protocol


def test_case_context_forwards_observer_and_stop_to_the_real_player_boundary(
    monkeypatch,
):
    import training.evaluation_jobs as module

    spec = protocol()
    observer = object()

    def stop():
        return False

    called = []
    game, players, runtime = object(), object(), {"source_commit": "d" * 40}
    monkeypatch.setattr(
        module, "checked_execution", lambda p, a: (game, {"model"}, "d" * 40)
    )
    monkeypatch.setattr(module, "execution_runtime", lambda *args: runtime)

    def prepare(p, a, **kwargs):
        called.append((p, a, kwargs))
        return players

    monkeypatch.setattr(module, "_prepare_players", prepare)
    assert module._context(
        spec, {"model": "opaque"}, stop_requested=stop, observe_input=observer
    ) == (game, players, runtime)
    assert called == [
        (spec, {"model": "opaque"}, {"stop_requested": stop, "observe_input": observer})
    ]


def test_assigned_pair_forwards_observer_before_starting_any_game(
    monkeypatch, tmp_path
):
    import training.evaluation_jobs as module

    observer, seen = object(), []

    def stop():
        return False

    monkeypatch.setattr(module, "_linux", lambda: None)
    monkeypatch.setattr(module, "_lease", lambda path: nullcontext())

    def context(spec, artifacts, **kwargs):
        seen.append(kwargs)
        raise InterruptedError("fake boundary; no engine execution")

    monkeypatch.setattr(module, "_context", context)
    with pytest.raises(InterruptedError, match="fake boundary"):
        module.run_case_assignment(
            protocol(),
            {},
            tmp_path / "case",
            case_id="tactic",
            stop_requested=stop,
            observe_input=observer,
        )
    assert seen == [{"stop_requested": stop, "observe_input": observer}]
