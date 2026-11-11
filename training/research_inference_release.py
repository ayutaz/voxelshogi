"""Typed M inference inventory from selected training and per-format evidence.

This is metadata/publication validation, not a substitute for Linux model
conversion, Rust replay, or the actual all-input audit that produces the files.
"""

import hashlib
import json
import math
import re
from copy import deepcopy
from pathlib import Path

from export.research_contract import ResearchConfig, parameter_count
from export.research_generate import review_inputs
from training.evaluation_v2 import fingerprint, validate_match_rows, validate_protocol
from training.evaluation_v2_runner import rust_policy_identity
from training.feature_cache import file_hash
from training.research_screen import screen_definitions
from training.research_weights import _unique_object

ROLE = "research-inference-package"
NAMES = ("initial-b", "after-one-w", "mate-in-one-b", "material-b")
PRECISIONS = ("fp32", "fp16", "int8")
MODEL_BYTES = 512 * 1024**2
METADATA_BYTES = 1024**2


def _hash(value, length=64):
    return (
        isinstance(value, str)
        and re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is not None
    )


def _integer(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def _descriptor(value, wanted, maximum, size=None):
    if (
        type(value) is not dict
        or set(value) != {"path", "bytes", "sha256"}
        or value["path"] != wanted
        or not _integer(value["bytes"], 1, maximum)
        or (size is not None and value["bytes"] != size)
        or not _hash(value["sha256"])
    ):
        raise ValueError("invalid M inference descriptor")
    return deepcopy(value)


def final_protocol(frozen, *, model_sha256, evaluation_source):
    """Rebind only runtime identities in the preregistered final cohort."""
    if not _hash(model_sha256) or not _hash(evaluation_source, 40):
        raise ValueError("immutable final evaluation identities required")
    p = deepcopy(frozen["protocol"])
    validate_protocol(p)
    definitions = screen_definitions("holdout")
    roots = frozen["roots"]
    if (
        p["purpose"] != "holdout"
        or len(p["cases"]) != 12
        or p["search_limits"]
        != {"max_depth": 3, "max_nodes": 20000, "table_capacity": 4096}
        or p["sensitivity"] != {"minimum_pairs": 12, "minimum_termination_rate": 0.25}
        or set(roots) != {c["id"] for c in p["cases"]}
    ):
        raise ValueError("fixed final12 roots, limits and sensitivity required")
    for case, definition in zip(p["cases"], definitions, strict=True):
        if {k: v for k, v in case.items() if k != "opening"} != {
            k: v for k, v in definition["case"].items() if k != "opening"
        }:
            raise ValueError("fixed final case identity differs")
        root = roots[case["id"]]
        if (
            set(root) != {"purpose", "position", "input"}
            or root["purpose"] != "holdout"
            or not _hash(root["position"])
            or not _hash(root["input"])
        ):
            raise ValueError("final root identities are incomplete")
    if (
        len({r["input"] for r in roots.values()}) != 12
        or len({r["position"] for r in roots.values()}) != 12
    ):
        raise ValueError("final root identities must be distinct")
    p["source_commit"] = evaluation_source
    p["participants"] = {
        "model": {
            "artifact_sha256": model_sha256,
            "backend": "ort-cpu",
            "policy": "legal-argmax-v1",
        },
        "opponent": {
            "artifact_sha256": rust_policy_identity(
                "alphabeta-v1", evaluation_source, p["search_limits"]
            ),
            "backend": "rust",
            "policy": "alphabeta-v1",
        },
    }
    validate_protocol(p)
    return p


def review_manifest(
    manifest, *, source_commit, selection, history, frozen, reports, audit
):
    """Return an exact typed inventory without reading model/tensor payloads."""
    try:
        review = review_inputs(selection, history)
        metadata, r = review["metadata"], manifest["research"]
        config = ResearchConfig(**metadata["architecture"])
        if (
            not _hash(source_commit, 40)
            or type(manifest["schema"]) is not int
            or manifest["schema"] != 1
            or manifest["trained"] is not True
            or manifest["sourceDirty"] is not False
            or manifest["sourceCommit"] != source_commit
            or "ciFixture" in manifest
            or manifest["license"] != "Apache-2.0"
            or not isinstance(manifest["id"], str)
            or re.fullmatch(r"[a-zA-Z0-9._-]{1,128}", manifest["id"]) is None
            or type(manifest["seed"]) is not int
            or manifest["seed"] != metadata["seed"]
            or type(manifest["parameters"]) is not int
            or manifest["parameters"] != parameter_count(config)
            or manifest["numericContract"] != "voxelshogi-trained-numeric-v1"
            or manifest["inputSchema"] != "voxelshogi-standard-features-v1"
            or manifest["ruleset"] != "voxelshogi-standard-v1"
            or manifest["inputs"]
            != {"features": {"shape": [1, 729, 43], "dtype": "float32"}}
            or manifest["outputs"]
            != {
                "policy": {"shape": [1, 1067985], "dtype": "float32"},
                "value": {"shape": [1, 1], "dtype": "float32"},
            }
        ):
            raise ValueError(
                "fixed trained M identity, source or tensor contract differs"
            )
        for group in (manifest["inputs"], manifest["outputs"]):
            if any(
                type(n) is not int for tensor in group.values() for n in tensor["shape"]
            ):
                raise ValueError("M tensor dimensions must be integers")
        if (
            r["schema"] != "voxelshogi-research-inference-v1"
            or r["architecture"] != metadata["architecture"]
            or r["trainingSourceCommit"] != metadata["source_commit"]
            or r["trainingBindingSha256"] != metadata["training_binding_sha256"]
            or type(r["selectedUpdate"]) is not int
            or r["selectedUpdate"] != metadata["step"]
            or type(r["totalUpdates"]) is not int
            or r["totalUpdates"] != review["total_updates"]
            or r["evaluationProtocolSha256"] != fingerprint(frozen["protocol"])
            or r["finalRootsSha256"] != fingerprint(frozen["roots"])
        ):
            raise ValueError("M training, selection or final cohort provenance differs")
        expected = {name: None for name in ["README.md", "LICENSE", "manifest.json"]}

        def include(value, path, maximum=METADATA_BYTES, size=None):
            expected[path] = _descriptor(value, path, maximum, size)

        include(manifest["checkpoint"], "model.safetensors", MODEL_BYTES)
        if manifest["checkpoint"] != {
            k: selection["weights"][k] for k in ["path", "bytes", "sha256"]
        }:
            raise ValueError("M checkpoint differs from selected original weights")
        include(r["selection"], "selection.json")
        include(r["history"], "training-history.jsonl", 64 * 1024**2, len(history))
        if r["history"]["sha256"] != hashlib.sha256(history).hexdigest():
            raise ValueError("complete original history differs")
        include(r["finalProtocol"], "final-protocol.json")
        include(r["inputAudit"], "input-audit.json")
        if [f["name"] for f in manifest["fixtures"]] != list(NAMES):
            raise ValueError("all four fixed M fixtures required")
        fixed_fixtures = json.loads(
            (
                Path(__file__).resolve().parents[1] / "export/fixtures/positions.json"
            ).read_text()
        )
        for i, fixture in enumerate(manifest["fixtures"]):
            if (
                fixture["side"] != ("w" if i == 1 else "b")
                or fixture["record"]["ruleset_id"] != manifest["ruleset"]
                or fixture["record"] != fixed_fixtures[i]["record"]
            ):
                raise ValueError("fixed M fixture identity differs")
            include(fixture["input"], f"inputs/{fixture['name']}.f32", 125388, 125388)
        variants = manifest["variants"]
        if (
            [v["precision"] for v in variants] != list(PRECISIONS)
            or set(reports) != set(PRECISIONS)
            or len({v["model"]["sha256"] for v in variants}) != 3
        ):
            raise ValueError("three actual M formats and separate reports required")
        if (
            audit["schema"] != "voxelshogi-generation-input-audit-v1"
            or audit["passed"] is not True
            or set(audit["runs"]) != set(PRECISIONS)
            or set(audit["observed_input_counts"])
            != {f"neural-query/{p}/model" for p in PRECISIONS}
        ):
            raise ValueError("all-format actual neural-input audit required")
        evaluation_sources = set()
        for variant in variants:
            precision = variant["precision"]
            if variant["id"] != precision:
                raise ValueError("M variant identity differs")
            include(variant["model"], precision + ".onnx", MODEL_BYTES)
            if precision == "fp32":
                if "conversion" in variant:
                    raise ValueError("M FP32 must remain unconverted")
            else:
                c = variant["conversion"]
                fp16 = precision == "fp16"
                tensors = c["convertedTensors" if fp16 else "quantizedTensors"]
                elements = c["convertedElements" if fp16 else "quantizedElements"]
                if (
                    c["method"]
                    != (
                        "fp16-weight-only"
                        if fp16
                        else "symmetric-per-tensor-weight-only-int8"
                    )
                    or c["compute"] != "float32"
                    or c["activations"] != "float32"
                    or not _integer(tensors, 1, manifest["parameters"])
                    or not _integer(elements, tensors, manifest["parameters"])
                ):
                    raise ValueError("evidenced M weight-only conversion required")
                differences = variant["fp32Difference"]
                if set(differences) != set(NAMES):
                    raise ValueError("all M conversion differences required")
                for outputs in differences.values():
                    if set(outputs) != {"policy", "value"}:
                        raise ValueError("complete M difference outputs required")
                    for output, stats in outputs.items():
                        if (
                            type(stats["elements"]) is not int
                            or stats["elements"]
                            != (1067985 if output == "policy" else 1)
                            or type(stats["argmaxEqual"]) is not bool
                            or any(
                                type(stats[k]) not in (int, float)
                                or not math.isfinite(stats[k])
                                or stats[k] < 0
                                for k in ["maxAbs", "mae", "rmse", "maxRelative"]
                            )
                        ):
                            raise ValueError("invalid M numeric differences")
            refs = variant["references"]
            if set(refs) != set(NAMES):
                raise ValueError("all M reference fixtures required")
            for name, pair in refs.items():
                if set(pair) != {"policy", "value"}:
                    raise ValueError("complete M reference outputs required")
                for output in ["policy", "value"]:
                    size = 4271940 if output == "policy" else 4
                    include(
                        pair[output],
                        f"reference/{precision}/{name}-{output}.f32",
                        size,
                        size,
                    )
            e = variant["evaluation"]
            report = reports[precision]
            if (
                e["scope"] != "final-holdout-v1"
                or e["complete"] is not True
                or type(e["gameCount"]) is not int
                or e["gameCount"] != 24
                or e["modelSha256"] != variant["model"]["sha256"]
                or e["weightsSha256"] != manifest["checkpoint"]["sha256"]
            ):
                raise ValueError("actual M format final evaluation binding differs")
            include(e["report"], f"evaluation/{precision}.json")
            if (
                report["schema"] != "voxelshogi-research-format-evaluation-v1"
                or report["complete"] is not True
                or report["precision"] != precision
                or report["model_sha256"] != variant["model"]["sha256"]
                or report["weights_sha256"] != manifest["checkpoint"]["sha256"]
                or not _integer(report["actual_neural_queries"], 1, 2**63 - 1)
                or not _hash(report["run_sha256"])
            ):
                raise ValueError("M format report is incomplete or unbound")
            p = final_protocol(
                frozen,
                model_sha256=variant["model"]["sha256"],
                evaluation_source=report["evaluation_source_commit"],
            )
            if (
                report["protocol"] != p
                or len(validate_match_rows(report["games"], p)) != 24
            ):
                raise ValueError("M final24 cohort differs")
            evaluation_sources.add(report["evaluation_source_commit"])
            if audit["runs"][precision] != {
                "games": 24,
                "run_sha256": report["run_sha256"],
                "protocol_sha256": fingerprint(p),
            }:
                raise ValueError("M input audit run/protocol differs")
            observed = audit["observed_input_counts"][f"neural-query/{precision}/model"]
            if set(observed) != {"positions", "inputs"} or any(
                not _integer(v, 1, report["actual_neural_queries"])
                for v in observed.values()
            ):
                raise ValueError("M actual neural query counts differ")
        if len(evaluation_sources) != 1:
            raise ValueError("M format evaluation sources must match")
        return expected
    except (KeyError, TypeError, AttributeError, IndexError, OverflowError) as error:
        raise ValueError("incomplete M inference metadata") from error


def _read(folder, descriptor, wanted, maximum=METADATA_BYTES):
    _descriptor(descriptor, wanted, maximum)
    path = folder / wanted
    if folder.is_symlink() or any(
        (folder / Path(*Path(wanted).parts[:i])).is_symlink()
        for i in range(1, len(Path(wanted).parts))
    ):
        raise ValueError("M evidence parent must not be a symlink")
    if (
        path.is_symlink()
        or not path.is_file()
        or path.stat().st_size != descriptor["bytes"]
        or file_hash(path) != descriptor["sha256"]
    ):
        raise ValueError("M publication evidence bytes/hash differ")
    return path.read_bytes()


def research_inventory(folder, plan, card):
    """Called by the shared HF harness before hashing the whole typed package."""
    folder = Path(folder)
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("real M publication folder required")
    manifest_path = folder / "manifest.json"
    if (
        manifest_path.is_symlink()
        or not manifest_path.is_file()
        or not 0 < manifest_path.stat().st_size <= METADATA_BYTES
    ):
        raise ValueError("bounded M inference manifest required")
    try:
        manifest = json.loads(
            manifest_path.read_bytes(), object_pairs_hook=_unique_object
        )
        r = manifest["research"]

        def read(value, path, maximum=METADATA_BYTES):
            return json.loads(
                _read(folder, value, path, maximum), object_pairs_hook=_unique_object
            )

        selection = read(r["selection"], "selection.json")
        history = _read(folder, r["history"], "training-history.jsonl", 64 * 1024**2)
        frozen = read(r["finalProtocol"], "final-protocol.json")
        audit = read(r["inputAudit"], "input-audit.json")
        reports = {
            v["precision"]: read(
                v["evaluation"]["report"], f"evaluation/{v['precision']}.json"
            )
            for v in manifest["variants"]
        }
        expected = review_manifest(
            manifest,
            source_commit=plan["source_commit"],
            selection=selection,
            history=history,
            frozen=frozen,
            reports=reports,
            audit=audit,
        )
        architecture = r["architecture"]["architecture"]
        if (
            plan["repo_id"] != f"voxelshogi/voxelshogi-research-m-{architecture}-v1"
            or plan["license"] != "apache-2.0"
        ):
            raise ValueError("separate M inference repository and Apache-2.0 required")
        for title in [
            "Training and provenance",
            "Evaluation",
            "Inference",
            "Access and license",
        ]:
            section = re.search(
                rf"^## {re.escape(title)}[ \t]*\n(.*?)(?=^## |\Z)",
                card,
                re.MULTILINE | re.DOTALL,
            )
            if section is None or not section.group(1).strip():
                raise ValueError("complete M Model Card sections required")
        if (folder / "NOTICE").exists():
            expected["NOTICE"] = None
        for name in ["README.md", "LICENSE", "NOTICE"]:
            p = folder / name
            if p.exists() and (
                p.is_symlink() or not 0 < p.stat().st_size <= METADATA_BYTES
            ):
                raise ValueError("bounded M publication notice required")
        return expected
    except (KeyError, TypeError, AttributeError, json.JSONDecodeError) as error:
        raise ValueError("incomplete M inference package") from error


def catalog_release(folder, plan, receipt):
    """Enroll only a verified immutable M release, retaining the explicit profile."""
    from training.hub_release import plan_release

    if (
        plan.get("artifact_role") != ROLE
        or receipt.get("verified") is not True
        or receipt.get("community_disabled") is not True
        or receipt.get("dry_run") is not False
        or receipt.get("repo_id") != plan["repo_id"]
        or receipt.get("repo_type") != "model"
        or not _hash(receipt.get("hub_commit"), 40)
        or receipt.get("release_sha256") != fingerprint(plan)
    ):
        raise ValueError("M catalog requires a verified immutable inference release")
    current = plan_release(
        folder,
        repo_id=plan["repo_id"],
        repo_type=plan["repo_type"],
        license_id=plan["license"],
        license_approved=plan["license_approved"],
        source_commit=plan["source_commit"],
        artifact_role=ROLE,
    )
    if current != plan:
        raise ValueError("M catalog artifacts changed since verified release")
    files = {f["path"]: f for f in plan["files"]}
    manifest = json.loads(
        _read(Path(folder), files["manifest.json"], "manifest.json"),
        object_pairs_hook=_unique_object,
    )
    return {
        "approved": True,
        "id": manifest["id"],
        "license": manifest["license"],
        "sourceCommit": plan["source_commit"],
        "repo": plan["repo_id"],
        "revision": receipt["hub_commit"],
        "manifest": files["manifest.json"],
        "notices": [files[n] for n in ["README.md", "LICENSE", "NOTICE"] if n in files],
        "profile": "research-m-v1",
        "architecture": manifest["research"]["architecture"]["architecture"],
    }
