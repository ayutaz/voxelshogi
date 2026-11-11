"""Linux-only pilot result dataset; exact JSON bytes, no checkpoint/data relay."""

import json
import math
import sys
import time
from pathlib import Path

from training.checkpoint import atomic_json
from training.evaluation_v2 import fingerprint
from training.feature_cache import file_hash
from training.hub_release import plan_release, publish_release, verify_release

REPO = "voxelshogi/voxelshogi-research-pilot-results-v1"
MAX_SOURCE_BYTES = 64 * 1024**2
MAX_TOTAL_BYTES = 128 * 1024**2
MAX_PARQUET_BYTES = 64 * 1024**2


def read_owned(path):
    path = Path(path)
    if (
        any(p.is_symlink() for p in (path, *path.parents))
        or not path.is_file()
        or path.stat().st_size > MAX_SOURCE_BYTES
    ):
        raise ValueError("bounded regular result file and parents required")
    data = path.read_bytes()
    if len(data) > MAX_SOURCE_BYTES:
        raise ValueError("result file grew beyond limit")
    return data


def finite_json(text):
    def reject(value):
        raise ValueError("nonfinite JSON result")

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("overflowing JSON result")
        return number

    return json.loads(text, parse_constant=reject, parse_float=finite_float)


def declared_paths(value):
    names = [
        "workflow-request.json",
        "workflow-compute.json",
        "state-budget-final.json",
        "workflow-failure.json",
        "job-failure.json",
        "training-complete.json",
        "cuda-preflight.json",
        "m4-input-receipt.json",
        "resource-samples.json",
    ]
    names += [
        n + "-input-receipt.json"
        for n in ("selfplay", "protection", "screen", "diagnosis")
    ]
    for architecture in ("full", "geometry"):
        names += [
            architecture + "/" + name
            for name in (
                "inputs.json",
                "complete.json",
                "failure.json",
                "resume-proof.json",
                "failure-rescue-result.json",
                "diagnostics/request.json",
                "diagnostics/complete.json",
                "diagnostics/failure.json",
                "diagnostics/selected/selection.json",
            )
        ]
        for run in ("continuous", "interrupted", "restored"):
            names += [
                f"{architecture}/{run}/{n}"
                for n in ("run.json", "events.jsonl", "attempt-wrapper.json")
            ]
        for stage in ("intermediate", "final"):
            names += [
                f"{architecture}/{stage}-transfer/{n}.json"
                for n in (
                    "publication-plan",
                    "publication-receipt",
                    "complete",
                    "failure",
                )
            ]
    names += [
        "development/" + n
        for n in ("complete.json", "failure.json", "input-audit.json", "queries.jsonl")
    ]
    for architecture in ("full", "geometry"):
        names += [
            f"development/{architecture}/{n}.json"
            for n in ("protocol", "run", "summary")
        ]
        names += [
            f"development/{architecture}/{case['id']}-{side}.json"
            for case in value["development"]["protocol"]["cases"]
            for side in ("b", "w")
        ]
    return names


def write_records(rows, target):
    """Real PyArrow byte/schema roundtrip is exercised on Linux, never Mac."""
    if sys.platform != "linux":
        raise ValueError("result Parquet requires external Linux")
    import pyarrow as pa
    import pyarrow.parquet as pq

    schema = pa.schema(
        [
            (k, pa.int64() if k == "line" else pa.string())
            for k in ("path", "line", "content", "sha256")
        ],
        metadata={b"schema": b"voxelshogi-research-pilot-records-v1"},
    )
    table = pa.Table.from_pylist(rows, schema=schema)
    pq.write_table(table, target, compression="zstd")
    if not pq.read_table(target).equals(table, check_metadata=True):
        raise ValueError("result Parquet byte/schema roundtrip differs")


def build_results(value, base, output, *, pipeline_complete, writer=None):
    if sys.platform != "linux":
        raise ValueError("pilot results require external Linux")
    from infrastructure.research.pilot.workflow import validate_workflow

    validate_workflow(value, now=value["job"]["compute_deadline"] - 1)
    base, output = Path(base), Path(output)
    if (
        base.absolute() != Path(value["job"]["base"]).absolute()
        or base.is_symlink()
        or output.exists()
        or output.is_symlink()
    ):
        raise ValueError("fresh publication and frozen owned result root required")
    request = finite_json(read_owned(base / "workflow-request.json").decode())
    compute = finite_json(read_owned(base / "workflow-compute.json").decode())
    if (
        request["workflow_sha256"] != fingerprint(value)
        or compute["pipeline_complete"] is not pipeline_complete
        or compute["source_commit"] != value["job"]["source_commit"]
    ):
        raise ValueError("workflow result/freeze differs")
    mandatory = {
        "workflow-request.json",
        "workflow-compute.json",
        "state-budget-final.json",
    }
    if pipeline_complete:
        mandatory.update(
            {
                "training-complete.json",
                "development/complete.json",
                "development/input-audit.json",
                "development/queries.jsonl",
            }
        )
        for name in ("full", "geometry"):
            mandatory.update(
                {
                    name + "/complete.json",
                    name + "/resume-proof.json",
                    name + "/diagnostics/complete.json",
                    name + "/diagnostics/selected/selection.json",
                }
            )
            for run in ("continuous", "interrupted", "restored"):
                mandatory.update(
                    {f"{name}/{run}/run.json", f"{name}/{run}/events.jsonl"}
                )
            for stage in ("intermediate", "final"):
                mandatory.update(
                    {
                        f"{name}/{stage}-transfer/complete.json",
                        f"{name}/{stage}-transfer/publication-plan.json",
                        f"{name}/{stage}-transfer/publication-receipt.json",
                    }
                )
            mandatory.update(
                {f"development/{name}/{n}.json" for n in ("protocol", "run", "summary")}
            )
            mandatory.update(
                f"development/{name}/{case['id']}-{side}.json"
                for case in value["development"]["protocol"]["cases"]
                for side in ("b", "w")
            )
    rows, inventory, consumed, completed = [], [], 0, 0
    for name in declared_paths(value):
        path = base / name
        if not path.exists() and not path.is_symlink():
            if name in mandatory:
                raise ValueError("missing mandatory result evidence: " + name)
            continue
        data = read_owned(path)
        consumed += len(data)
        if consumed > MAX_TOTAL_BYTES:
            raise ValueError("result evidence exceeds total bound")
        text = data.decode("utf-8")
        if name in {"full/complete.json", "geometry/complete.json"}:
            cycle = finite_json(text)
            architecture = name.split("/")[0]
            inputs = next(
                i
                for i in value["job"]["inputs"]
                if i["config"]["architecture"]["architecture"] == architecture
            )
            if (
                cycle.get("source_commit") == value["job"]["source_commit"]
                and cycle.get("architecture") == architecture
                and cycle.get("inputs_sha256") == fingerprint(inputs)
                and cycle.get("scientific_pilots") == 1
                and cycle.get("additional_independent_seeds") == 0
                and cycle.get("resume_proof", {}).get("verified") is True
                and all(
                    cycle.get(stage + "_transfer", {})
                    .get("receipt", {})
                    .get("verified")
                    is True
                    and cycle[stage + "_transfer"].get("restored") is True
                    for stage in ("intermediate", "final")
                )
            ):
                completed += 1
        contents = (
            [line.decode("utf-8") for line in data.splitlines(keepends=True)]
            if name.endswith(".jsonl")
            else [text]
        )
        for number, content in enumerate(contents):
            if len(content.encode()) > 1024**2 and name.endswith(".jsonl"):
                raise ValueError("result JSONL row exceeds bound")
            finite_json(content)
            rows.append(
                {
                    "path": name,
                    "line": number if name.endswith(".jsonl") else -1,
                    "content": content,
                    "sha256": fingerprint_bytes(content.encode()),
                }
            )
        inventory.append(
            {
                "path": name,
                "bytes": len(data),
                "sha256": fingerprint_bytes(data),
                "records": len(contents),
            }
        )
        if len(rows) > 200_000:
            raise ValueError("too many result records")
    if pipeline_complete:
        from infrastructure.research.pilot.results_evidence import (
            verify_complete_evidence,
        )

        verify_complete_evidence(value, base, compute)
    license_path = base / "input-m4/LICENSE"
    license_bytes = read_owned(license_path)
    entry = next(
        e for e in value["m4_bundle"]["plan"]["files"] if e["path"] == "LICENSE"
    )
    if (
        value["m4_bundle"]["plan"]["license"] != "cc-by-4.0"
        or len(license_bytes) != entry["bytes"]
        or fingerprint_bytes(license_bytes) != entry["sha256"]
    ):
        raise ValueError("fixed approved CC-BY-4.0 license bytes differ")
    output.mkdir(parents=True, exist_ok=False)
    (write_records if writer is None else writer)(rows, output / "records.parquet")
    if not 0 < (output / "records.parquet").stat().st_size <= MAX_PARQUET_BYTES:
        raise ValueError("result Parquet size exceeds publication limit")
    for entry in inventory:
        if file_hash(base / entry["path"]) != entry["sha256"]:
            raise ValueError("source evidence changed during result packing")
    manifest = {
        "schema": "voxelshogi-research-pilot-results-v1",
        "source_commit": value["job"]["source_commit"],
        "workflow_sha256": fingerprint(value),
        "pipeline_complete": pipeline_complete,
        "scientific_pilots_completed": completed,
        "record_count": len(rows),
        "files": inventory,
        "records_parquet_sha256": file_hash(output / "records.parquet"),
        "final_holdout_evaluated": False,
        "general_strength_improvement_established": False,
    }
    refs = {
        k: {n: v["receipt"][n] for n in ("repo_id", "hub_commit", "release_sha256")}
        for k, v in {**value["job"]["input_bundles"], "m4": value["m4_bundle"]}.items()
    }
    atomic_json(
        output / "config.json",
        {
            "schema": manifest["schema"],
            "source_commit": manifest["source_commit"],
            "workflow_sha256": manifest["workflow_sha256"],
            "inputs": refs,
            "configs": [i["config"] for i in value["job"]["inputs"]],
            "development_sha256": value["development_sha256"],
            "split_step": value["job"]["split_step"],
        },
    )
    atomic_json(output / "manifest.json", manifest)
    atomic_json(
        output / "validation.json",
        {
            "source_bytes_rechecked": True,
            "finite_json": True,
            "records": len(rows),
            "pipeline_complete": pipeline_complete,
            "final_holdout_evaluated": False,
        },
    )
    (output / "LICENSE").write_bytes(license_bytes)
    (output / "NOTICE").write_text(
        "VoxelShogi synthetic research measurements, CC-BY-4.0, VoxelShogi contributors. Code: Apache-2.0. Retain source and immutable input references.\n"
    )
    (output / "README.md").write_text(
        "---\nlicense: cc-by-4.0\nconfigs:\n- config_name: records\n  data_files:\n  - split: records\n    path: records.parquet\n---\n# VoxelShogi M pilot results\n\n"
        "## Generation and provenance\n"
        f"Source `{manifest['source_commit']}`, workflow `{manifest['workflow_sha256']}`. Pipeline complete: {pipeline_complete}. Completed scientific pilot cycles: {manifest['scientific_pilots_completed']}; {len(rows)} actual JSON document/line records from {len(inventory)} declared files. Full and Geometry share the frozen seed/data/update schedule in config.json. Exact fixed HF input revisions and release hashes are in that config. A replayed CUDA trajectory is not an independent seed. No raw source corpus or checkpoint weights are included.\n\n"
        "## Usage and schema\n"
        "Load `datasets.load_dataset('voxelshogi/voxelshogi-research-pilot-results-v1', 'records', revision='<verified Hub commit>', split='records')` after manual access approval. Columns: path (owned relative source path), line (-1 for one whole JSON document; zero-based for JSONL), content (exact UTF-8 text including newline), sha256 (content bytes). Concatenate JSONL rows by line to reconstruct each file; verify inventory bytes/hash in manifest.json, including empty files. The records split is an evidence table, not a position-level train/val/test split.\n\n"
        "## Verification\n"
        "Parquet is roundtripped with its explicit schema on external Linux. Every source file is rehashed after packing. Publication verifies all declared output files at one immutable HF revision. Complete results additionally bind both selected-best diagnostics, full CUDA resume proofs and the replayed48-game/NN-query audit; partial/failed results do not establish success. Val diagnostics measure terminal/bootstrap teacher reproduction separately; bootstrap is not an observed game outcome. Small correlated development cohorts and cutoff bounds do not establish general strength. Final12 holdout roots are not evaluated or used for selection. Independent seeds, main architecture comparison, quantized inference and physical mobile play are outside this pilot. Resource samples stop before publication; final shutdown observations belong to the controller record.\n\n"
        "## Access and license\n"
        "Public repository, manual download approval, Community disabled. Synthetic result evidence: CC-BY-4.0, VoxelShogi contributors; retain LICENSE, NOTICE and source/input hashes. Code: Apache-2.0. Failed/partial measurements remain labeled. Data/checkpoints stay on external Linux and HF; Mac receives only small summaries and ledgers.\n"
    )
    return manifest


def fingerprint_bytes(data):
    import hashlib

    return hashlib.sha256(data).hexdigest()


def publish_results(
    value, base, *, pipeline_complete, api, fetch, deadline, clock=time.time
):
    if sys.platform != "linux":
        raise ValueError("result publication requires external Linux")
    from infrastructure.research.pilot import job

    base = Path(base)
    control = base / "results-transfer"
    control.mkdir(parents=True, exist_ok=False)
    atomic_json(
        control / "publication-attempt.json",
        {"workflow_sha256": fingerprint(value), "at": clock()},
    )
    try:
        if clock() >= deadline:
            raise InterruptedError("fixed results publication deadline")
        job.check_source(value["job"]["source_commit"])
        output = base / "publication"
        manifest = build_results(
            value, base, output, pipeline_complete=pipeline_complete
        )
        plan = plan_release(
            output,
            repo_id=REPO,
            repo_type="dataset",
            license_id="cc-by-4.0",
            license_approved=True,
            source_commit=value["job"]["source_commit"],
        )
        atomic_json(control / "publication-plan.json", plan)
        if clock() >= deadline:
            raise InterruptedError("fixed results upload deadline")
        receipt = publish_release(output, plan, api, execute=True, system="linux")
        atomic_json(control / "publication-receipt.json", receipt)

        def fixed_fetch(**kwargs):
            if clock() >= deadline:
                raise InterruptedError("fixed results all-file deadline")
            if (
                kwargs["repo_id"] != REPO
                or kwargs["repo_type"] != "dataset"
                or kwargs["revision"] != receipt["hub_commit"]
            ):
                raise ValueError("result fetch escaped fixed release")
            return fetch(**kwargs)

        receipt = verify_release(plan, receipt, api, fixed_fetch, system="linux")
        if clock() >= deadline:
            raise InterruptedError("fixed results verification deadline")
        atomic_json(control / "publication-receipt.json", receipt)
        result = {
            "receipt": receipt,
            "pipeline_complete": pipeline_complete,
            "record_count": manifest["record_count"],
            "release_sha256": fingerprint(plan),
        }
        atomic_json(control / "complete.json", result)
        return result
    except BaseException as error:
        atomic_json(
            control / "failure.json",
            {"error_type": type(error).__name__, "verified": False},
        )
        raise
