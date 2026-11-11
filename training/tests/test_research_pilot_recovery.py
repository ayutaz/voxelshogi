"""Failure recovery uses opaque files and ports; no real Torch, HF or child."""

import json
from unittest.mock import patch

import pytest


@pytest.mark.parametrize(
    "mode",
    [
        "complete",
        "failed-transfer",
        "unverified",
        "pack-failed",
        "ambiguous",
        "expired",
        "duplicate",
    ],
)
def test_failed_cycle_preserves_each_owned_checkpoint_without_repeating_unknown_upload(
    tmp_path, mode
):
    from infrastructure.research.pilot.cycle import recover_cycle

    base = tmp_path / "cycle"
    base.mkdir()
    for name in ("continuous", "restored"):
        folder = base / name
        folder.mkdir()
        (folder / "run.json").write_text('{"opaque":true}')
    # A directory alone is not a checkpoint and must not be called preserved.
    (base / "interrupted").mkdir()
    if mode == "ambiguous":
        control = base / "intermediate-transfer"
        control.mkdir()
        (control / "publication-attempt.json").write_text("{}")
    if mode == "duplicate":
        (base / "failure-rescue-request.json").write_text("{}")
    calls = []

    def pack(source, folder):
        assert source.name in ("continuous", "restored")
        calls.append(("pack", source.name))
        if mode == "pack-failed":
            raise ValueError("opaque invalid checkpoint")
        folder.mkdir()

    def transfer(folder, control, restored, **kwargs):
        calls.append(("transfer", folder.name))
        assert kwargs["deadline"] == (90 if mode == "expired" else 200)
        assert kwargs["api"] == "opaque-api"
        assert kwargs["fetch"] == "opaque-fetch"
        assert kwargs["upload_budget"] == "opaque-ledger"
        assert not control.exists() and not restored.exists()
        control.mkdir()
        if mode == "failed-transfer":
            raise ConnectionError("diagnostics must not retain arbitrary text")
        return {"receipt": {"verified": mode != "unverified"}, "restored": True}

    with patch("sys.platform", "linux"):
        result = recover_cycle(
            base,
            deadline=90 if mode == "expired" else 200,
            api="opaque-api",
            fetch="opaque-fetch",
            upload_budget="opaque-ledger",
            ports={"pack": pack, "transfer": transfer},
            clock=lambda: 100,
        )
    assert result["job_complete"] is False
    assert result["host_retirement_authorized"] is False
    if mode == "complete":
        assert calls == [
            ("pack", "continuous"),
            ("transfer", "failure-rescue-continuous-archive"),
            ("pack", "restored"),
            ("transfer", "failure-rescue-restored-archive"),
        ]
        assert result["states_preserved"] is True
        assert result["unpreserved_runs"] == []
        assert [r["run"] for r in result["records"]] == ["continuous", "restored"]
    else:
        assert result["states_preserved"] is False
        assert result["unpreserved_runs"]
        if mode in ("ambiguous", "expired", "duplicate"):
            assert calls == []
        elif mode == "pack-failed":
            assert calls == [("pack", "continuous"), ("pack", "restored")]
            assert all(r["error_type"] == "ValueError" for r in result["records"])
        else:
            # An upload response is now unknown: do not make another write.
            assert calls == [
                ("pack", "continuous"),
                ("transfer", "failure-rescue-continuous-archive"),
            ]
            assert result["records"][0]["error_type"] == (
                "ValueError" if mode == "unverified" else "ConnectionError"
            )
    assert "diagnostics must not" not in json.dumps(result)


def test_no_checkpoint_is_not_preservation_evidence_and_mac_cannot_enter_recovery(
    tmp_path,
):
    from infrastructure.research.pilot.cycle import recover_cycle

    with patch("sys.platform", "linux"):
        result = recover_cycle(
            tmp_path,
            deadline=200,
            api=None,
            fetch=None,
            upload_budget=None,
            ports={},
            clock=lambda: 100,
        )
    assert result["states_preserved"] is False
    assert result["records"] == []
    with (
        patch("sys.platform", "darwin"),
        pytest.raises(ValueError, match="external Linux"),
    ):
        recover_cycle(
            tmp_path, deadline=200, api=None, fetch=None, upload_budget=None, ports={}
        )


def test_compute_deadline_is_distinct_from_reserved_transfer_deadline(tmp_path):
    import runpy

    from infrastructure.research.pilot.cycle import run_cycle

    with patch("sys.platform", "darwin"):
        inputs = runpy.run_path("training/tests/pilot_ports/check-attempt.py")["inputs"]
    observed = []

    def launch(script, input_path, output, **kw):
        observed.append(("fit", kw["deadline"]))
        output.mkdir(exist_ok=kw["resume"])
        return {
            "fit": {"reason": "max_new_steps" if kw["max_new_steps"] else "complete"}
        }

    def pack(*args):
        pass

    def transfer(folder, control, restored, **kw):
        observed.append(("transfer", kw["deadline"]))
        restored.mkdir()
        return {"receipt": {"verified": True}, "restored": True}

    with patch("sys.platform", "linux"), patch("time.time", return_value=100):
        result = run_cycle(
            inputs,
            tmp_path / "cycle",
            split_step=3,
            deadline=300,
            compute_deadline=200,
            api=None,
            fetch=None,
            upload_budget=None,
            ports={
                "launch": launch,
                "pack": pack,
                "transfer": transfer,
                "prove": lambda *a, **k: {"verified": True},
            },
        )
    assert observed == [
        ("fit", 200),
        ("fit", 200),
        ("transfer", 300),
        ("fit", 200),
        ("transfer", 300),
    ]
    assert result["scientific_pilots"] == 1


def test_cycle_failure_calls_recovery_and_keeps_original_failure(tmp_path, monkeypatch):
    import runpy

    from infrastructure.research.pilot import cycle

    with patch("sys.platform", "darwin"):
        inputs = runpy.run_path("training/tests/pilot_ports/check-attempt.py")["inputs"]
    calls = []

    def failed(*args, **kwargs):
        raise RuntimeError("opaque original failure")

    def recover(base, **kwargs):
        calls.append((base, kwargs["deadline"]))
        return {"states_preserved": False, "job_complete": False}

    monkeypatch.setattr(cycle, "recover_cycle", recover)
    with (
        patch("sys.platform", "linux"),
        patch("time.time", return_value=100),
        pytest.raises(RuntimeError, match="opaque original"),
    ):
        cycle.run_cycle(
            inputs,
            tmp_path / "cycle",
            split_step=3,
            deadline=300,
            compute_deadline=200,
            api=None,
            fetch=None,
            upload_budget=None,
            ports={"launch": failed, "pack": None, "transfer": None, "prove": None},
        )
    assert calls == [(tmp_path / "cycle", 300)]
    failure = json.loads((tmp_path / "cycle/failure.json").read_text())
    assert failure["stage"] == "continuous" and failure["error_type"] == "RuntimeError"
    assert failure["recovery"]["states_preserved"] is False


@pytest.mark.parametrize("compute_end", [100, 300, 301, float("nan"), True, None])
def test_cycle_rejects_missing_or_nonreserved_transfer_window(tmp_path, compute_end):
    import runpy

    from infrastructure.research.pilot.cycle import run_cycle

    with patch("sys.platform", "darwin"):
        inputs = runpy.run_path("training/tests/pilot_ports/check-attempt.py")["inputs"]
    with (
        patch("sys.platform", "linux"),
        patch("time.time", return_value=100),
        pytest.raises(ValueError),
    ):
        run_cycle(
            inputs,
            tmp_path / "cycle",
            split_step=3,
            deadline=300,
            compute_deadline=compute_end,
            api=None,
            fetch=None,
            upload_budget=None,
            ports={},
        )
    assert not (tmp_path / "cycle").exists()
