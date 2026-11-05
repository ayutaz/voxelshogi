"""Only the Mac boundary is exercised here; no model/data execution."""

import pytest


def test_preparation_refuses_mac_before_reading_models(monkeypatch, tmp_path):
    from training import research_browser_inputs as module

    monkeypatch.setattr(module.sys, "platform", "darwin")
    with pytest.raises(ValueError, match="Linux"):
        module.prepare_inputs(tmp_path, tmp_path / "output", plan={}, receipt={})
    assert not (tmp_path / "output").exists()
