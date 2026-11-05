"""Handwritten research weight metadata and fake evaluation routing, no Torch."""

import json
import struct
from copy import deepcopy

import pytest

from training.feature_cache import file_hash


def metadata(name="full"):
    return {
        "schema": "voxelshogi-research-weights-v1",
        "architecture": {
            "architecture": name,
            "side": 9,
            "width": 256 if name == "cnn" else 512,
            "layers": 8,
            "heads": 8,
            "ffn": 2048,
            "policy_rank": 64,
        },
        "seed": 69001,
        "source_commit": "a" * 40,
        "training_binding_sha256": "b" * 64,
        "checkpoint_role": "best",
        "step": 128,
    }


def header(path, value):
    raw = json.dumps(
        {"__metadata__": {"voxelshogi.research": json.dumps(value)}}
    ).encode()
    path.write_bytes(
        struct.pack("<Q", len(raw)) + raw + b"opaque unit bytes; not model tensors"
    )
    return path


def test_all_four_fixed_M_profiles_and_legacy_header_are_distinguished(tmp_path):
    from training.research_weights import research_metadata, validate_metadata

    for name in ("full", "axial", "geometry", "cnn"):
        value = metadata(name)
        assert validate_metadata(value) == value
        path = header(tmp_path / f"{name}.safetensors", value)
        assert research_metadata(path) == value
    legacy = tmp_path / "legacy.safetensors"
    raw = b'{"__metadata__":{"format":"pt"}}'
    legacy.write_bytes(struct.pack("<Q", len(raw)) + raw)
    assert research_metadata(legacy) is None
    legacy.write_bytes(b"opaque existing fake-port weights")
    assert research_metadata(legacy) is None


def test_metadata_rejects_unknown_schema_toy_profiles_and_unbound_provenance(tmp_path):
    from training.research_weights import research_metadata, validate_metadata

    changes = [
        lambda v: v.update(schema="voxelshogi-research-weights-v0"),
        lambda v: v["architecture"].update(side=2),
        lambda v: v["architecture"].update(width=8),
        lambda v: v["architecture"].update(layers=1),
        lambda v: v.update(seed=True),
        lambda v: v.update(seed=-1),
        lambda v: v.update(source_commit="main"),
        lambda v: v.update(training_binding_sha256="b" * 63),
        lambda v: v.update(checkpoint_role="unselected"),
        lambda v: v.update(step=True),
        lambda v: v.update(step=0),
        lambda v: v.update(extra="unknown"),
    ]
    for change in changes:
        value = deepcopy(metadata())
        change(value)
        with pytest.raises(ValueError):
            validate_metadata(value)
        with pytest.raises(ValueError):
            research_metadata(header(tmp_path / "bad.safetensors", value))
    path = header(tmp_path / "invalid-json.safetensors", "not an object")
    with pytest.raises(ValueError):
        research_metadata(path)


def test_real_model_entrypoints_refuse_Mac_before_numerical_ports(
    monkeypatch, tmp_path
):
    import training.research_weights as module

    monkeypatch.setattr(module.sys, "platform", "darwin")
    # A broken guard must fail before importing any numerical backend.
    monkeypatch.setitem(module.sys.modules, "torch", None)
    with pytest.raises(ValueError, match="external Linux"):
        module.write_research_weights({}, tmp_path / "unused", metadata=metadata())
    with pytest.raises(ValueError, match="external Linux"):
        module.load_research_player(
            tmp_path / "unused",
            expected_sha256="c" * 64,
            device="cpu",
            policy="legal-argmax-v1",
        )


@pytest.mark.parametrize("policy", ["legal-argmax-v1", "puct32-v1"])
def test_existing_cohort_runner_routes_bound_M_weights_without_S_constructor(
    monkeypatch, tmp_path, policy
):
    import training.research_weights as module
    from training.evaluation_v2_runner import _prepare_players, rust_policy_identity
    from training.tests.test_evaluation_v2 import protocol

    path = header(tmp_path / "research.safetensors", metadata())
    spec = protocol()
    spec["participants"]["model"] = {
        "policy": policy,
        "backend": "torch-cpu",
        "artifact_sha256": file_hash(path),
    }
    spec["participants"]["opponent"] = {
        "policy": "alphabeta-v1",
        "backend": "rust",
        "artifact_sha256": rust_policy_identity(
            "alphabeta-v1", spec["source_commit"], spec["search_limits"]
        ),
    }
    observed, called = [], []

    def stop():
        return False

    player = object()

    def load(p, **kw):
        called.append((p, kw))
        kw["observe_input"]("opaque fake game")
        return player

    monkeypatch.setattr(module, "load_research_player", load)
    result = _prepare_players(
        spec,
        {"model": path},
        stop_requested=stop,
        observe_input=lambda role, game: observed.append((role, game)),
    )
    assert result == {"model": player, "opponent": None}
    assert len(called) == 1 and called[0][0] == path
    kw = called[0][1]
    assert (
        kw["expected_sha256"] == file_hash(path)
        and kw["device"] == "cpu"
        and kw["policy"] == policy
    )
    assert kw["stop_requested"] is stop
    assert observed == [("model", "opaque fake game")]
    path.write_bytes(path.read_bytes() + b"changed after protocol freeze")
    with pytest.raises(ValueError, match="hash"):
        _prepare_players(spec, {"model": path})
    assert len(called) == 1
