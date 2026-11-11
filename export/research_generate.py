"""Convert the actual val-selected M weights on Linux; evaluation follows.

The output is deliberately conversion.json, never a publishable manifest.
All three actual ONNX files must subsequently receive their own frozen final
evaluation before an inference release/catalog entry can be assembled.
"""

import argparse
import hashlib
import json
import math
import re
import shutil
import sys
import time
from pathlib import Path

from export.research_contract import ResearchConfig, parameter_count
from training.checkpoint import atomic_json
from training.feature_cache import file_hash
from training.research_onnx import onnx_properties
from training.research_selection import review_selection, source_commit
from training.research_weights import _unique_object, research_metadata

ROOT = Path(__file__).resolve().parents[1]
NAMES = ("initial-b", "after-one-w", "mate-in-one-b", "material-b")


def _sha(value, length=64):
    return (
        isinstance(value, str)
        and re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is not None
    )


def review_inputs(selection, history):
    try:
        if (
            type(history) is not bytes
            or not 0 < len(history) <= 64 * 1024**2
            or hashlib.sha256(history).hexdigest() != selection["history_sha256"]
            or selection["schema"] != "voxelshogi-research-selection-v1"
            or selection["inference_publication_approved"] is not False
        ):
            raise ValueError("conversion needs the complete unchanged selected history")
        events = [
            json.loads(line, object_pairs_hook=_unique_object)
            for line in history.splitlines()
        ]
        metadata = review_selection(
            selection["binding"],
            selection["latest_receipt"],
            selection["selected_receipt"],
            events,
        )
        lineage, weights = selection["export_provenance"], selection["weights"]
        if (
            lineage["schema"] != "voxelshogi-export-lineage-v1"
            or lineage["training_source_commit"] != metadata["source_commit"]
            or not _sha(lineage["export_source_commit"], 40)
            or selection["binding"]["config"]["device"] != "cuda"
            or weights["path"] != "model.safetensors"
            or type(weights["bytes"]) is not int
            or not 0 < weights["bytes"] <= 512 * 1024**2
            or not _sha(weights["sha256"])
            or weights["metadata"] != metadata
        ):
            raise ValueError("selected M weights and source/history provenance differ")
        return {
            "metadata": metadata,
            "weights_sha256": weights["sha256"],
            "selection_export_source": lineage["export_source_commit"],
            "total_updates": selection["binding"]["config"]["total_updates"],
        }
    except (KeyError, TypeError, AttributeError, json.JSONDecodeError) as error:
        raise ValueError("incomplete selected M conversion inputs") from error


def _descriptor(root, path):
    path = Path(path)
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": file_hash(path),
    }


def _load(path, expected_sha256):
    from training.research_weights import load_research_network

    return load_research_network(path, expected_sha256=expected_sha256, device="cpu")


def _fixtures(output):
    import numpy as np
    from voxelshogi import Game

    from export.contract import encode_position
    from export.generate import write_floats

    positions = json.loads((ROOT / "export/fixtures/positions.json").read_text())
    if [p["name"] for p in positions] != list(NAMES):
        raise ValueError("all four fixed conversion fixtures required")
    result = []
    for position in positions:
        game = Game.from_record(position["record"])
        snapshot = game.snapshot()
        if (
            game.record() != position["record"]
            or snapshot["finished"]
            or snapshot["side"] != position["side"]
        ):
            raise ValueError("conversion fixture differs from Rust replay")
        features = encode_position(
            snapshot["board"], snapshot["hands"], snapshot["side"]
        )
        np.testing.assert_array_equal(features[0], game.features())
        result.append(
            {
                "name": position["name"],
                "side": snapshot["side"],
                "record": position["record"],
                "input": write_floats(
                    output, f"inputs/{position['name']}.f32", features
                ),
            }
        )
    return result


def _stamp(graph, binding, precision, conversion):
    properties = onnx_properties(
        binding["metadata"],
        precision=precision,
        weights_sha256=binding["weights_sha256"],
        export_source=binding["export_source_commit"],
        conversion=conversion,
    )
    retained = [
        (item.key, item.value)
        for item in graph.metadata_props
        if not item.key.startswith("voxelshogi.")
    ]
    del graph.metadata_props[:]
    for key, value in [*retained, *properties.items()]:
        graph.metadata_props.add(key=key, value=value)
    return graph


def _fp32(network, output, fixtures, binding):
    import numpy as np
    import onnx
    import torch

    from export.contract import compare_outputs
    from export.generate import write_floats
    from export.numeric import TRAINED_NUMERIC_CONTRACT
    from training.research_onnx import _open

    sample = np.fromfile(output / fixtures[0]["input"]["path"], dtype="<f4").reshape(
        1, 729, 43
    )
    path = output / "fp32.onnx"
    torch.onnx.export(
        network,
        (torch.from_numpy(sample),),
        path,
        input_names=["features"],
        output_names=["policy", "value"],
        dynamo=True,
        opset_version=18,
        external_data=False,
    )
    graph = _stamp(
        onnx.load(str(path), load_external_data=False), binding, "fp32", None
    )
    onnx.checker.check_model(graph, full_check=True)
    onnx.save(graph, str(path))
    session, references, comparison = _open(path, "fp32"), {}, {}
    with torch.inference_mode():
        for fixture in fixtures:
            name = fixture["name"]
            values = np.fromfile(
                output / fixture["input"]["path"], dtype="<f4"
            ).reshape(1, 729, 43)
            expected = network(torch.from_numpy(values.copy()))
            observed = session.run(["policy", "value"], {"features": values})
            references[name], comparison[name] = {}, {}
            for label, target, actual in zip(
                ("policy", "value"), expected, observed, strict=True
            ):
                comparison[name][label] = compare_outputs(
                    target.numpy(),
                    actual,
                    output=label,
                    numeric_contract=TRAINED_NUMERIC_CONTRACT,
                )
                references[name][label] = write_floats(
                    output, f"reference/fp32/{name}-{label}.f32", actual
                )
    return {
        "id": "fp32",
        "precision": "fp32",
        "model": _descriptor(output, path),
        "references": references,
        "torchComparison": comparison,
    }


def _variant(precision, output, fixtures, base, binding):
    import onnx

    from export.generate import low_precision_variant
    from export.variants import make_fp16_weights, make_int8

    if precision not in ("fp16", "int8"):
        raise ValueError("explicit converted format required")
    source = onnx.load(str(output / "fp32.onnx"), load_external_data=False)

    def convert(graph):
        converted, settings = (make_fp16_weights if precision == "fp16" else make_int8)(
            graph
        )
        return _stamp(converted, binding, precision, settings), settings

    return low_precision_variant(
        output, source, fixtures, base["references"], precision, convert
    )


def _verify(output, result):
    from training.research_onnx import _inspect

    model = result["model"]
    if [f["name"] for f in model["fixtures"]] != list(NAMES) or [
        v["precision"] for v in model["variants"]
    ] != ["fp32", "fp16", "int8"]:
        raise ValueError("complete fixed conversion inventory required")
    files = [model["checkpoint"], model["research"]["selection"], result["history"]]
    for fixture in model["fixtures"]:
        if fixture["input"]["bytes"] != 125388:
            raise ValueError("conversion feature byte count differs")
        files.append(fixture["input"])
    for variant in model["variants"]:
        binding = _inspect(output / variant["model"]["path"])
        if (
            binding["precision"] != variant["precision"]
            or binding["weights_sha256"] != model["checkpoint"]["sha256"]
            or binding["export_source_commit"] != model["sourceCommit"]
            or binding["metadata"] != result["weight_metadata"]
        ):
            raise ValueError("converted graph metadata differs from selected weights")
        files.append(variant["model"])
        if set(variant["references"]) != set(NAMES):
            raise ValueError("conversion references incomplete")
        for pair in variant["references"].values():
            if pair["policy"]["bytes"] != 4271940 or pair["value"]["bytes"] != 4:
                raise ValueError("conversion reference byte count differs")
            files.extend((pair["policy"], pair["value"]))
    if len({f["path"] for f in files}) != len(files):
        raise ValueError("conversion artifact paths overlap")
    for f in files:
        path = output / f["path"]
        if path.is_symlink() or not path.is_file() or _descriptor(output, path) != f:
            raise ValueError("conversion artifact bytes/hash changed")


def _bounded(path, maximum):
    path = Path(path)
    if (
        path.is_symlink()
        or not path.is_file()
        or not 0 < path.stat().st_size <= maximum
    ):
        raise ValueError("bounded regular conversion input required")
    return path.read_bytes()


def generate(
    selected,
    history,
    output,
    *,
    selection_sha256,
    expected_source,
    deadline,
    clock=time.time,
    stop_requested=lambda: False,
    ports=None,
):
    if sys.platform != "linux":
        raise ValueError("M model conversion requires external Linux")
    if (
        type(deadline) not in (int, float)
        or not math.isfinite(deadline)
        or clock() >= deadline
        or stop_requested()
    ):
        raise InterruptedError("fixed conversion deadline")
    ports = (
        {
            "source": source_commit,
            "load": _load,
            "fixtures": _fixtures,
            "fp32": _fp32,
            "variant": _variant,
            "verify": _verify,
        }
        if ports is None
        else ports
    )
    if (
        set(ports) != {"source", "load", "fixtures", "fp32", "variant", "verify"}
        or not _sha(expected_source, 40)
        or ports["source"]() != expected_source
    ):
        raise ValueError("conversion requires the clean frozen export source")
    selected, output = Path(selected), Path(output)
    if selected.is_symlink() or not selected.is_dir():
        raise ValueError("regular selected weight folder required")
    selection_raw = _bounded(selected / "selection.json", 1024**2)
    if (
        not _sha(selection_sha256)
        or hashlib.sha256(selection_raw).hexdigest() != selection_sha256
    ):
        raise ValueError("frozen selection receipt hash differs")
    selection = json.loads(selection_raw, object_pairs_hook=_unique_object)
    history_raw = _bounded(history, 64 * 1024**2)
    review = review_inputs(selection, history_raw)
    weights = selected / "model.safetensors"
    if (
        weights.is_symlink()
        or not weights.is_file()
        or weights.stat().st_size != selection["weights"]["bytes"]
        or file_hash(weights) != review["weights_sha256"]
        or research_metadata(weights) != review["metadata"]
    ):
        raise ValueError("selected weight bytes/header differ")
    if output.exists() or output.is_symlink():
        raise FileExistsError("conversion output must be fresh")

    def stopping():
        if clock() >= deadline or stop_requested():
            raise InterruptedError("fixed conversion deadline")

    stopping()
    network, metadata = ports["load"](weights, review["weights_sha256"])
    if metadata != review["metadata"]:
        raise ValueError("loaded M structure/selection differs")
    stopping()
    output.mkdir(parents=True, exist_ok=False)
    stage = "copy-selected-inputs"
    try:
        atomic_json(
            output / "request.json",
            {
                "source_commit": expected_source,
                "selection_sha256": selection_sha256,
                "deadline": deadline,
            },
        )
        shutil.copyfile(weights, output / "model.safetensors")
        (output / "selection.json").write_bytes(selection_raw)
        (output / "training-history.jsonl").write_bytes(history_raw)
        stage = "fixtures"
        fixtures = ports["fixtures"](output)
        binding = {**review, "export_source_commit": expected_source}
        stage = "fp32"
        stopping()
        base = ports["fp32"](network, output, fixtures, binding)
        variants = [base]
        for precision in ("fp16", "int8"):
            stage = precision
            stopping()
            variants.append(
                ports["variant"](precision, output, fixtures, base, binding)
            )
        model = {
            "schema": 1,
            "id": f"voxelshogi-transformer-m-{metadata['architecture']['architecture']}-{metadata['seed']}-{metadata['training_binding_sha256'][:12]}",
            "trained": True,
            "license": "Apache-2.0",
            "numericContract": "voxelshogi-trained-numeric-v1",
            "inputSchema": "voxelshogi-standard-features-v1",
            "ruleset": "voxelshogi-standard-v1",
            "sourceCommit": expected_source,
            "sourceDirty": False,
            "seed": metadata["seed"],
            "parameters": parameter_count(ResearchConfig(**metadata["architecture"])),
            "inputs": {"features": {"shape": [1, 729, 43], "dtype": "float32"}},
            "outputs": {
                "policy": {"shape": [1, 1067985], "dtype": "float32"},
                "value": {"shape": [1, 1], "dtype": "float32"},
            },
            "checkpoint": _descriptor(output, output / "model.safetensors"),
            "fixtures": fixtures,
            "variants": variants,
            "research": {
                "schema": "voxelshogi-research-inference-v1",
                "architecture": metadata["architecture"],
                "trainingSourceCommit": metadata["source_commit"],
                "trainingBindingSha256": metadata["training_binding_sha256"],
                "selectedUpdate": metadata["step"],
                "totalUpdates": review["total_updates"],
                "selection": _descriptor(output, output / "selection.json"),
            },
        }
        result = {
            "schema": "voxelshogi-research-conversion-v1",
            "conversion_complete": True,
            "inference_publication_approved": False,
            "weight_metadata": metadata,
            "model": model,
            "history": _descriptor(output, output / "training-history.jsonl"),
        }
        stage = "verify"
        stopping()
        ports["verify"](output, result)
        if (
            ports["source"]() != expected_source
            or file_hash(weights) != review["weights_sha256"]
            or (selected / "selection.json").read_bytes() != selection_raw
            or Path(history).read_bytes() != history_raw
        ):
            raise ValueError("conversion source/input bytes changed")
        stopping()
        atomic_json(output / "conversion.json", result)
        return result
    except Exception as error:
        atomic_json(
            output / "failure.json",
            {"complete": False, "stage": stage, "error_type": type(error).__name__},
        )
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("selected", type=Path)
    parser.add_argument("history", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--selection-sha256", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--deadline", type=float, required=True)
    args = parser.parse_args()
    generate(
        args.selected,
        args.history,
        args.output,
        selection_sha256=args.selection_sha256,
        expected_source=args.source,
        deadline=args.deadline,
    )


if __name__ == "__main__":
    main()
