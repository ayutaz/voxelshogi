"""Preregistered operator measurement and fake clock, without CUDA or a game."""

from copy import deepcopy

import pytest


def test_probe_freezes_all_four_configs_batches_seed_and_distinct_numeric_fixtures():
    from training.research_probe import probe_protocol, validate_probe

    spec = probe_protocol("d" * 40)
    assert validate_probe(spec) == spec
    assert set(spec["architectures"]) == {"full", "axial", "geometry", "cnn"}
    assert spec["batch_sizes"] == [1, 4, 8, 16]
    assert spec["warmup_steps"] == 8 and spec["measured_steps"] == 32
    assert spec["model_seed"] == 66001 and spec["precision"] == "float32"
    assert spec["tf32"] is False and spec["fixture_indices"] == [0, 3]
    assert spec["maximum_seconds"] == 1800
    assert spec["measurement_scope"].startswith("synthetic operator load")
    spec["architectures"]["full"]["width"] = 1
    assert probe_protocol("d" * 40)["architectures"]["full"]["width"] == 512
    with pytest.raises(ValueError):
        validate_probe(spec)


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_commit", "bad"),
        ("model_seed", 66002),
        ("tf32", True),
        ("batch_sizes", [1, 16]),
        ("warmup_steps", 0),
        ("measured_steps", 1),
        ("maximum_seconds", 3600),
        ("fixture_indices", [0]),
    ],
)
def test_probe_rejects_undeclared_conditions(field, value):
    from training.research_probe import probe_protocol, validate_probe

    spec = probe_protocol("d" * 40)
    spec[field] = value
    with pytest.raises(ValueError):
        validate_probe(spec)


def test_warmup_and_synchronization_are_outside_the_measured_update_count():
    from training.research_probe import measure_steps

    events = []
    moments = iter((10.0, 12.0))

    def clock():
        events.append("clock")
        return next(moments)

    result = measure_steps(
        lambda: events.append("step"),
        lambda: events.append("sync"),
        batch_size=4,
        warmup_steps=8,
        measured_steps=32,
        clock=clock,
    )
    assert events == ["step"] * 8 + ["sync", "clock"] + ["step"] * 32 + [
        "sync",
        "clock",
    ]
    assert result == {
        "warmup_steps": 8,
        "measured_steps": 32,
        "batch_size": 4,
        "measured_examples": 128,
        "elapsed_seconds": 2.0,
        "examples_per_second": 64.0,
    }


def test_stop_cannot_be_reported_as_a_shorter_successful_measurement():
    from training.research_probe import measure_steps

    steps = []
    with pytest.raises(InterruptedError):
        measure_steps(
            lambda: steps.append(1),
            lambda: None,
            batch_size=1,
            warmup_steps=8,
            measured_steps=32,
            stop_requested=lambda: len(steps) >= 3,
        )
    assert len(steps) == 3


def test_invalid_measurement_arguments_and_nonpositive_elapsed_are_rejected():
    from training.research_probe import measure_steps

    base = {"batch_size": 4, "warmup_steps": 8, "measured_steps": 32}
    for field, value in (
        ("batch_size", True),
        ("batch_size", 0),
        ("warmup_steps", -1),
        ("measured_steps", 0),
    ):
        args = deepcopy(base)
        args[field] = value
        with pytest.raises(ValueError):
            measure_steps(lambda: None, lambda: None, **args)
    for moments in ((1.0, 1.0), (2.0, 1.0), (0.0, float("nan"))):
        values = iter(moments)
        with pytest.raises(ValueError):
            measure_steps(
                lambda: None, lambda: None, **base, clock=lambda: next(values)
            )


def test_execution_rejects_mac_before_importing_cuda_or_creating_output(
    monkeypatch, tmp_path
):
    import training.research_probe as module

    monkeypatch.setattr(module.sys, "platform", "darwin")
    with pytest.raises(ValueError, match="external Linux"):
        module.run_probe(module.probe_protocol("d" * 40), tmp_path / "output")
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("helper", ["inputs", "export", "measure"])
def test_real_private_helpers_also_refuse_mac_before_importing_models_or_engine(
    monkeypatch, helper, tmp_path
):
    import builtins

    import training.research_probe as module

    monkeypatch.setattr(module.sys, "platform", "darwin")
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name == "torch" or name == "voxelshogi":
            raise AssertionError("heavy import occurred before the platform guard")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    with pytest.raises(ValueError, match="external Linux"):
        if helper == "inputs":
            module._inputs({})
        elif helper == "export":
            module._export_and_check(None, {}, [], tmp_path)
        else:
            module._measure_model(None, {}, None, batch_size=1, stopping=lambda: False)
