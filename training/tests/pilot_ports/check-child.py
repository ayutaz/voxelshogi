"""Bounded child lifecycle with fake ports only; no real processes or numerics."""

import runpy
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from training.evaluation_v2 import fingerprint

module = runpy.run_path("infrastructure/research/pilot/child.py")
inputs = {
    "source_commit": "a" * 40,
    "quality_decision": {"pilot_allowed": True},
    "config": {"total_updates": 7, "device": "cuda"},
}
result = {
    "schema": "voxelshogi-research-pilot-attempt-result-v1",
    "source_commit": inputs["source_commit"],
    "input_contract_sha256": fingerprint(inputs),
    "teacher_decision_sha256": fingerprint(inputs["quality_decision"]),
    "resume": True,
    "encoding": {"feature_content_sha256": "b" * 64},
    "fit": {
        "reason": "complete",
        "progress": {"step": 7},
        "new_steps": 3,
        "binding": {
            "source_commit": inputs["source_commit"],
            "config": inputs["config"],
            "cache_sha256": "b" * 64,
        },
    },
    "preparation_seconds": 1.0,
    "fitting_call_seconds": 2.0,
    "whole_attempt_seconds": 3.0,
}
module["review_attempt"](result, inputs, resume=True, max_new_steps=None)
for change in (
    lambda r: r.update(input_contract_sha256="0" * 64),
    lambda r: r.update(resume=False),
    lambda r: r["fit"]["progress"].update(step=6),
    lambda r: r["fit"]["binding"].update(cache_sha256="0" * 64),
    lambda r: r.update(whole_attempt_seconds=float("nan")),
    lambda r: r.update(
        whole_attempt_seconds=float("inf"), preparation_seconds=float("inf")
    ),
    lambda r: r["fit"].update(reason="max_new_steps"),
    lambda r: r["fit"].update(reason="max_new_steps", progress={"step": 6}),
):
    changed = deepcopy(result)
    change(changed)
    try:
        module["review_attempt"](changed, inputs, resume=True, max_new_steps=None)
    except ValueError:
        pass
    else:
        raise AssertionError("stale/partial/unbound child result admitted")
env = module["child_environment"](
    {
        "PATH": "/opaque",
        "HF_TOKEN": "fake",
        "VAST_API_KEY": "fake",
        "GH_TOKEN": "fake",
        "PYTHONPATH": ".",
    }
)
assert env == {
    "PATH": "/opaque",
    "PYTHONPATH": ".",
    "CUBLAS_WORKSPACE_CONFIG": ":4096:8",
}


class Child:
    pid = 123

    def __init__(self, *, done=False, ignores_term=False):
        self.done, self.ignores_term, self.calls = done, ignores_term, []

    def poll(self):
        return 0 if self.done else None

    def wait(self, timeout):
        import subprocess

        self.calls.append(timeout)
        if self.ignores_term and len(self.calls) == 1:
            raise subprocess.TimeoutExpired("opaque", timeout)
        self.done = True
        return 0


for ignores_term in (False, True):
    child = Child(ignores_term=ignores_term)
    with patch("os.killpg") as kill:
        result = module["stop_owned_child"](child)
        assert kill.call_count == (2 if ignores_term else 1)
        assert result == ("killed" if ignores_term else "terminated")
child = Child(done=True)
with patch("os.killpg") as kill:
    assert module["stop_owned_child"](child) == "already-terminal"
    kill.assert_not_called()
try:
    module["run_attempt"](Path("opaque"), Path("opaque"), Path("opaque"), deadline=1)
except ValueError as error:
    assert "external Linux" in str(error)
else:
    raise AssertionError("Mac spawned an actual child")
print(
    "Clean child environment, owned TERM/KILL/terminal paths and Mac-before-spawn checked; actual processes0"
)
