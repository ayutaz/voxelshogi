"""Hand-counted trees exercise search math, without executing game rules."""

import copy

import pytest


def win(color):
    return {"Win": {"winner": color, "reason": "Checkmate"}}


class Tree:
    def __init__(self, nodes, name="root"):
        self.nodes, self.name, self.moves = nodes, name, []

    def fork(self):
        return copy.deepcopy(self)

    def snapshot(self):
        node = self.nodes[self.name]
        return {
            "side": node["side"],
            "finished": "result" in node,
            "result": node.get("result"),
        }

    def legal_actions(self):
        return {key: str(key) for key in self.nodes[self.name].get("children", {})}

    def play(self, text):
        action = int(text)
        self.name = self.nodes[self.name]["children"][action]
        self.moves.append(action)


def terminal_choices(side="b"):
    return Tree(
        {
            "root": {
                "side": side,
                "children": {9: "lose", 7: "win"},
                "priors": {9: 0.5, 7: 0.5},
                "value": 0.0,
            },
            "win": {
                "side": "w" if side == "b" else "b",
                "result": win("Black" if side == "b" else "White"),
            },
            "lose": {
                "side": "w" if side == "b" else "b",
                "result": win("White" if side == "b" else "Black"),
            },
        }
    )


def evaluator(calls):
    def evaluate(game):
        calls.append(game.name)
        node = game.nodes[game.name]
        assert "result" not in node, "terminal nodes must never use a model estimate"
        return node["priors"], node["value"]

    return evaluate


@pytest.mark.parametrize("side", ["b", "w"])
def test_puct_visits_values_and_ties_match_hand_counted_terminal_tree(side):
    from training.selfplay_search import SearchConfig, search

    root, calls = terminal_choices(side), []
    result = search(root, evaluator(calls), SearchConfig(simulations=4, cpuct=4))
    # N=0: equal U, choose action7. N=1: tie again, choose7.
    # N=2: U(9)=2sqrt(2) > 1+2sqrt(2)/3, choose9.
    # N=3: 1+2sqrt(3)/3 > -1+2sqrt(3)/2, choose7.
    assert result["visits"] == {7: 3, 9: 1}
    assert result["best_action"] == 7
    assert result["root_value"] == 0.5  # (+1 +1 -1 +1) / 4
    assert result["completed_simulations"] == 4
    assert result["model_evaluations"] == 1 and calls == ["root"]
    assert result["stop_reason"] == "simulations"
    assert root.name == "root" and root.moves == []
    again = search(root, evaluator([]), SearchConfig(simulations=4, cpuct=4))
    assert again == result


def chain():
    return Tree(
        {
            "root": {
                "side": "b",
                "children": {3: "middle"},
                "priors": {3: 1.0},
                "value": 0.8,
            },
            "middle": {
                "side": "w",
                "children": {5: "end"},
                "priors": {5: 1.0},
                "value": 0.25,
            },
            "end": {"side": "b", "result": win("White")},
        }
    )


def test_multilevel_backup_uses_leaf_side_and_includes_terminal_result():
    from training.selfplay_search import SearchConfig, search

    calls = []
    result = search(chain(), evaluator(calls), SearchConfig(simulations=2))
    assert result["visits"] == {3: 2}
    assert result["root_value"] == -0.625  # first -.25, then -1
    assert result["max_depth_reached"] == 2
    assert calls == ["root", "middle"]


def test_depth_bound_uses_explicit_leaf_estimate_without_fabricating_a_draw():
    from training.selfplay_search import SearchConfig, search

    calls = []
    result = search(chain(), evaluator(calls), SearchConfig(simulations=3, max_depth=1))
    assert result["root_value"] == -0.25
    assert result["max_depth_reached"] == 1
    assert result["completed_simulations"] == 3
    assert calls == ["root", "middle"]


def test_cancellation_during_inference_does_not_create_a_completed_visit():
    from training.selfplay_search import SearchConfig, search

    calls, stopped = [], False

    def evaluate(game):
        nonlocal stopped
        result = evaluator(calls)(game)
        if game.name == "middle":
            stopped = True
        return result

    result = search(
        chain(), evaluate, SearchConfig(simulations=5), stop_requested=lambda: stopped
    )
    assert result["stop_reason"] == "interrupted"
    assert result["completed_simulations"] == 0
    assert result["best_action"] is None and result["visits"] == {3: 0}
    assert result["root_value"] is None
    assert calls == ["root", "middle"]


def test_pre_cancelled_search_does_not_run_inference_or_pick_a_random_action():
    from training.selfplay_search import SearchConfig, search

    calls = []
    result = search(
        chain(), evaluator(calls), SearchConfig(), stop_requested=lambda: True
    )
    assert result["stop_reason"] == "interrupted" and result["best_action"] is None
    assert result["completed_simulations"] == result["model_evaluations"] == 0
    assert calls == []


def test_terminal_result_is_not_reused_for_a_fresh_search_request():
    from training.selfplay_search import SearchConfig, search

    # A terminal response from one request must not poison the next request.
    game = Tree({"root": {"side": "b", "result": {"Draw": {"reason": "Repetition"}}}})
    calls = []
    result = search(game, evaluator(calls), SearchConfig())
    assert result["stop_reason"] == "terminal" and result["root_value"] == 0
    assert result["best_action"] is None and result["visits"] == {}
    result2 = search(chain(), evaluator(calls), SearchConfig(simulations=1))
    assert result2["root_value"] == -0.25 and result2["best_action"] == 3
    assert calls == ["root", "middle"]


def test_new_model_priors_are_used_on_each_request():
    from training.selfplay_search import SearchConfig, search

    root = terminal_choices()
    first = search(root, lambda _: ({7: 0.9, 9: 0.1}, 0.0), SearchConfig(simulations=1))
    second = search(
        root, lambda _: ({7: 0.1, 9: 0.9}, 0.0), SearchConfig(simulations=1)
    )
    assert first["best_action"] == 7 and second["best_action"] == 9
    assert first["root_value"] == 1 and second["root_value"] == -1


def test_interruption_preserves_only_the_already_completed_visits():
    from training.selfplay_search import SearchConfig, search

    root, forks = terminal_choices(), 0
    original = root.fork

    def fork():
        nonlocal forks
        forks += 1
        return original()

    root.fork = fork
    # First terminal simulation completes; second is interrupted before backup.
    result = search(
        root,
        evaluator([]),
        SearchConfig(simulations=4),
        stop_requested=lambda: forks >= 2,
    )
    assert result["stop_reason"] == "interrupted"
    assert result["completed_simulations"] == 1
    assert result["visits"] == {7: 1, 9: 0} and result["best_action"] == 7
    assert result["root_value"] == 1


def test_unfinished_empty_legal_set_is_an_adapter_error():
    from training.selfplay_search import SearchConfig, search

    with pytest.raises(ValueError, match="legal actions"):
        search(
            Tree({"root": {"side": "b", "children": {}}}), evaluator([]), SearchConfig()
        )


@pytest.mark.parametrize("result", [None, {"Draw": {"reason": "MaxPlies"}}])
def test_stopped_or_cutoff_root_is_not_a_natural_terminal_label(result):
    from training.selfplay_search import SearchConfig, search

    root = Tree({"root": {"side": "b", "result": result}})
    with pytest.raises(ValueError):
        search(root, evaluator([]), SearchConfig())


@pytest.mark.parametrize(
    "priors,value",
    [
        ({7: 1.0}, 0.0),
        ({7: 0.4, 9: 0.4}, 0.0),
        ({7: float("nan"), 9: 0.5}, 0.0),
        ({7: -0.1, 9: 1.1}, 0.0),
        ({7: True, 9: 0.0}, 0.0),
        ({7: 0.5, 9: 0.5}, float("nan")),
        ({7: 0.5, 9: 0.5}, 1.1),
        ({7: 0.5, 9: 0.5}, True),
    ],
)
def test_model_priors_must_cover_all_and_only_legal_actions_and_values_are_finite(
    priors, value
):
    from training.selfplay_search import SearchConfig, search

    with pytest.raises(ValueError):
        search(terminal_choices(), lambda _: (priors, value), SearchConfig())


@pytest.mark.parametrize(
    "arguments",
    [
        {"simulations": 0},
        {"simulations": True},
        {"simulations": 100001},
        {"max_depth": 0},
        {"max_depth": 257},
        {"cpuct": 0},
        {"cpuct": float("inf")},
    ],
)
def test_invalid_or_unbounded_search_limits_are_rejected(arguments):
    from training.selfplay_search import SearchConfig

    with pytest.raises(ValueError):
        SearchConfig(**arguments)
