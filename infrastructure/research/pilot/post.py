"""Reconstruct fixed train/val and diagnose the same selected M weights.

Run on the admitted external Linux host after a complete learning cycle. This
stage does not query test/final roots, upload results or authorize retirement.
"""

import argparse
import json
import math
import os
import signal
import sys
import threading
import time
from pathlib import Path

from infrastructure.research.pilot.attempt import prepare_corpus, validate_inputs
from infrastructure.research.pilot.validation import origin_metrics
from training.checkpoint import atomic_json
from training.evaluation_v2 import fingerprint
from training.feature_cache import file_hash
from training.fit import runtime_environment
from training.research_selection import export_selected_weights
from training.research_visit_fit import validate_binding
from training.research_weights import load_research_network


def run_post(
    inputs,
    run,
    output,
    *,
    deadline,
    clock=time.time,
    stop_requested=lambda: False,
    ports=None,
):
    if sys.platform != "linux":
        raise ValueError("pilot diagnostics require external Linux")
    if os.environ.get("CUBLAS_WORKSPACE_CONFIG") != ":4096:8":
        raise ValueError("set deterministic CUDA workspace before diagnostics")
    config, decision_sha = validate_inputs(inputs)
    if type(deadline) not in (int, float) or not math.isfinite(deadline):
        raise ValueError("fixed diagnostic deadline required")

    def stopping():
        return stop_requested() or clock() >= deadline

    if stopping():
        raise InterruptedError("fixed diagnostic deadline")
    ports = (
        {
            "prepare": prepare_corpus,
            "environment": runtime_environment,
            "export": export_selected_weights,
            "network": load_research_network,
            "metrics": origin_metrics,
        }
        if ports is None
        else ports
    )
    if set(ports) != {"prepare", "environment", "export", "network", "metrics"}:
        raise ValueError("complete diagnostic execution ports required")
    run, output = Path(run), Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError("fresh diagnostic output required")
    output.mkdir(parents=True, exist_ok=False)
    atomic_json(
        output / "request.json",
        {
            "source_commit": inputs["source_commit"],
            "inputs_sha256": fingerprint(inputs),
            "deadline": deadline,
        },
    )
    stage = "verified-feature-reconstruction"
    started = clock()
    try:
        actual_config, actual_decision, data, encoding = ports["prepare"](
            inputs, stop_requested=stopping
        )
        if (
            actual_config != config
            or actual_decision != decision_sha
            or encoding["test_features_encoded"] != 0
        ):
            raise ValueError("diagnostic preparation escaped the frozen inputs")
        if stopping():
            raise InterruptedError("diagnostic feature deadline")
        run_path = run / "run.json"
        if (
            run_path.is_symlink()
            or not run_path.is_file()
            or run_path.stat().st_size > 1024**2
        ):
            raise ValueError("bounded regular run binding required")
        saved = json.loads(run_path.read_text())
        binding = saved["binding"]
        validate_binding(binding)
        digest = data.digest(config)
        if (
            saved != {"schema": "voxelshogi-training-run-v1", "binding": binding}
            or binding["source_commit"] != inputs["source_commit"]
            or binding["config"] != config.value()
            or binding["contract"]["admission_sha256"] != inputs["admission_sha256"]
            or binding["cache_sha256"] != digest
            or encoding["feature_content_sha256"] != digest
        ):
            raise ValueError("reconstructed diagnostic data/config binding differs")
        stage = "runtime-and-best-selection"
        if ports["environment"](config) != binding["environment"]:
            raise ValueError("diagnostic CUDA environment differs from training")
        selected = output / "selected"
        selection = ports["export"](run, selected, expected_binding=binding)
        weights = selected / "model.safetensors"
        if stopping():
            raise InterruptedError("diagnostic selection deadline")
        network, metadata = ports["network"](
            weights, expected_sha256=selection["weights"]["sha256"], device="cuda"
        )
        if (
            metadata != selection["weights"]["metadata"]
            or network.config != config.architecture
            or network.training
        ):
            raise ValueError("diagnostic network differs from the selected M weights")
        stage = "separate-value-origin-validation"
        metrics = ports["metrics"](network, data.val, config, stop_requested=stopping)
        aggregate = metrics.get("aggregate", {})
        if (
            metrics.get("schema") != "voxelshogi-research-val-origins-v1"
            or metrics.get("split") != "val"
            or metrics.get("bootstrap_is_observed_outcome") is not False
            or type(aggregate.get("examples")) is not int
            or aggregate["examples"] != len(data.val.rows)
            or any(
                type(aggregate.get(k)) not in (int, float)
                or not math.isfinite(aggregate[k])
                or aggregate[k] < 0
                for k in ("policy_ce", "value_mse", "loss")
            )
            or not math.isclose(
                aggregate["loss"],
                aggregate["policy_ce"] + aggregate["value_mse"],
                rel_tol=1e-6,
                abs_tol=1e-7,
            )
        ):
            raise ValueError("fixed-val diagnostic metric/count differs")
        if stopping():
            raise InterruptedError("diagnostic validation deadline")
        if (
            file_hash(weights) != selection["weights"]["sha256"]
            or data.digest(config) != digest
            or json.loads(run_path.read_text()) != saved
        ):
            raise ValueError("diagnostic weights/data/run changed during evaluation")
        result = {
            "schema": "voxelshogi-research-pilot-diagnostic-v1",
            "source_commit": inputs["source_commit"],
            "inputs_sha256": fingerprint(inputs),
            "binding_sha256": fingerprint(binding),
            "cache_sha256": digest,
            "teacher_decision_sha256": decision_sha,
            "architecture": config.architecture.architecture,
            "selected_step": selection["selected_receipt"]["step"],
            "selection": {
                "folder": str(selected),
                "selection_sha256": file_hash(selected / "selection.json"),
            },
            "weights_sha256": selection["weights"]["sha256"],
            "origins": metrics,
            "test_features_encoded": 0,
            "final_holdout_evaluated": False,
            "elapsed_seconds": clock() - started,
            "scope": "Reconstruction, selected-best export/load and separate fixed-val origin diagnostics, including IO and hashing; not a pure kernel benchmark, independent seed, test evaluation or strength claim.",
        }
        atomic_json(output / "complete.json", result)
        return result
    except BaseException as error:
        atomic_json(
            output / "failure.json",
            {
                "complete": False,
                "stage": stage,
                "error_type": type(error).__name__,
                "final_holdout_evaluated": False,
            },
        )
        raise


def main():
    if sys.platform != "linux":
        raise ValueError("pilot diagnostics require external Linux")
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("inputs", type=Path)
    parser.add_argument("run", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--compute-deadline", type=float, required=True)
    args = parser.parse_args()
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    result = run_post(
        json.loads(args.inputs.read_text()),
        args.run,
        args.output,
        deadline=args.compute_deadline,
        stop_requested=stop.is_set,
    )
    print(
        json.dumps(
            {
                "source_commit": result["source_commit"],
                "architecture": result["architecture"],
                "selected_step": result["selected_step"],
                "test_features_encoded": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
