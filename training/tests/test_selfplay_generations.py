"""Frozen metadata and seed families; no game or model execution."""

from dataclasses import asdict

import pytest


def protocol():
    from training.selfplay_generations import make_protocol

    return make_protocol(
        "1" * 40,
        base_model_sha256="a" * 64,
        protection_sha256="b" * 64,
        protection_count=113321,
        protection_provenance={
            "m6_dataset_revision": "6e7fb29d2469b56a895042fbb089d86e7b4d074f",
            "p5_evaluation_proof_sha256": "c" * 64,
            "p51_dataset_revision": "2" * 40,
        },
    )


def test_three_generations_have_fixed_training_only_families_and_bounded_search():
    from training.selfplay_generations import validate_protocol

    p = protocol()
    assert len(validate_protocol(p)) == 64
    assert p["generations"] == 3 and p["episodes_per_generation"] == 16
    assert p["replay_capacity"] == 32 and p["opening_plies"] == 16
    assert p["actor"]["max_plies"] == 256 and p["actor"]["search"]["simulations"] == 32
    assert [f["seed"] for f in p["families"]] == list(range(10000, 10016))
    assert all(f["split"] == "train" for f in p["families"])
    for mutate in (
        lambda x: x.update(generations=True),
        lambda x: x["families"][0].update(split="test"),
        lambda x: x["families"][1].update(seed=10000),
        lambda x: x.update(base_model_sha256="latest"),
        lambda x: x["actor"]["search"].update(simulations=0),
        lambda x: x.update(protection_count=0),
    ):
        bad = protocol()
        mutate(bad)
        with pytest.raises(ValueError):
            validate_protocol(bad)


def test_family_opening_is_shared_across_generations_but_actor_seed_is_distinct():
    from training.selfplay_generations import episode_settings

    p = protocol()
    first, seed = episode_settings(p, 0, 2)
    next_generation, next_seed = episode_settings(p, 1, 2)
    assert seed == next_seed == 10002
    assert first.seed != next_generation.seed
    assert asdict(first) == asdict(episode_settings(p, 0, 2)[0])
    assert p["actor"]["seed"] == 314159  # Config copies must not mutate the protocol.


def test_generation_execution_is_linux_only(monkeypatch, tmp_path):
    from training import selfplay_generations as generations

    monkeypatch.setattr(generations.sys, "platform", "darwin")
    with pytest.raises(ValueError, match="Linux"):
        generations.run_generations({}, tmp_path, tmp_path, tmp_path)


def test_publication_acknowledges_only_a_pair_of_verified_namespace_receipts():
    from training.selfplay_generations import validate_publication

    pair = {
        key: {
            "verified": True,
            "dry_run": False,
            "community_disabled": True,
            "repo_type": kind,
            "repo_id": "voxelshogi/fixture-" + key,
            "hub_commit": "1" * 40,
            "release_sha256": "2" * 64,
        }
        for key, kind in (("dataset", "dataset"), ("state", "model"))
    }
    validate_publication(pair)
    pair["state"]["verified"] = False
    with pytest.raises(ValueError):
        validate_publication(pair)


def test_failed_publication_is_retried_without_advancing_its_cursor(tmp_path):
    import json

    from training.selfplay_generations import _publish_pending

    m = {"generations": [{"generation": 0}], "publications": []}
    path = tmp_path / "run.json"
    path.write_text(json.dumps(m))

    def failed(record, folder):
        raise OSError("interrupted publication")

    with pytest.raises(OSError):
        _publish_pending(m, path, failed, tmp_path)
    assert m["publications"] == []
    assert json.loads(path.read_text())["generations"] == [{"generation": 0}]


def test_protected_inputs_require_exact_hash_unique_ids_and_declared_provenance(
    tmp_path,
):
    import hashlib
    import json

    from training.selfplay_generations import _protection

    p = protocol()
    p["protection_count"] = 2
    record = {
        "schema": "voxelshogi-protected-inputs-v1",
        "provenance": p["protection_provenance"],
        "ids": ["a" * 64, "b" * 64],
    }
    path = tmp_path / "protected.json"

    def write(value):
        path.write_text(json.dumps(value))
        p["protection_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()

    write(record)
    assert _protection(path, p) == {"a" * 64, "b" * 64}
    path.write_text(path.read_text() + "\n")
    with pytest.raises(ValueError, match="hash"):
        _protection(path, p)
    for ids in (["a" * 64, "a" * 64], ["b" * 64, "a" * 64], ["short", "b" * 64], []):
        write({**record, "ids": ids})
        with pytest.raises(ValueError):
            _protection(path, p)
    write(
        {
            **record,
            "provenance": {**record["provenance"], "p51_dataset_revision": "3" * 40},
        }
    )
    with pytest.raises(ValueError):
        _protection(path, p)
