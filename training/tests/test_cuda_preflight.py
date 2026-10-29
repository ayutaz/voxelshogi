"""Pure quoted-runtime metadata validation; no CUDA import or computation."""

import pytest


def facts():
    return {
        "system": "Linux",
        "machine": "x86_64",
        "python": "3.14.9",
        "torch": "2.14.1+cu130",
        "cuda": "13.0",
        "cuda_available": True,
        "gpu_count": 1,
        "gpu": "NVIDIA GeForce RTX 5090",
        "capability": [12, 0],
        "compiled_arches": ["sm_80", "sm_89", "sm_120"],
        "driver": "580.159.03",
        "vram_mib": 32607,
    }


def test_only_the_pinned_linux_cuda_5090_runtime_is_accepted():
    from training.cuda_preflight import validate_facts

    assert validate_facts(facts()) == facts()


@pytest.mark.parametrize(
    "change",
    [
        {"system": "Darwin"},
        {"machine": "arm64"},
        {"python": "3.13.11"},
        {"torch": "2.14.1+cpu"},
        {"torch": "2.15.0+cu130"},
        {"cuda": None},
        {"cuda": "12.8"},
        {"cuda_available": False},
        {"gpu_count": 2},
        {"gpu": "Tesla V100"},
        {"capability": [8, 9]},
        {"compiled_arches": ["sm_89"]},
        {"driver": "570.195.03"},
        {"driver": "unknown"},
        {"vram_mib": 24000},
    ],
)
def test_unquoted_unsupported_or_insufficient_gpu_facts_fail_closed(change):
    from training.cuda_preflight import validate_facts

    with pytest.raises(ValueError):
        validate_facts({**facts(), **change})
