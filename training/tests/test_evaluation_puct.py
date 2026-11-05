"""Fixed-policy metadata and hand-counted tree ports; no tensors or shogi on Mac."""

import hashlib

import pytest

from training.tests.test_evaluation_v2 import protocol
from training.tests.test_selfplay_search import evaluator, terminal_choices


@pytest.mark.parametrize("backend", ["torch-cpu", "torch-cuda"])
def test_puct32_protocol_binds_a_distinct_fixed_policy_on_the_same_weights(backend):
    from training.evaluation_v2 import validate_protocol

    spec = protocol()
    before = validate_protocol(spec)
    spec["participants"]["model"].update(policy="puct32-v1", backend=backend)
    assert len(validate_protocol(spec)) == 64 and validate_protocol(spec) != before
    assert spec["participants"]["model"]["artifact_sha256"] == "a" * 64


@pytest.mark.parametrize("backend", ["ort-cpu", "rust", "python-rng"])
def test_puct32_does_not_silently_claim_an_unimplemented_backend(backend):
    from training.evaluation_v2 import validate_protocol

    spec = protocol()
    spec["participants"]["model"].update(policy="puct32-v1", backend=backend)
    with pytest.raises(ValueError):
        validate_protocol(spec)


def test_fixed_search_budget_and_stop_port_are_forwarded_without_noise(monkeypatch):
    from training import evaluation_puct as module

    root, calls = terminal_choices(), []

    def stop():
        return False

    def fake_search(game, evaluate, config, *, stop_requested):
        assert game is root and evaluate is oracle and stop_requested is stop
        assert (config.simulations, config.max_depth, config.cpuct) == (32, 64, 1.0)
        calls.append(1)
        return {
            "stop_reason": "simulations",
            "completed_simulations": 32,
            "best_action": 7,
        }

    oracle = evaluator([])
    monkeypatch.setattr(module, "search", fake_search)
    player = module.PuctPlayer(oracle, stop_requested=stop)
    assert player(root) == player(root) == 7 and calls == [1, 1]


def test_hand_terminal_tree_uses_value_and_visits_without_mutating_the_root():
    from training.evaluation_puct import PuctPlayer

    root, calls = terminal_choices(), []
    # The losing move has higher network prior, but the actual terminal values
    # make action7 the independent winning oracle. Every call starts a new tree.
    root.nodes["root"]["priors"] = {9: 0.75, 7: 0.25}
    player = PuctPlayer(evaluator(calls))
    assert player(root) == player(root) == 7
    assert calls == ["root", "root"]
    assert root.name == "root" and root.moves == []


@pytest.mark.parametrize(
    "kind", ["interrupted", "partial", "illegal", "stopped-after-completion"]
)
def test_interrupted_partial_or_illegal_search_cannot_be_adjudicated(kind, monkeypatch):
    from training import evaluation_puct as module

    result = {
        "stop_reason": "simulations",
        "completed_simulations": 32,
        "best_action": 7,
    }
    if kind == "interrupted":
        result["stop_reason"] = "interrupted"
    elif kind == "partial":
        result["completed_simulations"] = 31
    elif kind == "illegal":
        result["best_action"] = 999
    monkeypatch.setattr(module, "search", lambda *a, **kw: result)
    with pytest.raises(InterruptedError if kind != "illegal" else ValueError):
        module.PuctPlayer(
            evaluator([]), stop_requested=lambda: kind == "stopped-after-completion"
        )(terminal_choices())


def test_loader_dispatch_binds_the_actual_weight_and_stop_port(tmp_path, monkeypatch):
    from training import evaluation_puct as module
    from training.evaluation_v2_runner import _prepare_players, rust_policy_identity

    path = tmp_path / "fixture.safetensors"
    path.write_bytes(b"opaque fake-loader port, never decoded as weights")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    spec = protocol()
    spec["participants"]["model"].update(
        policy="puct32-v1", backend="torch-cuda", artifact_sha256=digest
    )
    spec["participants"]["opponent"]["artifact_sha256"] = rust_policy_identity(
        "alphabeta-v1", spec["source_commit"], spec["search_limits"]
    )
    loaded, stop = [], lambda: False

    def load(actual, *, expected_sha256, device):
        loaded.append((actual, expected_sha256, device))
        return evaluator([])

    monkeypatch.setattr(module, "load_policy_value", load)
    observed = []
    player = _prepare_players(
        spec,
        {"model": path},
        stop_requested=stop,
        observe_input=lambda role, game: observed.append((role, game.name)),
    )["model"]
    assert isinstance(player, module.PuctPlayer)
    assert player.stop_requested is stop
    assert player(terminal_choices()) == 7
    assert observed == [("model", "root")]
    assert loaded == [(path, digest, "cuda")]
    spec["participants"]["model"]["artifact_sha256"] = "b" * 64
    with pytest.raises(ValueError):
        _prepare_players(spec, {"model": path}, stop_requested=stop)
    assert len(loaded) == 1


def test_pool_archive_requires_the_puct_weights_like_the_argmax_weights():
    from training.evaluation_pool_archive import _artifacts

    spec = protocol()
    spec["participants"]["model"]["policy"] = "puct32-v1"
    value = {"puct": {"model": "/external-linux/weights.safetensors"}}
    assert _artifacts({"puct": spec}, value) == value
    with pytest.raises(ValueError):
        _artifacts({"puct": spec}, {"puct": {}})


def test_actual_hand_tree_cancellation_discards_partial_visits():
    from training.evaluation_puct import PuctPlayer

    checks = []

    def stop():
        checks.append(1)
        return len(checks) >= 5

    root = terminal_choices()
    with pytest.raises(InterruptedError):
        PuctPlayer(evaluator([]), stop_requested=stop)(root)
    assert len(checks) >= 5 and root.name == "root" and root.moves == []


def test_assigned_case_context_forwards_the_same_stop_port(monkeypatch):
    from training import evaluation_jobs as module

    spec, stop, calls = protocol(), lambda: False, []
    monkeypatch.setattr(
        module, "checked_execution", lambda *a: ("fake-game", {"model"}, "d" * 40)
    )

    def prepare(p, artifacts, *, stop_requested, observe_input):
        assert p is spec and artifacts == {"model": "opaque"} and stop_requested is stop
        assert observe_input is None
        calls.append(1)
        return {"model": "fake-player"}

    monkeypatch.setattr(module, "_prepare_players", prepare)
    monkeypatch.setattr(module, "execution_runtime", lambda *a: {"fake_runtime": True})
    assert module._context(spec, {"model": "opaque"}, stop_requested=stop) == (
        "fake-game",
        {"model": "fake-player"},
        {"fake_runtime": True},
    )
    assert calls == [1]


def test_pool_forwards_the_puct_weight_path_before_starting_any_process(
    tmp_path, monkeypatch
):
    import json

    from training import evaluation_jobs as module

    spec = protocol()
    spec["participants"]["model"]["policy"] = "puct32-v1"
    plan = module.plan_case_jobs({"puct": spec}, max_workers=1)
    weight, folder = tmp_path / "opaque.safetensors", tmp_path / "pool"
    monkeypatch.setattr(module, "_linux", lambda: None)

    class NoExecution(Exception):
        pass

    def stop_before_launch(jobs, **kwargs):
        assert len(jobs) == 2 and kwargs["max_workers"] == 1
        raise NoExecution

    monkeypatch.setattr(module, "bounded_pool", stop_before_launch)
    with pytest.raises(NoExecution):
        module.run_case_plan(plan, {"puct": {"model": str(weight)}}, folder)
    assert json.loads((folder / "artifacts.json").read_text()) == {
        "puct": {"model": str(weight.resolve())}
    }
    with pytest.raises(ValueError):
        module.run_case_plan(plan, {"puct": {}}, tmp_path / "missing")
    assert not (tmp_path / "missing").exists()


def test_fixed_policy_does_not_accept_hidden_budget_overrides():
    from training.evaluation_v2 import validate_protocol

    for policy in ("puct31-v1", "puct32-v2"):
        spec = protocol()
        spec["participants"]["model"]["policy"] = policy
        with pytest.raises(ValueError):
            validate_protocol(spec)
    spec = protocol()
    spec["participants"]["model"].update(policy="puct32-v1", simulations=31)
    with pytest.raises(ValueError):
        validate_protocol(spec)


def test_execution_requires_puct_artifacts_before_allocating_a_player(monkeypatch):
    import sys
    from types import SimpleNamespace

    from training import evaluation_v2_runner as module
    from training.tests.test_evaluation_v2_runner import FakeGame

    spec = protocol()
    spec["participants"]["model"]["policy"] = "puct32-v1"
    factory = SimpleNamespace(from_record=lambda record: FakeGame(record))
    monkeypatch.setitem(sys.modules, "voxelshogi", SimpleNamespace(Game=factory))
    monkeypatch.setattr(module.sys, "platform", "linux")
    monkeypatch.setattr(
        module.subprocess,
        "check_output",
        lambda args, **kw: spec["source_commit"] if args[1] == "rev-parse" else "",
    )
    assert module.checked_execution(spec, {"model": "opaque"}) == (
        factory,
        {"model"},
        spec["source_commit"],
    )
    with pytest.raises(ValueError, match="artifact"):
        module.checked_execution(spec, {})


def test_observer_sees_the_actual_nonterminal_puct_queries_including_branches():
    from training.evaluation_puct import PuctPlayer
    from training.tests.test_selfplay_search import chain

    root, queried, calls = chain(), [], []
    player = PuctPlayer(
        evaluator(calls), observe_input=lambda game: queried.append(game.name)
    )
    assert player(root) == player(root) == 3
    assert queried == calls == ["root", "middle", "root", "middle"]
    assert root.name == "root" and root.moves == []


def test_argmax_observer_retains_the_actual_player_and_its_result():
    from training.evaluation_v2_runner import _observed_player

    root, events = terminal_choices(), []

    def choose(game):
        assert game is root
        events.append("inference")
        return 9

    def observe(role, game):
        assert game is root
        events.append(role)

    assert _observed_player(choose, "model", None) is choose
    assert _observed_player(choose, "model", observe)(root) == 9
    assert events == ["model", "inference"]


def test_public_sequential_runner_forwards_the_observer(tmp_path, monkeypatch):
    from training import evaluation_v2_runner as module

    def observer(role, game):
        pass

    monkeypatch.setattr(module.sys, "platform", "linux")

    def execute(*args, stop_requested, resume, observe_input):
        assert observe_input is observer and resume is False
        return {"fake_ports_only": True}

    monkeypatch.setattr(module, "_execute_protocol", execute)
    assert module.run_protocol(
        protocol(), {}, tmp_path / "run", observe_input=observer
    ) == {"fake_ports_only": True}
