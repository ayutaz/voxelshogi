"""Linux replay/Parquet integration with a fake neural chooser, not inference."""

import json
import time
from collections import Counter

import pytest


def test_real_rust_histories_parquet_and_json_traces_join_into_reference_sources(
    tmp_path, monkeypatch
):
    import pyarrow as pa
    import pyarrow.parquet as pq
    from voxelshogi import Game

    from infrastructure.research.pilot.validation import _query
    from training import evaluation_v2_runner as runner
    from training.evaluation_v2 import fingerprint
    from training.feature_cache import file_hash
    from training.research_development_references import collect_references
    from training.tests.test_evaluation_v2_native import native_protocol

    root = tmp_path / "references"
    root.mkdir()
    artifact = tmp_path / "opaque.bin"
    artifact.write_bytes(b"Fake neural chooser; no model is loaded")
    spec = native_protocol()
    spec["participants"]["model"] = {
        "policy": "puct32-v1",
        "backend": "torch-cpu",
        "artifact_sha256": file_hash(artifact),
    }

    def prepare(protocol, artifacts, *, observe_input, **unused):
        assert artifacts == {"model": artifact}

        def choose(game):
            # Explicitly simulate one played-path query and one legal branch.
            # The collector must replay both, without invoking a neural model.
            observe_input("model", game)
            branch = Game.from_record(game.record())
            branch.play(branch.legal_actions()[max(branch.legal_actions())])
            if not branch.snapshot()["finished"]:
                observe_input("model", branch)
            return min(game.legal_actions())

        return {"model": choose, "opponent": None}

    monkeypatch.setattr(runner, "_prepare_players", prepare)
    captured = {}
    for name in ("screen-run", "full", "geometry"):
        captured[name] = []

        def observe(role, game, name=name):
            captured[name].append(_query(role, game))

        runner.run_protocol(
            spec, {"model": artifact}, root / name, observe_input=observe
        )

    def write(name, body):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        return descriptor(name)

    def descriptor(name):
        path = root / name
        return {"path": name, "bytes": path.stat().st_size, "sha256": file_hash(path)}

    write("screen/config.json", json.dumps({"protocols": {"arm": spec}}).encode())
    write("screen/manifest.json", b'{"scope":"fake-model native replay fixture"}')
    matches = []
    for case in spec["cases"]:
        for side in ("b", "w"):
            row = json.loads(
                (root / "screen-run" / f"{case['id']}-{side}.json").read_bytes()
            )
            matches.append(
                {
                    "arm": "arm",
                    "case_id": case["id"],
                    "protocol_sha256": fingerprint(spec),
                    "match_json": json.dumps(row),
                }
            )
    pq.write_table(pa.Table.from_pylist(matches), root / "screen/matches.parquet")
    queries = []
    for index, row in enumerate(captured["screen-run"], 1):
        game = Game.from_record(row["record"])
        case = next(
            c
            for c in spec["cases"]
            if c["opening"]["initial"] == row["record"]["initial"]
        )
        queries.append(
            {
                "arm": "arm",
                "case_id": case["id"],
                "protocol_sha256": fingerprint(spec),
                "role": row["role"],
                "query_index": index,
                "record_json": json.dumps(row["record"]),
                "vsfen": game.snapshot()["vsfen"],
                "side": game.snapshot()["side"],
                "physical_id": row["physical_id"],
                "input_id": row["input_id"],
            }
        )
    pq.write_table(pa.Table.from_pylist(queries), root / "screen/queries.parquet")
    traces = [
        {"architecture": name, **row}
        for name in ("full", "geometry")
        for row in captured[name]
    ]
    trace = write(
        "pilot/queries.jsonl",
        b"".join((json.dumps(row) + "\n").encode() for row in traces),
    )
    plan = {
        "schema": "voxelshogi-development-reference-plan-v1",
        "screens": [
            {
                "id": "screen",
                "files": {
                    n: descriptor("screen/" + n)
                    for n in (
                        "config.json",
                        "manifest.json",
                        "matches.parquet",
                        "queries.parquet",
                    )
                },
                "games": 4,
                "queries": len(queries),
            }
        ],
        "runs": [
            {
                "id": n,
                "run": descriptor(n + "/run.json"),
                "games": 4,
                "query_coverage": "trace",
            }
            for n in ("full", "geometry")
        ],
        "traces": [
            {
                "file": trace,
                "cohort_field": "architecture",
                "cohorts": {n: n for n in ("full", "geometry")},
                "queries": dict(Counter(row["architecture"] for row in traces)),
            }
        ],
    }
    result = collect_references(root, plan, deadline=time.time() + 60)
    assert result["receipt"]["verified"] is True
    assert sum(s["games"] for s in result["receipt"]["sources"].values()) == 12
    assert sum(s["queries"] for s in result["receipt"]["sources"].values()) == len(
        queries
    ) + len(traces)
    for name in ("screen", "full", "geometry"):
        actual = captured["screen-run" if name == "screen" else name]
        assert {r["input_id"] for r in actual} <= result["model_input"][
            "development/" + name
        ]


def test_real_terminal_positions_cannot_be_certified_as_neural_queries():
    from pathlib import Path

    from voxelshogi import Game

    from training.research_development_references import load_ports

    fixtures = json.loads(
        (
            Path(__file__).resolve().parents[2] / "export/fixtures/positions.json"
        ).read_bytes()
    )
    game = Game.from_record(fixtures[2]["record"])
    game.play("232222")
    assert game.snapshot()["finished"] is True
    with pytest.raises(ValueError, match="unfinished"):
        load_ports()["query"](game.record())
