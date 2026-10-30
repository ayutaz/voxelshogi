"""Handwritten episode ports and sampling oracles; real games run on Linux."""

import copy

import pytest

from training.tests.test_selfplay_search import Tree, chain, evaluator, terminal_choices


class EpisodeTree(Tree):
    def snapshot(self):
        return {
            **super().snapshot(),
            "ruleset_id": "voxelshogi-standard-v1",
            "vsfen": self.name,
        }

    def record(self):
        return {
            "ruleset_id": "voxelshogi-standard-v1",
            "initial": "root",
            "moves": [str(a) for a in self.moves],
            "result": self.snapshot()["result"],
            "termination": None,
        }


def root():
    return EpisodeTree(copy.deepcopy(chain().nodes))


class FixedRandom:
    def __init__(self, draw):
        self.draw = draw

    def random(self):
        return self.draw


def test_temperature_cdf_and_zero_temperature_ties_are_hand_counted():
    from training.selfplay_actor import sample_action

    # tau=.5: weights 3²:1²=9:1, action order is canonical even if input is not.
    assert sample_action({7: 1, 3: 3, 99: 0}, 0.5, FixedRandom(0.85)) == 3
    assert sample_action({7: 1, 3: 3, 99: 0}, 0.5, FixedRandom(0.95)) == 7
    assert sample_action({7: 2, 3: 2}, 0, FixedRandom(0.99)) == 3
    assert sample_action({7: 1, 3: 3}, 1, FixedRandom(0.74)) == 3
    assert sample_action({7: 1, 3: 3}, 1, FixedRandom(0.76)) == 7


def test_root_noise_mixture_and_input_order_are_explicit():
    from training.selfplay_actor import mix_dirichlet

    class Noise:
        def __init__(self):
            self.values = iter([1.0, 4.0])

        def gammavariate(self, alpha, scale):
            assert alpha == 0.3 and scale == 1
            return next(self.values)

    # Noise [1/5,4/5], prior[3/4,1/4], epsilon1/4.
    assert mix_dirichlet({7: 0.25, 3: 0.75}, 0.25, 0.3, Noise()) == pytest.approx(
        {3: 0.6125, 7: 0.3875}
    )


def config(plies=2, **kwargs):
    from training.selfplay_actor import ActorConfig
    from training.selfplay_search import SearchConfig

    options = dict(
        max_plies=plies,
        temperature_plies=0,
        noise_fraction=0,
        search=SearchConfig(simulations=1),
    )
    options.update(kwargs)
    return ActorConfig(**options)


def test_episode_uses_played_visits_and_terminal_outcome_at_last_allowed_ply():
    from training.selfplay_actor import play_episode

    game, calls = root(), []
    episode = play_episode(
        game, evaluator(calls), config(), model_sha256="a" * 64, source_commit="1" * 40
    )
    assert episode["complete"] and episode["termination_kind"] == "natural"
    assert episode["record"]["moves"] == ["3", "5"]
    assert episode["record"]["result"] == {
        "Win": {"winner": "White", "reason": "Checkmate"}
    }
    assert episode["record"]["termination"] is None
    assert [s["value"] for s in episode["samples"]] == [
        {"kind": "terminal-v1", "value": -1.0},
        {"kind": "terminal-v1", "value": 1.0},
    ]
    assert [s["side"] for s in episode["samples"]] == ["b", "w"]
    assert [s["ply"] for s in episode["samples"]] == [0, 1]
    assert [s["policy"]["actions"] for s in episode["samples"]] == [[3], [5]]
    assert all(s["policy"]["total_visits"] == 1 for s in episode["samples"])
    assert episode["model_sha256"] == "a" * 64 and episode["opening"] == game.record()
    assert game.name == "root" and game.moves == []
    assert episode == play_episode(
        root(), evaluator([]), config(), model_sha256="a" * 64, source_commit="1" * 40
    )
    assert calls == ["root", "middle", "middle"]
    assert episode["model_evaluations"] == 3 and episode["bootstrap_evaluations"] == 0


def test_cutoff_is_recorded_separately_and_uses_signed_explicit_bootstrap():
    from training.selfplay_actor import play_episode

    episode = play_episode(
        root(),
        evaluator([]),
        config(1, bootstrap_discount=0.5),
        model_sha256="b" * 64,
        source_commit="1" * 40,
    )
    assert episode["termination_kind"] == "cutoff"
    assert episode["record"]["termination"] == "MaxPlies"
    assert episode["record"]["result"] == {"Draw": {"reason": "MaxPlies"}}
    assert len(episode["samples"]) == 1
    label = episode["samples"][0]["value"]
    assert label["kind"] == "bootstrap-v1" and label["value"] == -0.125
    assert label["bootstrap_side"] == "w" and label["remaining_plies"] == 1
    assert label["model_sha256"] == "b" * 64 and label["discount"] == 0.5
    assert episode["model_evaluations"] == 3 and episode["bootstrap_evaluations"] == 1


def test_cancellation_during_search_produces_no_completed_episode():
    from training.selfplay_actor import play_episode

    calls, stopped = [], False

    def evaluate(game):
        nonlocal stopped
        result = evaluator(calls)(game)
        if game.name == "middle":
            stopped = True
        return result

    game = root()
    with pytest.raises(InterruptedError):
        play_episode(
            game,
            evaluate,
            config(),
            model_sha256="a" * 64,
            source_commit="1" * 40,
            stop_requested=lambda: stopped,
        )
    assert game.record()["moves"] == []


def test_seed_reexecution_has_no_dependency_on_ambient_random_state():
    import random

    from training.selfplay_actor import play_episode
    from training.selfplay_search import SearchConfig

    def game():
        return EpisodeTree(copy.deepcopy(terminal_choices().nodes))

    settings = config(
        1,
        seed=123,
        temperature_plies=1,
        noise_fraction=0.25,
        search=SearchConfig(simulations=4, cpuct=4),
    )
    original = random.getstate()
    try:
        first = play_episode(
            game(),
            evaluator([]),
            settings,
            model_sha256="a" * 64,
            source_commit="1" * 40,
        )
        assert random.getstate() == original
        random.seed(999)
        for _ in range(10):
            random.random()
        before = random.getstate()
        assert (
            play_episode(
                game(),
                evaluator([]),
                settings,
                model_sha256="a" * 64,
                source_commit="1" * 40,
            )
            == first
        )
        assert random.getstate() == before
    finally:
        random.setstate(original)


def test_opening_prefix_does_not_consume_the_additional_ply_budget():
    from training.selfplay_actor import play_episode

    game = root()
    game.play("3")
    episode = play_episode(
        game, evaluator([]), config(1), model_sha256="a" * 64, source_commit="1" * 40
    )
    assert episode["termination_kind"] == "natural"
    assert episode["record"]["moves"] == ["3", "5"]
    assert len(episode["samples"]) == 1 and episode["samples"][0]["ply"] == 1
    assert episode["samples"][0]["value"] == {"kind": "terminal-v1", "value": 1.0}
    assert game.moves == [3]


def test_stop_during_bootstrap_does_not_publish_cutoff_labels():
    from training.selfplay_actor import play_episode

    middle_calls, stopped = 0, False

    def evaluate(game):
        nonlocal middle_calls, stopped
        result = evaluator([])(game)
        if game.name == "middle":
            middle_calls += 1
            stopped = middle_calls == 2
        return result

    with pytest.raises(InterruptedError):
        play_episode(
            root(),
            evaluate,
            config(1),
            model_sha256="a" * 64,
            source_commit="1" * 40,
            stop_requested=lambda: stopped,
        )
    assert stopped and middle_calls == 2


def test_noise_is_mixed_only_at_each_search_root(monkeypatch):
    import training.selfplay_actor as actor

    original, calls, mixed = actor.mix_dirichlet, [], []

    def mix(priors, fraction, alpha, rng):
        mixed.append(calls[-1])
        return original(priors, fraction, alpha, rng)

    monkeypatch.setattr(actor, "mix_dirichlet", mix)
    actor.play_episode(
        root(),
        evaluator(calls),
        config(noise_fraction=0.25),
        model_sha256="a" * 64,
        source_commit="1" * 40,
    )
    assert calls == ["root", "middle", "middle"]
    assert mixed == ["root", "middle"]


def test_episode_identity_is_bound_to_the_source_even_for_the_same_played_moves():
    from training.selfplay_actor import play_episode

    first = play_episode(
        root(), evaluator([]), config(), model_sha256="a" * 64, source_commit="1" * 40
    )
    second = play_episode(
        root(), evaluator([]), config(), model_sha256="a" * 64, source_commit="2" * 40
    )
    assert first["record"] == second["record"]
    assert first["episode_id"] != second["episode_id"]
    assert first["source_commit"] == "1" * 40 and second["source_commit"] == "2" * 40


@pytest.mark.parametrize("source", ["", "A" * 40, True])
def test_invalid_source_commit_is_rejected_before_inference(source):
    from training.selfplay_actor import play_episode

    calls = []
    with pytest.raises(ValueError):
        play_episode(
            root(),
            evaluator(calls),
            config(),
            model_sha256="a" * 64,
            source_commit=source,
        )
    assert calls == []


@pytest.mark.parametrize(
    "arguments",
    [
        {"seed": True},
        {"max_plies": 0},
        {"temperature": -0.1},
        {"temperature": True},
        {"noise_fraction": 1.1},
        {"noise_alpha": 0},
        {"bootstrap_discount": 0},
    ],
)
def test_actor_limits_and_sampling_configuration_are_validated(arguments):
    from training.selfplay_actor import ActorConfig

    with pytest.raises(ValueError):
        ActorConfig(**arguments)


@pytest.mark.parametrize(
    "visits,tau,draw",
    [
        ({3: 0}, 1, 0.5),
        ({3: True}, 1, 0.5),
        ({3: 1}, -0.1, 0.5),
        ({3: 1}, 1, 1.0),
        ({3: 1}, 1, float("nan")),
    ],
)
def test_invalid_sampling_cannot_silently_pick_an_action(visits, tau, draw):
    from training.selfplay_actor import sample_action

    with pytest.raises(ValueError):
        sample_action(visits, tau, FixedRandom(draw))
