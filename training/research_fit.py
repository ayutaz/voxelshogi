"""Model-bound P6 supervised runs using the deterministic, resumable fitter.

Metadata and fake execution ports are safe on Mac. Real construction, fitting
and resume execution require external Linux. Dataset exclusion/holdout admission
and a measured whole-job budget must be established by the execution driver.
"""

import re
import sys
from dataclasses import asdict, dataclass, field

from export.research_contract import ResearchConfig, architecture_config
from training.fit import RunConfig, fit
from training.supervision import label_contract

SCHEMA = "voxelshogi-research-training-config-v1"


def _linux():
    if sys.platform != "linux":
        raise ValueError("research training requires external Linux")


@dataclass(frozen=True)
class ResearchRunConfig(RunConfig):
    architecture: ResearchConfig = field(
        default_factory=lambda: architecture_config("full")
    )

    def __post_init__(self):
        super().__post_init__()
        if type(self.architecture) is not ResearchConfig:
            raise ValueError(
                "research training requires explicit architecture dimensions"
            )

    def value(self):
        return {
            **super().value(),
            "schema": SCHEMA,
            "architecture": asdict(self.architecture),
        }

    @classmethod
    def from_value(cls, value):
        try:
            if type(value) is not dict or type(value["architecture"]) is not dict:
                raise ValueError("invalid research training config")
            config = cls(
                **{key: value[key] for key in RunConfig.__dataclass_fields__},
                architecture=ResearchConfig(**value["architecture"]),
            )
            if config.value() != value:
                raise ValueError("research training config differs")
            return config
        except (KeyError, TypeError) as error:
            raise ValueError("research training config differs") from error


def validate_research_binding(binding):
    if (
        type(binding) is not dict
        or set(binding)
        != {"source_commit", "cache_sha256", "config", "contract", "environment"}
        or not isinstance(binding["source_commit"], str)
        or re.fullmatch(r"[0-9a-f]{40}", binding["source_commit"]) is None
        or not isinstance(binding["cache_sha256"], str)
        or re.fullmatch(r"[0-9a-f]{64}", binding["cache_sha256"]) is None
        or binding["contract"] != label_contract()
        or type(binding["environment"]) is not dict
    ):
        raise ValueError("research resume source/input/label binding differs")
    config = ResearchRunConfig.from_value(binding["config"])
    if binding["environment"].get("device") != config.device:
        raise ValueError("research resume environment device differs")


def training_objects(config):
    _linux()
    import torch

    from export.research_model import make_research_model
    from training.checkpoint import seed_all

    if type(config) is not ResearchRunConfig:
        raise ValueError("research run config required")
    seed_all(config.seed)
    torch.set_num_threads(config.threads)
    model = make_research_model(config.architecture, seed=config.seed).to(config.device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
        betas=(0.9, 0.999),
        eps=1e-8,
        foreach=False,
        fused=False,
    )
    return model, optimizer


def fit_research(
    cache,
    folder,
    *,
    config,
    source_commit,
    resume=False,
    max_new_steps=None,
    stop_requested=lambda: False,
):
    """Fit a verified admitted cache; dimensions and all run settings enter binding.

    max_new_steps bounds this attempt only. Epochs/batches define the frozen
    schedule; it must not be described as an equal-total-FLOPs comparison.
    """
    _linux()
    if type(config) is not ResearchRunConfig:
        raise ValueError("research run config required")
    model, optimizer = training_objects(config)
    return fit(
        model,
        optimizer,
        cache,
        folder,
        config=config,
        source_commit=source_commit,
        resume=resume,
        max_new_steps=max_new_steps,
        stop_requested=stop_requested,
    )
