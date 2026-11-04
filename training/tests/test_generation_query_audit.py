"""Hand-authored input IDs prove off-trajectory neural queries are audited."""

import pytest

from training.generation_evaluation import audit_evaluation_inputs


def test_observed_query_is_audited_even_when_the_played_path_has_no_overlap():
    from training.generation_audit import include_observed_inputs

    played = {"played": {"positions": {"a" * 64}, "inputs": {"b" * 64}}}
    queries = {"query/model": {"positions": {"c" * 64}, "inputs": {"d" * 64}}}
    physical, canonical = {"train": {"e" * 64}}, {"protected": {"d" * 64}}
    assert audit_evaluation_inputs(physical, canonical, played)["passed"] is True
    combined = include_observed_inputs(played, queries)
    result = audit_evaluation_inputs(physical, canonical, combined)
    assert result["passed"] is False
    assert result["overlaps_by_source"] == {
        "physical": {"train": 0},
        "model_input": {"protected": 1},
    }
    assert result["cases_with_overlap"] == ["query/model"]
    assert result["evaluation_counts"] == {"positions": 2, "inputs": 2}
    assert set(played) == {"played"} and set(queries) == {"query/model"}
    assert include_observed_inputs(played, None) == played


@pytest.mark.parametrize(
    "invalid",
    [
        {},
        {"played": {"positions": {"c" * 64}, "inputs": {"d" * 64}}},
        {"query": {"positions": set(), "inputs": {"d" * 64}}},
        {"query": {"positions": {"c" * 64}, "inputs": {"not-a-sha256"}}},
        {"query": {"positions": {"c" * 64}}},
    ],
)
def test_query_inventory_cannot_be_empty_malformed_or_replace_a_played_case(invalid):
    from training.generation_audit import include_observed_inputs

    played = {"played": {"positions": {"a" * 64}, "inputs": {"b" * 64}}}
    with pytest.raises(ValueError):
        include_observed_inputs(played, invalid)


def test_full_auditor_includes_observed_queries_through_small_metadata_ports(
    tmp_path, monkeypatch
):
    import json
    import sys
    from types import SimpleNamespace

    from training import generation_audit as module
    from training import selfplay_dataset, selfplay_generations, supervision

    rows = [
        {
            "vsfen": "fixture-" + split + " b - 1",
            "split": split,
            "ruleset_id": "voxelshogi-standard-v1",
        }
        for split in ("train", "val", "test")
    ]
    table = SimpleNamespace(to_pylist=lambda: rows)
    parquet = SimpleNamespace(read_table=lambda *a, **kw: table)
    monkeypatch.setitem(sys.modules, "pyarrow", SimpleNamespace(parquet=parquet))
    monkeypatch.setitem(sys.modules, "pyarrow.parquet", parquet)
    snapshot = {
        "ruleset_id": "voxelshogi-standard-v1",
        "board": [0] * 729,
        "hands": [0] * 14,
        "side": "b",
    }

    def factory(vsfen):
        return SimpleNamespace(snapshot=lambda: snapshot)

    monkeypatch.setitem(sys.modules, "voxelshogi", SimpleNamespace(Game=factory))
    monkeypatch.setattr(module.sys, "platform", "linux")
    monkeypatch.setattr(
        supervision,
        "audit_corpus",
        lambda *a: {"counts": {"rows": 3}, "contract": {}, "files": []},
    )
    monkeypatch.setattr(selfplay_generations, "_protection", lambda *a: {"d" * 64})
    monkeypatch.setattr(
        selfplay_dataset,
        "_load",
        lambda *a: (
            {"run": {"complete": True, "generations": [0]}},
            [{"samples": [{"position": "fixture-selfplay b - 1"}]}],
        ),
    )
    monkeypatch.setattr(module, "verify_run", lambda *a: None)
    monkeypatch.setattr(
        module,
        "replay_scored_identities",
        lambda *a: {"positions": {"a" * 64}, "inputs": {"b" * 64}},
    )
    corpus, selfplay, run = (tmp_path / name for name in ("corpus", "selfplay", "run"))
    for folder in (corpus, selfplay, run):
        folder.mkdir()
    (corpus / "manifest.json").write_text(
        json.dumps({"shards": [{"file": "opaque.parquet"}]})
    )
    (selfplay / "manifest.json").write_text("{}")
    protection = tmp_path / "protection.json"
    protection.write_text("{}")
    (run / "protocol.json").write_text(
        json.dumps({"cases": [{"id": "fixture", "opening": {}}]})
    )
    (run / "run.json").write_text(
        json.dumps(
            {
                "files": [{"path": "fixture.json"}],
                "games": 1,
                "protocol_sha256": "f" * 64,
            }
        )
    )
    (run / "fixture.json").write_text(json.dumps({"case_id": "fixture", "record": {}}))
    query = {"query/model": {"positions": {"c" * 64}, "inputs": {"d" * 64}}}
    result = module.audit_generation_runs(
        {"fixture": run},
        corpus,
        selfplay,
        expected_protocol={},
        protection=protection,
        observed_inputs=query,
    )
    assert (
        result["passed"] is False
        and result["overlaps_by_source"]["model_input"]["protected"] == 1
    )
    assert result["cases_with_overlap"] == ["query/model"]
    assert result["observed_input_counts"] == {
        "query/model": {"positions": 1, "inputs": 1}
    }
    assert (
        result["runs"]["fixture"]["games"] == 1 and result["corpus_counts"]["rows"] == 3
    )
