"""Research run metadata and fake execution ports; no tensors on Mac."""

from dataclasses import asdict

import pytest

from export.research_contract import ResearchConfig, architecture_config


def test_model_dimensions_and_seed_are_bound_to_the_existing_supervised_contract():
    from training.research_fit import ResearchRunConfig, validate_research_binding
    from training.supervision import label_contract

    config = ResearchRunConfig(architecture=architecture_config("geometry"), seed=67001)
    value = config.value()
    assert value["architecture"] == {
        "architecture": "geometry",
        "side": 9,
        "width": 512,
        "layers": 8,
        "heads": 8,
        "ffn": 2048,
        "policy_rank": 64,
    }
    assert value["schema"] == "voxelshogi-research-training-config-v1"
    assert value["seed"] == 67001 and value["selection_split"] == "val"
    assert value["optimizer"] == {
        "name": "AdamW",
        "betas": [0.9, 0.999],
        "eps": 1e-8,
        "foreach": False,
        "fused": False,
    }
    binding = {
        "source_commit": "a" * 40,
        "cache_sha256": "b" * 64,
        "config": value,
        "contract": label_contract(),
        "environment": {"device": "cuda"},
    }
    assert validate_research_binding(binding) is None
    assert ResearchRunConfig.from_value(value) == config
    value["architecture"]["layers"] = 1
    assert config.architecture.layers == 8


@pytest.mark.parametrize(
    "change",
    [
        "extra",
        "schema",
        "dtype",
        "optimizer",
        "dimensions",
        "source",
        "cache",
        "contract",
        "environment",
    ],
)
def test_malformed_or_nonresearch_bindings_are_rejected(change):
    from training.research_fit import ResearchRunConfig, validate_research_binding
    from training.supervision import label_contract

    binding = {
        "source_commit": "a" * 40,
        "cache_sha256": "b" * 64,
        "config": ResearchRunConfig().value(),
        "contract": label_contract(),
        "environment": {"device": "cuda"},
    }
    if change == "extra":
        binding["config"]["unbound"] = 1
    elif change == "schema":
        binding["config"]["schema"] = "voxelshogi-training-run-v1"
    elif change == "dtype":
        binding["config"]["precision"] = "float16"
    elif change == "optimizer":
        binding["config"]["optimizer"]["fused"] = True
    elif change == "dimensions":
        binding["config"]["architecture"]["width"] = 5
    elif change == "source":
        binding["source_commit"] = "main"
    elif change == "cache":
        binding["cache_sha256"] = "b" * 63
    elif change == "contract":
        binding["contract"] = {}
    else:
        binding["environment"] = {"device": "cpu"}
    with pytest.raises(ValueError):
        validate_research_binding(binding)


def test_legacy_m6_binding_cannot_be_decoded_as_research():
    from training.fit import RunConfig
    from training.research_fit import ResearchRunConfig

    with pytest.raises(ValueError):
        ResearchRunConfig.from_value(RunConfig().value())
    with pytest.raises(ValueError):
        ResearchRunConfig(architecture=asdict(architecture_config("full")))
    # Tiny dimensions are useful for Linux numerical CI, never real M admission.
    config = ResearchRunConfig(
        architecture=ResearchConfig(
            "cnn", side=2, width=4, heads=1, ffn=8, layers=1, policy_rank=2
        )
    )
    assert ResearchRunConfig.from_value(config.value()) == config


def test_research_wrapper_builds_the_requested_model_and_delegates_resume(
    monkeypatch, tmp_path
):
    from training import research_fit as module

    config = module.ResearchRunConfig(
        architecture=architecture_config("axial"), seed=17
    )
    model, optimizer, cache = object(), object(), object()
    seen = []
    monkeypatch.setattr(module, "_linux", lambda: None)
    monkeypatch.setattr(
        module,
        "training_objects",
        lambda actual: (seen.append(actual) or model, optimizer),
    )

    def fit(*args, **kwargs):
        seen.append((args, kwargs))
        return {"reason": "stopped"}

    monkeypatch.setattr(module, "fit", fit)

    def stop():
        return True

    result = module.fit_research(
        cache,
        tmp_path / "run",
        config=config,
        source_commit="a" * 40,
        resume=True,
        max_new_steps=3,
        stop_requested=stop,
    )
    assert result == {"reason": "stopped"}
    assert seen[0] is config
    args, kwargs = seen[1]
    assert args == (model, optimizer, cache, tmp_path / "run")
    assert kwargs == {
        "config": config,
        "source_commit": "a" * 40,
        "resume": True,
        "max_new_steps": 3,
        "stop_requested": stop,
    }


def test_real_entrypoint_refuses_mac_before_importing_torch(monkeypatch, tmp_path):
    from training import research_fit as module

    monkeypatch.setattr(module.sys, "platform", "darwin")

    def forbidden(*args, **kwargs):
        pytest.fail("Mac must be refused before constructing models")

    monkeypatch.setattr(module, "training_objects", forbidden)
    with pytest.raises(ValueError, match="Linux"):
        module.fit_research(
            object(),
            tmp_path,
            config=module.ResearchRunConfig(),
            source_commit="a" * 40,
        )
