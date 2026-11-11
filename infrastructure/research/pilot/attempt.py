"""One bounded, separate-process fit attempt from reviewed immutable inputs.

No rental, HF credentials, publication or test evaluation belongs in this child.
Run only on the source-admitted external Linux host after actual data diagnosis.
"""

import argparse
import json
import math
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path


def validate_inputs(value):
    from export.research_contract import architecture_config
    from training.evaluation_v2 import fingerprint
    from training.research_visit_fit import VisitRunConfig

    if (
        type(value) is not dict
        or set(value)
        != {
            "schema",
            "source_commit",
            "admission_sha256",
            "development_protection_sha256",
            "diagnosis_sha256",
            "quality_decision",
            "paths",
            "maximum_feature_bytes",
            "config",
        }
        or value["schema"] != "voxelshogi-research-pilot-attempt-inputs-v1"
        or not isinstance(value["source_commit"], str)
        or re.fullmatch(r"[0-9a-f]{40}", value["source_commit"]) is None
        or any(
            not isinstance(value[k], str)
            or re.fullmatch(r"[0-9a-f]{64}", value[k]) is None
            for k in (
                "admission_sha256",
                "development_protection_sha256",
                "diagnosis_sha256",
            )
        )
        or type(value["maximum_feature_bytes"]) is not int
        or not 1 <= value["maximum_feature_bytes"] <= 2 * 1024**3
        or type(value["paths"]) is not dict
        or set(value["paths"])
        != {"selfplay", "protocol", "protection", "screen", "diagnosis_manifest"}
        or any(
            not isinstance(p, str)
            or not p
            or Path(p).is_absolute()
            or ".." in Path(p).parts
            for p in value["paths"].values()
        )
    ):
        raise ValueError("invalid frozen pilot input contract")
    decision = value["quality_decision"]
    if (
        type(decision) is not dict
        or set(decision)
        != {
            "schema",
            "admission_sha256",
            "development_protection_sha256",
            "diagnosis_sha256",
            "pilot_allowed",
            "main_comparison_allowed",
            "basis",
            "limitations",
        }
        or decision["schema"] != "voxelshogi-research-teacher-decision-v1"
        or any(
            decision[k] != value[k]
            for k in (
                "admission_sha256",
                "development_protection_sha256",
                "diagnosis_sha256",
            )
        )
        or decision["pilot_allowed"] is not True
        or decision["main_comparison_allowed"] is not False
        or any(
            not isinstance(decision[k], str) or not decision[k].strip()
            for k in ("basis", "limitations")
        )
    ):
        raise ValueError("actual reviewed diagnosis is required before a pilot")
    config = VisitRunConfig.from_value(value["config"])
    if config.device != "cuda":
        raise ValueError("pilot requires explicit CUDA; no Mac/CPU fallback")
    if config.architecture != architecture_config(config.architecture.architecture):
        raise ValueError(
            "pilot requires the actual fixed M structure, not a tiny CI model"
        )
    return config, fingerprint(decision)


def reviewed_audit(manifest, inputs, source_hashes):
    """Bind earlier zero-overlap evidence by source role, not a VM-local path."""
    from training.evaluation_v2 import fingerprint

    if manifest["failure"] is not None or manifest["report"] is None:
        raise ValueError("completed diagnosis required before feature encoding")
    records = manifest["diagnosis_records"]
    audit = records["admission.json"]
    protection = records["development-protection.json"]
    if (
        fingerprint(audit) != inputs["admission_sha256"]
        or fingerprint(protection) != inputs["development_protection_sha256"]
        or fingerprint(records["target-diagnosis.json"]) != inputs["diagnosis_sha256"]
        or protection["passed"] is not True
        or protection["overlaps"]
        or audit["admission"]["usable_for_pilot"] is not True
        or manifest["report"]["training_executed"] is not False
        or manifest["report"]["teacher_quality_accepted"] is not False
        or source_hashes
        != {
            "selfplay_manifest": audit["source_manifest_sha256"],
            "protocol_fingerprint": audit["source_protocol_sha256"],
            "protection": audit["source_protection_sha256"],
            "screen_config": audit["screen_config_sha256"],
            "screen_manifest": protection["source_release_manifest_sha256"],
        }
    ):
        raise ValueError("reviewed diagnosis/input source binding differs")
    return audit


def run(inputs, output, *, deadline, resume=False, max_new_steps=None):
    if sys.platform != "linux":
        raise ValueError("pilot fitting requires external Linux")
    if (
        type(deadline) not in (int, float)
        or not math.isfinite(deadline)
        or type(resume) is not bool
        or (
            max_new_steps is not None
            and (type(max_new_steps) is not int or max_new_steps < 1)
        )
    ):
        raise ValueError("invalid fixed pilot attempt bounds")
    import os

    assert not any(
        os.environ.get(k) for k in ("HF_TOKEN", "VAST_API_KEY", "CLOUDRIFT_API_KEY")
    )
    from training.checkpoint import atomic_json
    from training.evaluation_v2 import fingerprint
    from training.feature_cache import file_hash
    from training.research_visit_data import encode_corpus
    from training.research_visit_fit import fit_visits

    config, decision_sha = validate_inputs(inputs)
    assert (
        subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        == inputs["source_commit"]
    )
    assert not subprocess.check_output(["git", "status", "--porcelain"], text=True)
    paths = {name: Path(path) for name, path in inputs["paths"].items()}
    manifest = json.loads(paths["diagnosis_manifest"].read_text())
    audit = reviewed_audit(
        manifest,
        inputs,
        {
            "selfplay_manifest": file_hash(paths["selfplay"] / "manifest.json"),
            "protocol_fingerprint": fingerprint(
                json.loads(paths["protocol"].read_text())
            ),
            "protection": file_hash(paths["protection"]),
            "screen_config": file_hash(paths["screen"]),
            "screen_manifest": file_hash(paths["screen"].parent / "manifest.json"),
        },
    )
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())

    def stopping():
        return stop.is_set() or time.time() >= deadline

    if stopping():
        raise InterruptedError("fixed pilot preparation deadline")
    started = time.monotonic()
    corpus, encoding = encode_corpus(
        paths["selfplay"],
        json.loads(paths["protocol"].read_text()),
        paths["protection"],
        paths["screen"],
        screen_sha256=audit["screen_config_sha256"],
        expected_audit_sha256=inputs["admission_sha256"],
        maximum_feature_bytes=inputs["maximum_feature_bytes"],
    )
    # Full development-input protection and the measured teacher decision enter
    # the actual feature digest and thus the fitter's resume binding.
    for split in (corpus.train, corpus.val):
        split.provenance.update(
            full_development_protection_sha256=inputs["development_protection_sha256"],
            teacher_decision_sha256=decision_sha,
        )
    encoding["feature_content_sha256"] = corpus.digest(config)
    encoding["teacher_decision_sha256"] = decision_sha
    prepared = time.monotonic()
    result = fit_visits(
        corpus,
        output,
        config=config,
        source_commit=inputs["source_commit"],
        resume=resume,
        max_new_steps=max_new_steps,
        stop_requested=stopping,
    )
    ended = time.monotonic()
    record = {
        "schema": "voxelshogi-research-pilot-attempt-result-v1",
        "source_commit": inputs["source_commit"],
        "input_contract_sha256": fingerprint(inputs),
        "teacher_decision_sha256": decision_sha,
        "encoding": encoding,
        "fit": result,
        "preparation_seconds": prepared - started,
        "fitting_call_seconds": ended - prepared,
        "whole_attempt_seconds": ended - started,
        "resume": resume,
        "scope": "One actual CUDA attempt; fixed full-run updates differ from per-attempt stop. Feature replay, corpus digest, model construction/checkpoint IO included in wrapper timing. Not pure kernel speed or total training FLOPs. No test/final-holdout evaluation or strength adoption.",
    }
    atomic_json(Path(output) / "attempt-wrapper.json", record)
    return record


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("inputs", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--compute-deadline", type=float, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-new-steps", type=int)
    args = parser.parse_args()
    result = run(
        json.loads(args.inputs.read_text()),
        args.output,
        deadline=args.compute_deadline,
        resume=args.resume,
        max_new_steps=args.max_new_steps,
    )
    print(
        json.dumps(
            {
                "source_commit": result["source_commit"],
                "reason": result["fit"]["reason"],
                "progress": result["fit"]["progress"],
                "whole_attempt_seconds": result["whole_attempt_seconds"],
            }
        )
    )


if __name__ == "__main__":
    main()
