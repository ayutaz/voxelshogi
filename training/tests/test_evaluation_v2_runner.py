"""Small fake ports exercise orchestration only, never simulate shogi rules."""

from copy import deepcopy

import pytest

from training.tests.test_evaluation_v2 import protocol


class FakeGame:
    def __init__(self, record, mate_after=None):
        self.value = deepcopy(record)
        self.mate_after = mate_after
        self.played = 0

    def record(self):
        return deepcopy(self.value)

    def snapshot(self):
        return {
            "finished": self.value["result"] is not None,
            "side": "b" if self.played % 2 == 0 else "w",
            "result": deepcopy(self.value["result"]),
        }

    def legal_actions(self):
        return {7: "legal-seven", 9: "legal-nine"}

    def play(self, move):
        assert move in self.legal_actions().values()
        self.value["moves"].append(move)
        self.played += 1
        if self.played == self.mate_after:
            self.value["result"] = {"Win": {"winner": "Black", "reason": "Checkmate"}}


def play(case, game, **kwargs):
    from training.evaluation_v2_runner import _play_case

    times = iter([10.0, 13.0])
    return _play_case(
        case,
        game,
        model_side="b",
        choose_model=lambda g: 7,
        choose_opponent=lambda g: 9,
        clock=lambda: next(times),
        **kwargs,
    )


def test_additional_limit_excludes_opening_and_preserves_prefix_and_color_routing():
    case = protocol()["cases"][0]
    result = play(case, FakeGame(case["opening"]))
    assert result["record"]["moves"] == ["opaque-prefix", "legal-seven", "legal-nine"]
    assert result["record"]["termination"] == "MaxPlies"
    assert result["record"]["result"] == {"Draw": {"reason": "MaxPlies"}}
    assert result["outcome"] == "cutoff" and result["elapsed_seconds"] == 3.0
    assert case["opening"]["moves"] == ["opaque-prefix"]


def test_natural_last_ply_mate_precedes_cutoff_and_cannot_be_relabelled_draw():
    case = protocol()["cases"][0]
    result = play(case, FakeGame(case["opening"], mate_after=2))
    assert result["outcome"] == "win"
    assert result["record"]["termination"] is None
    assert result["record"]["result"] == {
        "Win": {"winner": "Black", "reason": "Checkmate"}
    }


def test_interruption_illegal_actions_and_no_actions_do_not_emit_completed_result():
    from training.evaluation_v2_runner import _play_case

    case = protocol()["cases"][0]
    with pytest.raises(InterruptedError):
        play(case, FakeGame(case["opening"]), stop_requested=lambda: True)
    game = FakeGame(case["opening"])
    with pytest.raises(ValueError):
        _play_case(
            case,
            game,
            model_side="b",
            choose_model=lambda g: 999,
            choose_opponent=lambda g: 9,
        )
    game.legal_actions = lambda: {}
    with pytest.raises(ValueError):
        play(case, game)


def test_position_identity_excludes_ply_but_retains_rules_side_and_hands():
    from training.evaluation_v2_runner import position_identity

    original = position_identity("opaque-board b 2P 1")
    assert original == position_identity("opaque-board b 2P 900")
    for value in ("other-board b 2P 1", "opaque-board w 2P 1", "opaque-board b P 1"):
        assert position_identity(value) != original
    with pytest.raises(ValueError):
        position_identity("opaque-board b 2P 1", ruleset="nine-kings")
    for value in ("broken", "board x - 1", "board b - 0", "board b - nan"):
        with pytest.raises(ValueError):
            position_identity(value)


def test_native_execution_is_rejected_on_mac_before_importing_engine(monkeypatch):
    from training.evaluation_v2_runner import run_protocol

    monkeypatch.setattr("training.evaluation_v2_runner.sys.platform", "darwin")
    with pytest.raises(ValueError, match="Linux"):
        run_protocol(protocol(), {}, "unused-output")


def test_native_policy_identity_binds_source_search_limits_and_random_seed_rule():
    from training.evaluation_v2_runner import rust_policy_identity

    limits = protocol()["search_limits"]
    original = rust_policy_identity("alphabeta-v1", "a" * 40, limits)
    assert original != rust_policy_identity("alphabeta-v1", "b" * 40, limits)
    assert original != rust_policy_identity(
        "alphabeta-v1", "a" * 40, {**limits, "max_nodes": 1}
    )
    assert original != rust_policy_identity("random-canonical-v1", "a" * 40, limits)
    with pytest.raises(ValueError):
        rust_policy_identity("unknown", "a" * 40, limits)


def test_random_policy_identifies_python_rng_separately_from_rust_search():
    from training.evaluation_v2 import validate_protocol

    spec = protocol()
    spec["participants"]["opponent"].update(
        policy="random-canonical-v1", backend="python-rng"
    )
    assert len(validate_protocol(spec)) == 64
    spec["participants"]["opponent"]["backend"] = "rust"
    with pytest.raises(ValueError):
        validate_protocol(spec)


def partial_run(tmp_path):
    import json

    from training.evaluation_v2 import fingerprint
    from training.feature_cache import file_hash
    from training.tests.test_evaluation_v2 import rows

    spec = protocol()
    folder = tmp_path / "run"
    folder.mkdir()
    (folder / "protocol.json").write_text(json.dumps(spec))
    row = rows(spec)[0]
    name = "tactic-b.json"
    path = folder / name
    path.write_text(json.dumps(row))
    receipt = {
        "complete": False,
        "protocol_sha256": fingerprint(spec),
        "games": 1,
        "runtime": {"source_commit": spec["source_commit"]},
        "files": [
            {"path": name, "bytes": path.stat().st_size, "sha256": file_hash(path)}
        ],
    }
    (folder / "run.json").write_text(json.dumps(receipt))
    return spec, folder, row, receipt


def test_partial_resume_checks_bound_hashes_and_every_saved_row_before_reuse(tmp_path):
    from training.evaluation_v2_runner import read_partial_run

    spec, folder, row, receipt = partial_run(tmp_path)
    assert read_partial_run(folder, spec) == ([row], receipt)
    path = folder / "tactic-b.json"
    path.write_text(path.read_text() + " ")
    with pytest.raises(ValueError, match="hash|bytes"):
        read_partial_run(folder, spec)
    import json

    row["elapsed_seconds"] += 1.0
    path.write_text(json.dumps(row))
    assert path.stat().st_size == receipt["files"][0]["bytes"]
    with pytest.raises(ValueError, match="hash"):
        read_partial_run(folder, spec)


def test_partial_resume_refuses_orphan_files_changed_protocol_and_incomplete_bindings(
    tmp_path,
):
    import json

    from training.evaluation_v2_runner import read_partial_run

    spec, folder, row, receipt = partial_run(tmp_path)
    (folder / "tactic-w.json").write_text(json.dumps(row))
    with pytest.raises(ValueError, match="uncommitted|inventory"):
        read_partial_run(folder, spec)
    (folder / "tactic-w.json").unlink()
    (folder / "protocol.json").write_text(json.dumps(dict(spec, purpose="holdout")))
    with pytest.raises(ValueError, match="protocol"):
        read_partial_run(folder, spec)
    (folder / "protocol.json").write_text(json.dumps(spec))
    changed = deepcopy(spec)
    changed["search_limits"]["max_nodes"] += 1
    with pytest.raises(ValueError, match="protocol"):
        read_partial_run(folder, changed)
    receipt["games"] = 2
    (folder / "run.json").write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        read_partial_run(folder, spec)


def test_fake_port_resume_keeps_committed_matches_and_skips_their_execution(
    monkeypatch, tmp_path
):
    import json
    import sys
    from types import SimpleNamespace

    from training.evaluation_v2_runner import run_protocol, verify_run

    spec = protocol()
    participant = {
        "artifact_sha256": "b" * 64,
        "policy": "alphabeta-v1",
        "backend": "rust",
    }
    spec["participants"] = {"model": dict(participant), "opponent": dict(participant)}
    monkeypatch.setattr("training.evaluation_v2_runner.sys.platform", "linux")
    monkeypatch.setitem(
        sys.modules,
        "voxelshogi",
        SimpleNamespace(
            Game=SimpleNamespace(from_record=lambda r: FakeGame(r, mate_after=1))
        ),
    )
    monkeypatch.setattr(
        "training.evaluation_v2_runner.subprocess.check_output",
        lambda cmd, **kw: spec["source_commit"] if cmd[1] == "rev-parse" else "",
    )
    calls = []

    def choose(_):
        calls.append(1)
        return 7

    monkeypatch.setattr(
        "training.evaluation_v2_runner._prepare_players",
        lambda *a: {"model": choose, "opponent": choose},
    )
    monkeypatch.setattr("training.evaluation_v2_runner.verify_record", lambda *a: None)
    folder = tmp_path / "fake-resume"
    first = folder / "tactic-b.json"
    with pytest.raises(InterruptedError):
        run_protocol(spec, {}, folder, stop_requested=first.exists)
    before = first.read_bytes()
    assert json.loads((folder / "run.json").read_text())["games"] == 1
    result = run_protocol(spec, {}, folder, resume=True)
    assert first.read_bytes() == before and len(calls) == 4
    assert result["overall"]["games"] == 4 and verify_run(folder) == result
    assert run_protocol(spec, {}, folder, resume=True) == result
    assert len(calls) == 4  # a complete receipt does not allocate/execute new players


def test_partial_resume_rechecks_metadata_even_when_changed_file_hash_is_rebound(
    tmp_path,
):
    import json

    from training.evaluation_v2_runner import read_partial_run
    from training.feature_cache import file_hash

    spec, folder, row, receipt = partial_run(tmp_path)
    row["model_sha256"] = "f" * 64
    path = folder / "tactic-b.json"
    path.write_text(json.dumps(row))
    receipt["files"][0].update(bytes=path.stat().st_size, sha256=file_hash(path))
    (folder / "run.json").write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        read_partial_run(folder, spec)
