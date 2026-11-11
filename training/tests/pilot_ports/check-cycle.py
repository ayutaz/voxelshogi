"""Handwritten execution order and stop evidence, with all numerical/HF ports fake."""

import json
import runpy
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

module = runpy.run_path("infrastructure/research/pilot/cycle.py")
inputs = runpy.run_path("training/tests/pilot_ports/check-attempt.py")["inputs"]
for failure in (None, "partial-primary", "unverified-transfer", "parity"):
    with tempfile.TemporaryDirectory(prefix="voxelshogi-pilot-cycle-fake-") as td:
        root = Path(td)
        calls = []

        def launch(script, input_path, output, **kw):
            assert json.loads(Path(input_path).read_text()) == inputs
            assert kw["deadline"] == deadline - 20
            calls.append(("launch", output.name, kw["resume"], kw["max_new_steps"]))
            output.mkdir(exist_ok=kw["resume"])
            reason = "complete" if kw["max_new_steps"] is None else "max_new_steps"
            if failure == "partial-primary" and output.name == "continuous":
                reason = "stopped"
            return {"fit": {"reason": reason}}

        def pack(source, output):
            calls.append(("pack", source.name))
            output.mkdir()

        def transfer(folder, control, restored, **kw):
            assert kw["deadline"] == deadline
            calls.append(("transfer", folder.name))
            restored.mkdir()
            return {
                "receipt": {"verified": failure != "unverified-transfer"},
                "restored": True,
            }

        def prove(a, b, **kw):
            assert kw["total_updates"] == inputs["config"]["total_updates"]
            calls.append(("prove", a.name, b.name))
            return {"verified": failure != "parity"}

        ports = {"launch": launch, "pack": pack, "transfer": transfer, "prove": prove}
        deadline = time.time() + 60
        with patch.object(module["sys"], "platform", "linux"):
            try:
                result = module["run_cycle"](
                    inputs,
                    root / "cycle",
                    split_step=3,
                    deadline=deadline,
                    compute_deadline=deadline - 20,
                    api=None,
                    fetch=None,
                    upload_budget=None,
                    ports=ports,
                )
            except ValueError:
                assert failure is not None
                assert (root / "cycle/failure.json").is_file()
                assert not (root / "cycle/complete.json").exists()
            else:
                assert failure is None
                assert [c[0] for c in calls] == [
                    "launch",
                    "launch",
                    "pack",
                    "transfer",
                    "launch",
                    "prove",
                    "pack",
                    "transfer",
                ]
                assert calls[0] == ("launch", "continuous", False, None)
                assert calls[1] == ("launch", "interrupted", False, 3)
                assert calls[4] == ("launch", "restored", True, None)
                assert result["scientific_pilots"] == 1
                assert result["additional_independent_seeds"] == 0
                assert result["development_evaluation_executed"] is False
                assert result["final_holdout_evaluated"] is False
try:
    module["run_cycle"](
        {},
        "opaque",
        split_step=3,
        deadline=1,
        compute_deadline=0,
        api=None,
        fetch=None,
        upload_budget=None,
    )
except ValueError as error:
    assert "external Linux" in str(error)
else:
    raise AssertionError("Mac entered actual pilot cycle")
print(
    "One scientific run plus replay companion, two HF roundtrips, partial/parity/transfer failures and no holdout; all ports fake, real operations0"
)
