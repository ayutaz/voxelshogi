"""Holdout-history and protected-ID assembly without search or tensor work."""

from copy import deepcopy

import pytest

from training.research_data import pilot_protocol
from training.supervision import RULESET


class HistoryPort:
    def __init__(self):
        self.moves = []

    def record(self):
        return {
            "ruleset_id": RULESET,
            "initial": "fixture",
            "moves": self.moves[:],
            "result": None,
            "termination": None,
        }

    def snapshot(self):
        return {
            "ruleset_id": RULESET,
            "board": [len(self.moves)] + [0] * 728,
            "hands": [0] * 14,
            "side": "b",
            "finished": False,
        }

    def play(self, move):
        if move != ("a", "b")[len(self.moves)]:
            raise ValueError("illegal fixture move")
        self.moves.append(move)


def entry():
    p = pilot_protocol("a" * 40)
    p.update(max_plies=2, opening_plies=0, sample_plies=[1])
    p["games"] = p["games"][:1]
    p["games"][0]["split"] = "val"
    game = HistoryPort()
    game.play("a")
    game.play("b")
    record = game.record()
    record.update(termination="MaxPlies", result={"Draw": {"reason": "MaxPlies"}})
    return p, {"game": p["games"][0], "record": record, "termination_kind": "cutoff"}


def test_all_holdout_history_inputs_are_protected_without_reading_teachers():
    from training.selfplay_protection import history_inputs

    p, saved = entry()
    ids = history_inputs(p, p["games"][0], saved, HistoryPort)
    # There is one sampled ply, but opening/root, unsampled and final states
    # must all be protected. No teacher data or search port is supplied.
    assert len(ids) == 3
    bad = deepcopy(saved)
    bad["record"]["moves"][1] = "illegal"
    with pytest.raises(ValueError, match="illegal"):
        history_inputs(p, p["games"][0], bad, HistoryPort)
    bad = deepcopy(saved)
    bad["record"]["initial"] = "another position"
    with pytest.raises(ValueError):
        history_inputs(p, p["games"][0], bad, HistoryPort)
    bad = deepcopy(saved)
    bad["record"]["result"] = None
    with pytest.raises(ValueError):
        history_inputs(p, p["games"][0], bad, HistoryPort)


def test_sorted_union_is_nonempty_and_records_each_input_source():
    from training.selfplay_protection import assemble_protection

    provenance = {
        "m6_dataset_revision": "6e7fb29d2469b56a895042fbb089d86e7b4d074f",
        "p5_evaluation_proof_sha256": "d" * 64,
        "p51_dataset_revision": "1b86f7e83b70a69cdfa3cc0bd4e9b0886623c472",
    }
    sources = {
        "m4_m6": {"b" * 64, "a" * 64},
        "p5_evaluation": {"b" * 64},
        "p51_holdout": {"c" * 64},
    }
    document, audit = assemble_protection(sources, provenance)
    assert document == {
        "schema": "voxelshogi-protected-inputs-v1",
        "provenance": provenance,
        "ids": [c * 64 for c in "abc"],
    }
    assert audit["counts"] == {"m4_m6": 2, "p5_evaluation": 1, "p51_holdout": 1}
    assert audit["unique_inputs"] == 3
    for bad in (
        {},
        {**sources, "p51_holdout": set()},
        {**sources, "p51_holdout": {"bad"}},
    ):
        with pytest.raises(ValueError):
            assemble_protection(bad, provenance)
    with pytest.raises(ValueError):
        assemble_protection(sources, {**provenance, "p51_dataset_revision": "e" * 40})


def test_build_refuses_mac_before_opening_inputs(monkeypatch, tmp_path):
    from training import selfplay_protection

    monkeypatch.setattr(selfplay_protection.sys, "platform", "darwin")
    with pytest.raises(ValueError, match="Linux"):
        selfplay_protection.build_protection(
            tmp_path, tmp_path, tmp_path, tmp_path, tmp_path
        )


def test_unverified_hf_transfer_is_not_input_provenance(tmp_path):
    from training.selfplay_protection import _p51_release

    with pytest.raises(ValueError, match="verified"):
        _p51_release(tmp_path, None, None)
    plan = {"repo_id": "voxelshogi/voxelshogi-search-v1", "repo_type": "dataset"}
    receipt = {
        "repo_id": plan["repo_id"],
        "repo_type": "dataset",
        "hub_commit": "1b86f7e83b70a69cdfa3cc0bd4e9b0886623c472",
        "verified": False,
        "dry_run": False,
        "community_disabled": True,
    }
    with pytest.raises(ValueError, match="verified"):
        _p51_release(tmp_path, plan, receipt)
