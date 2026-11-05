"""Frozen root admission uses actual Rust replay on Linux, without neural calls."""

import copy
import json

import pytest


@pytest.fixture(scope="module")
def bundle():
    from training.research_screen import prepare_screen
    from training.tests.test_research_screen_native import participants

    source, players = participants()
    return prepare_screen(players, source)


def write(path, value):
    from training.evaluation_v2 import fingerprint
    from training.feature_cache import file_hash

    value = copy.deepcopy(value)
    value["conditions_sha256"] = fingerprint(
        {k: v for k, v in value.items() if k != "conditions_sha256"}
    )
    path.write_text(json.dumps(value))
    return file_hash(path)


def test_all_24_frozen_roots_are_replayed_and_final12_are_kept_separate(
    tmp_path, bundle
):
    from training.research_corpus import _screen_protection

    path = tmp_path / "screen.json"
    digest = write(path, bundle)
    roots = _screen_protection(path, digest)
    assert len(roots["holdout"]) == len(roots["development"]) == 12
    assert not roots["holdout"] & roots["development"]
    assert sorted(roots["holdout"]) == bundle["protected_holdout_inputs"]
    with pytest.raises(ValueError, match="hash"):
        _screen_protection(path, "0" * 64)


@pytest.mark.parametrize("change", ["input", "purpose", "protected-list"])
def test_rehashing_a_corrupt_root_manifest_does_not_replace_rust_evidence(
    tmp_path, bundle, change
):
    from training.research_corpus import _screen_protection

    value = copy.deepcopy(bundle)
    key = value["holdout_protocol"]["cases"][0]["id"]
    if change == "input":
        value["roots"][key]["input"] = "0" * 64
    elif change == "purpose":
        value["roots"][key]["purpose"] = "development"
    else:
        value["protected_holdout_inputs"].pop()
    path = tmp_path / "changed.json"
    digest = write(path, value)
    with pytest.raises(ValueError):
        _screen_protection(path, digest)
