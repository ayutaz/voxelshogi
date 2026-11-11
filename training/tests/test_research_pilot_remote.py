"""Credential-by-stdin launch contract through opaque subprocess ports."""

import base64
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from training.checkpoint import atomic_json
from training.tests.test_research_pilot_workflow import setup


@pytest.mark.parametrize(
    "mode",
    ["complete", "duplicate", "wrong-ledger", "changed-source", "provider-key", "mac"],
)
def test_remote_installs_frozen_bytes_and_launches_once_without_persisting_token(
    tmp_path, monkeypatch, mode
):
    from infrastructure.research.pilot import job
    from infrastructure.research.pilot.remote import install_inputs, launch_worker

    value, _, _, _ = setup(tmp_path, monkeypatch)
    base = Path(value["job"]["base"])
    ledger = (base / "state-upload-budget.json").read_bytes()
    (base / "state-upload-budget.json").unlink()
    atomic_json(
        base / "bootstrap-complete.json",
        {"complete": True, "source_commit": value["job"]["source_commit"]},
    )
    owner = {
        "provider": "vast.ai",
        "instance_id": 123,
        "tag": "voxelshogi-phase6-research-pilot1-control",
    }
    monkeypatch.setattr(job, "check_source", lambda source: None)
    if mode == "changed-source":
        monkeypatch.setattr(
            job,
            "check_source",
            lambda source: (_ for _ in ()).throw(ValueError("source changed")),
        )
    data = base64.b64encode(
        ledger + b"\n" if mode == "wrong-ledger" else ledger
    ).decode()
    monkeypatch.setenv("UNRELATED_SERVICE_KEY", "opaque-unrelated-test-key")
    calls = []

    def popen(command, **kwargs):
        calls.append((command, kwargs))
        assert kwargs["env"]["HF_TOKEN"] == "opaque-test-token-not-a-credential"
        assert kwargs["env"]["HF_TOKEN_PATH"] == "/dev/null"
        assert "UNRELATED_SERVICE_KEY" not in kwargs["env"]
        assert "opaque-test-token-not-a-credential" not in json.dumps(command)
        assert kwargs["start_new_session"] is True
        return SimpleNamespace(pid=17)

    with patch("sys.platform", "darwin" if mode == "mac" else "linux"):
        if mode in ("wrong-ledger", "changed-source", "mac"):
            with pytest.raises(ValueError):
                install_inputs(
                    value, ledger_base64=data, owner=owner, clock=lambda: 100
                )
            assert calls == []
            return
        install_inputs(value, ledger_base64=data, owner=owner, clock=lambda: 100)
        # A lost install observation can be reconciled using exactly the same bytes.
        install_inputs(value, ledger_base64=data, owner=owner, clock=lambda: 100)
        if mode == "duplicate":
            atomic_json(base / "job-launch-request.json", {"prior": True})
        elif mode == "provider-key":
            monkeypatch.setenv("VAST_API_KEY", "opaque-provider-key-no-credential")
        kwargs = {
            "hf_token": "opaque-test-token-not-a-credential",
            "owner": owner,
            "popen": popen,
            "birth": lambda pid: 10.5,
            "clock": lambda: 100,
        }
        if mode in ("duplicate", "provider-key"):
            with pytest.raises(ValueError):
                launch_worker(value, **kwargs)
            assert calls == []
        else:
            result = launch_worker(value, **kwargs)
            assert result["pid"] == 17 and result["create_time"] == 10.5
            assert calls[0][0][-2:] == [
                "infrastructure.research.pilot.workflow",
                str(base / "workflow.json"),
            ]
            with pytest.raises(ValueError):
                launch_worker(value, **kwargs)
            assert len(calls) == 1
        for name in (
            "workflow.json",
            "job-launch-request.json",
            "job-launch.json",
            "state-upload-budget.json",
        ):
            path = base / name
            if path.exists():
                assert "opaque-test-token-not-a-credential" not in path.read_text()
