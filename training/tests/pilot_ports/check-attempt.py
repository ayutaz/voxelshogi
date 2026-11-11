"""Handwritten metadata only; no actual corpus, Torch or model execution."""

import copy
import runpy
from dataclasses import replace

from export.research_contract import ResearchConfig
from training.evaluation_v2 import fingerprint
from training.research_visit_fit import VisitRunConfig

module = runpy.run_path("infrastructure/research/pilot/attempt.py")
audit = {
    "source_manifest_sha256": "1" * 64,
    "source_protocol_sha256": "2" * 64,
    "source_protection_sha256": "3" * 64,
    "screen_config_sha256": "4" * 64,
    "admission": {"usable_for_pilot": True},
}
protection = {
    "passed": True,
    "overlaps": [],
    "source_release_manifest_sha256": "5" * 64,
}
diagnosis = {"hand_counted_target_rows": 3, "teacher_quality_accepted": False}
manifest = {
    "failure": None,
    "report": {"training_executed": False, "teacher_quality_accepted": False},
    "diagnosis_records": {
        "admission.json": audit,
        "development-protection.json": protection,
        "target-diagnosis.json": diagnosis,
        "result.json": {"source_bytes": {"different-retired-VM/local-path": "opaque"}},
    },
}
inputs = {
    "schema": "voxelshogi-research-pilot-attempt-inputs-v1",
    "source_commit": "a" * 40,
    "admission_sha256": fingerprint(audit),
    "development_protection_sha256": fingerprint(protection),
    "diagnosis_sha256": fingerprint(diagnosis),
    "paths": {
        "selfplay": "runs/new-VM/input-selfplay",
        "protocol": "runs/new-VM/protocol.json",
        "protection": "runs/new-VM/input-protection/config.json",
        "screen": "runs/new-VM/input-screen/config.json",
        "diagnosis_manifest": "runs/new-VM/input-diagnosis/manifest.json",
    },
    "maximum_feature_bytes": 2 * 1024**3,
    "config": VisitRunConfig().value(),
}
inputs["quality_decision"] = {
    "schema": "voxelshogi-research-teacher-decision-v1",
    **{
        k: inputs[k]
        for k in (
            "admission_sha256",
            "development_protection_sha256",
            "diagnosis_sha256",
        )
    },
    "pilot_allowed": True,
    "main_comparison_allowed": False,
    "basis": "Opaque hand fixture; not an actual teacher review",
    "limitations": "No real data processing or learning",
}
hashes = dict(
    zip(
        (
            "selfplay_manifest",
            "protocol_fingerprint",
            "protection",
            "screen_config",
            "screen_manifest",
        ),
        [str(i) * 64 for i in range(1, 6)],
        strict=True,
    )
)
c, decision_sha = module["validate_inputs"](inputs)
assert c.device == "cuda" and decision_sha == fingerprint(inputs["quality_decision"])
assert module["reviewed_audit"](manifest, inputs, hashes) == audit


def reject_input(change):
    value = copy.deepcopy(inputs)
    change(value)
    try:
        module["validate_inputs"](value)
    except ValueError:
        return
    raise AssertionError("invalid pilot input admitted")


reject_input(lambda v: v["quality_decision"].update(pilot_allowed=False))
reject_input(lambda v: v["quality_decision"].update(main_comparison_allowed=True))
reject_input(lambda v: v["quality_decision"].update(diagnosis_sha256="0" * 64))
reject_input(lambda v: v["quality_decision"].update(basis=" "))
reject_input(lambda v: v["paths"].update(selfplay="/outside/data"))
reject_input(lambda v: v["paths"].update(screen="../outside.json"))
reject_input(lambda v: v.update(maximum_feature_bytes=True))
reject_input(lambda v: v.update(maximum_feature_bytes=2 * 1024**3 + 1))
reject_input(lambda v: v.update(config=VisitRunConfig(device="cpu").value()))
reject_input(
    lambda v: v.update(
        config=replace(
            VisitRunConfig(),
            architecture=ResearchConfig(
                "full", side=2, width=4, layers=1, heads=2, ffn=8, policy_rank=2
            ),
        ).value()
    )
)
for key in hashes:
    changed = {**hashes, key: "0" * 64}
    try:
        module["reviewed_audit"](manifest, inputs, changed)
    except ValueError:
        pass
    else:
        raise AssertionError("old zero-overlap report bound to changed source")
partial = copy.deepcopy(manifest)
partial["failure"] = {"error_type": "InterruptedError"}
try:
    module["reviewed_audit"](partial, inputs, hashes)
except ValueError:
    pass
else:
    raise AssertionError("partial diagnosis admitted")
try:
    module["run"]({}, "opaque", deadline=1)
except ValueError as error:
    assert "external Linux" in str(error)
else:
    raise AssertionError("Mac reached numerical execution")
print(
    "Reviewed diagnosis/decision hashes, role-bound portable source identity, strict pilot-only CUDA contract and Mac boundary checked; actual data/models0"
)
