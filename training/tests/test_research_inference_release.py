"""Handwritten M publication metadata; no tensors, inference, or game execution."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from training.evaluation_v2 import fingerprint
from training.tests.test_evaluation_v2 import opening, protocol, rows
from training.tests.test_research_conversion import inputs

NAMES = ["initial-b", "after-one-w", "mate-in-one-b", "material-b"]
PRECISIONS = ["fp32", "fp16", "int8"]
SOURCE = "f" * 40


def fixture(tmp_path):
    from training.evaluation_v2_runner import rust_policy_identity

    _, history, selection = inputs(tmp_path)
    metadata = selection["weights"]["metadata"]

    def file(path, size=64):
        return {
            "path": path,
            "bytes": size,
            "sha256": hashlib.sha256(path.encode()).hexdigest(),
        }

    frozen = {"protocol": protocol(), "roots": {}}
    p = frozen["protocol"]
    p.update(purpose="holdout")
    p["cases"] = [
        {
            "id": f"final-seed-{65000 + i}",
            "stratum": "middlegame",
            "seed": 65000 + i,
            "max_additional_plies": 128,
            "opening": opening(f"opaque-final-{i}"),
        }
        for i in range(12)
    ]
    p["sensitivity"] = {"minimum_pairs": 12, "minimum_termination_rate": 0.25}
    frozen["roots"] = {
        c["id"]: {
            "purpose": "holdout",
            "position": hashlib.sha256((c["id"] + "p").encode()).hexdigest(),
            "input": hashlib.sha256((c["id"] + "i").encode()).hexdigest(),
        }
        for c in p["cases"]
    }
    variants, reports = [], {}
    audit = {
        "schema": "voxelshogi-generation-input-audit-v1",
        "passed": True,
        "runs": {},
        "observed_input_counts": {},
    }
    fixtures = json.loads(
        (
            Path(__file__).resolve().parents[2] / "export/fixtures/positions.json"
        ).read_text()
    )
    for precision in PRECISIONS:
        model = file(precision + ".onnx")
        spec = deepcopy(p)
        spec["source_commit"] = SOURCE
        spec["participants"] = {
            "model": {
                "artifact_sha256": model["sha256"],
                "backend": "ort-cpu",
                "policy": "legal-argmax-v1",
            },
            "opponent": {
                "artifact_sha256": rust_policy_identity(
                    "alphabeta-v1", SOURCE, p["search_limits"]
                ),
                "backend": "rust",
                "policy": "alphabeta-v1",
            },
        }
        games = rows(spec, (("win", "loss"),) * 12)
        for row in games:
            row["model_sha256"] = model["sha256"]
            row["opponent_sha256"] = spec["participants"]["opponent"]["artifact_sha256"]
        report = {
            "schema": "voxelshogi-research-format-evaluation-v1",
            "complete": True,
            "precision": precision,
            "evaluation_source_commit": SOURCE,
            "model_sha256": model["sha256"],
            "weights_sha256": selection["weights"]["sha256"],
            "protocol": spec,
            "games": games,
            "run_sha256": hashlib.sha256((precision + "run").encode()).hexdigest(),
            "actual_neural_queries": 24,
        }
        reports[precision] = report
        audit["runs"][precision] = {
            "games": 24,
            "run_sha256": report["run_sha256"],
            "protocol_sha256": fingerprint(spec),
        }
        audit["observed_input_counts"][f"neural-query/{precision}/model"] = {
            "positions": 24,
            "inputs": 24,
        }
        variant = {
            "id": precision,
            "precision": precision,
            "model": model,
            "references": {
                name: {
                    "policy": file(
                        f"reference/{precision}/{name}-policy.f32", 4_271_940
                    ),
                    "value": file(f"reference/{precision}/{name}-value.f32", 4),
                }
                for name in NAMES
            },
            "evaluation": {
                "scope": "final-holdout-v1",
                "complete": True,
                "gameCount": 24,
                "modelSha256": model["sha256"],
                "weightsSha256": selection["weights"]["sha256"],
                "report": file(f"evaluation/{precision}.json"),
            },
        }
        if precision != "fp32":
            variant["conversion"] = {
                "method": "fp16-weight-only"
                if precision == "fp16"
                else "symmetric-per-tensor-weight-only-int8",
                "compute": "float32",
                "activations": "float32",
                ("convertedTensors" if precision == "fp16" else "quantizedTensors"): 1,
                (
                    "convertedElements" if precision == "fp16" else "quantizedElements"
                ): 4,
            }
            variant["fp32Difference"] = {
                name: {
                    output: {
                        "elements": 1_067_985 if output == "policy" else 1,
                        "maxAbs": 0.1,
                        "mae": 0.01,
                        "rmse": 0.02,
                        "maxRelative": 0.2,
                        "argmaxEqual": False,
                    }
                    for output in ["policy", "value"]
                }
                for name in NAMES
            }
        variants.append(variant)
    manifest = {
        "schema": 1,
        "trained": True,
        "sourceDirty": False,
        "sourceCommit": SOURCE,
        "license": "Apache-2.0",
        "id": "opaque-m-full",
        "seed": metadata["seed"],
        "parameters": 25_783_688,
        "numericContract": "voxelshogi-trained-numeric-v1",
        "inputSchema": "voxelshogi-standard-features-v1",
        "ruleset": "voxelshogi-standard-v1",
        "inputs": {"features": {"shape": [1, 729, 43], "dtype": "float32"}},
        "outputs": {
            "policy": {"shape": [1, 1_067_985], "dtype": "float32"},
            "value": {"shape": [1, 1], "dtype": "float32"},
        },
        "checkpoint": deepcopy(selection["weights"]),
        "fixtures": [
            {**f, "input": file("inputs/" + f["name"] + ".f32", 125_388)}
            for f in fixtures
        ],
        "variants": variants,
        "research": {
            "schema": "voxelshogi-research-inference-v1",
            "architecture": deepcopy(metadata["architecture"]),
            "trainingSourceCommit": metadata["source_commit"],
            "trainingBindingSha256": metadata["training_binding_sha256"],
            "selectedUpdate": metadata["step"],
            "totalUpdates": selection["binding"]["config"]["total_updates"],
            "selection": file("selection.json"),
            "history": file("training-history.jsonl", len(history.read_bytes())),
            "finalProtocol": file("final-protocol.json"),
            "inputAudit": file("input-audit.json"),
            "evaluationProtocolSha256": fingerprint(p),
            "finalRootsSha256": fingerprint(frozen["roots"]),
        },
    }
    manifest["checkpoint"].pop("metadata")
    manifest["research"]["history"]["sha256"] = hashlib.sha256(
        history.read_bytes()
    ).hexdigest()
    return manifest, selection, history.read_bytes(), frozen, reports, audit


def review(args):
    from training.research_inference_release import review_manifest

    manifest, selection, history, frozen, reports, audit = args
    return review_manifest(
        manifest,
        source_commit=SOURCE,
        selection=selection,
        history=history,
        frozen=frozen,
        reports=reports,
        audit=audit,
    )


def test_fixed_M_inventory_has_each_actual_format_and_its_own_evidence(tmp_path):
    args = fixture(tmp_path)
    inventory = review(args)
    assert len(inventory) == 42
    assert inventory["fp32.onnx"] == args[0]["variants"][0]["model"]
    assert inventory["reference/int8/material-b-policy.f32"]["bytes"] == 4_271_940
    assert set(inventory) >= {
        "model.safetensors",
        "selection.json",
        "training-history.jsonl",
        "final-protocol.json",
        "input-audit.json",
        "evaluation/fp32.json",
        "evaluation/fp16.json",
        "evaluation/int8.json",
    }
    assert (
        args[0]["variants"][2]["fp32Difference"]["initial-b"]["policy"]["argmaxEqual"]
        is False
    )


@pytest.mark.parametrize(
    "change",
    [
        "source",
        "untrained",
        "dirty",
        "ci",
        "license",
        "profile",
        "count",
        "seed",
        "selected",
        "history",
        "cpu",
        "shape",
        "fixture",
        "fixture-bytes",
        "variant",
        "duplicate-model",
        "reference",
        "conversion",
        "elements",
        "nonfinite",
        "unbound-evaluation",
        "shared-report",
        "report-model",
        "s-weights",
        "development",
        "roots",
        "root-count",
        "case-seed",
        "partial-games",
        "wrong-color",
        "wrong-prefix",
        "no-query",
        "no-audit",
        "audit-run",
        "audit-protocol",
        "audit-queries",
    ],
)
def test_incomplete_or_mismatched_M_evidence_is_rejected(tmp_path, change):
    m, s, h, f, reports, audit = args = fixture(tmp_path)
    if change == "source":
        m["sourceCommit"] = "e" * 40
    elif change == "untrained":
        m["trained"] = False
    elif change == "dirty":
        m["sourceDirty"] = True
    elif change == "ci":
        m["ciFixture"] = "opaque"
    elif change == "license":
        m["license"] = "MIT"
    elif change == "profile":
        m["research"]["architecture"]["width"] = 8
    elif change == "count":
        m["parameters"] = 5_000_000
    elif change == "seed":
        m["seed"] += 1
    elif change == "selected":
        m["research"]["selectedUpdate"] = 1
    elif change == "history":
        args = (m, s, h + b"{}\n", f, reports, audit)
    elif change == "cpu":
        s["binding"]["config"]["device"] = "cpu"
    elif change == "shape":
        m["outputs"]["policy"]["shape"] = [1, 2]
    elif change == "fixture":
        m["fixtures"][0]["side"] = "w"
    elif change == "fixture-bytes":
        m["fixtures"][0]["input"]["bytes"] = 4
    elif change == "variant":
        m["variants"].pop()
    elif change == "duplicate-model":
        m["variants"][1]["model"]["sha256"] = m["variants"][0]["model"]["sha256"]
    elif change == "reference":
        m["variants"][0]["references"]["material-b"]["value"]["bytes"] = 8
    elif change == "conversion":
        m["variants"][1]["conversion"]["compute"] = "float16"
    elif change == "elements":
        m["variants"][2]["conversion"]["quantizedElements"] = 0
    elif change == "nonfinite":
        m["variants"][2]["fp32Difference"]["initial-b"]["policy"]["rmse"] = float("nan")
    elif change == "unbound-evaluation":
        m["variants"][0]["evaluation"]["weightsSha256"] = "0" * 64
    elif change == "shared-report":
        m["variants"][1]["evaluation"]["report"]["path"] = "evaluation/fp32.json"
    elif change == "report-model":
        reports["int8"]["model_sha256"] = m["variants"][0]["model"]["sha256"]
    elif change == "s-weights":
        m["checkpoint"]["sha256"] = "0" * 64
    elif change == "development":
        f["protocol"]["purpose"] = "development"
    elif change == "roots":
        m["research"]["finalRootsSha256"] = "0" * 64
    elif change == "root-count":
        f["roots"].pop(next(iter(f["roots"])))
    elif change == "case-seed":
        f["protocol"]["cases"][0]["seed"] += 1
    elif change == "partial-games":
        reports["fp32"]["games"].pop()
    elif change == "wrong-color":
        reports["fp16"]["games"][0]["model_side"] = "w"
    elif change == "wrong-prefix":
        reports["int8"]["games"][0]["record"]["initial"] = "different"
    elif change == "no-query":
        reports["fp32"]["actual_neural_queries"] = 0
    elif change == "no-audit":
        audit["passed"] = False
    elif change == "audit-run":
        audit["runs"]["fp16"]["run_sha256"] = "0" * 64
    elif change == "audit-protocol":
        audit["runs"]["int8"]["protocol_sha256"] = "0" * 64
    elif change == "audit-queries":
        audit["observed_input_counts"].pop("neural-query/int8/model")
    with pytest.raises(ValueError):
        review(args)


def package(tmp_path):
    m, s, h, f, reports, audit = fixture(tmp_path)
    folder = tmp_path / "release"
    folder.mkdir()

    def write(path, raw):
        p = folder / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
        return {
            "path": path,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }

    def value(path, obj):
        return write(path, json.dumps(obj, sort_keys=True).encode())

    m["research"]["selection"] = value("selection.json", s)
    m["research"]["history"] = write("training-history.jsonl", h)
    m["research"]["finalProtocol"] = value("final-protocol.json", f)
    m["research"]["inputAudit"] = value("input-audit.json", audit)
    for v in m["variants"]:
        v["evaluation"]["report"] = value(
            "evaluation/" + v["precision"] + ".json", reports[v["precision"]]
        )
    value("manifest.json", m)
    card = (
        "---\nlicense: apache-2.0\n---\n# Handwritten metadata fixture\n\n"
        + "".join(
            "## " + title + "\nOpaque fixture only.\n\n"
            for title in [
                "Training and provenance",
                "Evaluation",
                "Inference",
                "Access and license",
            ]
        )
    )
    write("README.md", card.encode())
    write("LICENSE", b"Opaque unit license, not a real model")
    return folder, m, card


def plan_args(**overrides):
    return {
        "repo_id": "voxelshogi/voxelshogi-research-m-full-v1",
        "repo_type": "model",
        "license_id": "apache-2.0",
        "license_approved": True,
        "source_commit": SOURCE,
        "artifact_role": "research-inference-package",
    } | overrides


def test_M_role_routes_exact_inventory_without_relaxing_S_limits(monkeypatch, tmp_path):
    import training.hub_release as hub

    folder, m, _ = package(tmp_path)
    calls = []

    def inventory(folder, repo_type, *, expected, artifact_role):
        calls.append((repo_type, expected, artifact_role))
        return [m["variants"][0]["model"]]

    monkeypatch.setattr(hub, "_inventory", inventory)
    result = hub.plan_release(folder, **plan_args())
    assert result["artifact_role"] == "research-inference-package"
    assert isinstance(calls[0][1], dict)
    assert len(calls[0][1]) == 42 and calls[0][2] == "research-inference-package"
    assert hub.artifact_limits("research-inference-package", "fp16.onnx") == (
        512 * 1024**2,
        1536 * 1024**2,
    )
    assert hub.artifact_limits("research-inference-package", "model.safetensors") == (
        512 * 1024**2,
        1536 * 1024**2,
    )
    assert hub.artifact_limits("inference-package", "fp16.onnx") == (
        64 * 1024**2,
        512 * 1024**2,
    )
    assert hub.artifact_limits("research-training-state", "x/state.safetensors") == (
        512 * 1024**2,
        2 * 1024**3,
    )


@pytest.mark.parametrize(
    "change",
    [
        "wrong-repo",
        "wrong-type",
        "wrong-license",
        "unapproved",
        "default-role",
        "S-role",
        "report-bytes",
        "history-bytes",
        "selection-bytes",
        "symlink",
        "notice",
        "card",
    ],
)
def test_M_publication_role_rejects_unreviewed_destination_and_changed_evidence(
    monkeypatch, tmp_path, change
):
    import training.hub_release as hub

    folder, m, _ = package(tmp_path)
    called = []
    monkeypatch.setattr(hub, "_inventory", lambda *a, **kw: called.append(True))
    args = plan_args()
    if change == "wrong-repo":
        args["repo_id"] = "voxelshogi/voxelshogi-research-m-cnn-v1"
    elif change == "wrong-type":
        args["repo_type"] = "dataset"
    elif change == "wrong-license":
        args["license_id"] = "mit"
    elif change == "unapproved":
        args["license_approved"] = False
    elif change == "default-role":
        args["artifact_role"] = "artifacts"
    elif change == "S-role":
        args["artifact_role"] = "inference-package"
    elif change == "report-bytes":
        (folder / "evaluation/int8.json").write_bytes(b"changed")
    elif change == "history-bytes":
        (folder / "training-history.jsonl").write_bytes(b"changed")
    elif change == "selection-bytes":
        (folder / "selection.json").write_bytes(b"changed")
    elif change == "symlink":
        original = folder / "final-protocol.json"
        original.rename(folder / "moved.json")
        original.symlink_to("moved.json")
    elif change == "notice":
        (folder / "NOTICE").symlink_to("LICENSE")
    elif change == "card":
        (folder / "README.md").write_text("---\nlicense: apache-2.0\n---\nempty")
    with pytest.raises(ValueError):
        hub.plan_release(folder, **args)
    assert not called


@pytest.mark.parametrize(
    "change", ["boolean-schema", "boolean-dimension", "fixture-record"]
)
def test_M_format_identity_matches_the_browser_and_fixed_fixture_contract(
    tmp_path, change
):
    args = fixture(tmp_path)
    m = args[0]
    if change == "boolean-schema":
        m["schema"] = True
    elif change == "boolean-dimension":
        m["inputs"]["features"]["shape"][0] = True
    else:
        m["fixtures"][0]["record"]["initial"] = "different"
    with pytest.raises(ValueError):
        review(args)


def test_research_catalog_pins_verified_M_profile_and_exact_release(
    monkeypatch, tmp_path
):
    import training.hub_release as hub
    from training.research_inference_release import catalog_release

    folder, m, _ = package(tmp_path)
    reviewed = {
        "schema": 1,
        **plan_args(),
        "license": "apache-2.0",
        "private": False,
        "gated": "manual",
        "files": [
            {
                "path": "manifest.json",
                "bytes": (folder / "manifest.json").stat().st_size,
                "sha256": hashlib.sha256(
                    (folder / "manifest.json").read_bytes()
                ).hexdigest(),
            },
            {
                "path": "README.md",
                "bytes": (folder / "README.md").stat().st_size,
                "sha256": hashlib.sha256(
                    (folder / "README.md").read_bytes()
                ).hexdigest(),
            },
            {
                "path": "LICENSE",
                "bytes": (folder / "LICENSE").stat().st_size,
                "sha256": hashlib.sha256((folder / "LICENSE").read_bytes()).hexdigest(),
            },
        ],
    }
    reviewed.pop("license_id")
    receipt = {
        "verified": True,
        "community_disabled": True,
        "dry_run": False,
        "repo_id": reviewed["repo_id"],
        "repo_type": "model",
        "hub_commit": "c" * 40,
        "release_sha256": fingerprint(reviewed),
    }
    called = []

    def replan(*args, **kwargs):
        called.append(kwargs)
        return deepcopy(reviewed)

    monkeypatch.setattr(hub, "plan_release", replan)
    entry = catalog_release(folder, reviewed, receipt)
    assert entry == {
        "approved": True,
        "id": m["id"],
        "license": "Apache-2.0",
        "sourceCommit": SOURCE,
        "repo": reviewed["repo_id"],
        "revision": "c" * 40,
        "manifest": reviewed["files"][0],
        "notices": reviewed["files"][1:],
        "profile": "research-m-v1",
        "architecture": "full",
    }
    assert called[0]["artifact_role"] == "research-inference-package"
    for changed in [
        {"verified": False},
        {"community_disabled": False},
        {"dry_run": True},
        {"hub_commit": "main"},
        {"repo_id": "voxelshogi/other"},
        {"repo_type": "dataset"},
        {"release_sha256": "0" * 64},
    ]:
        with pytest.raises(ValueError):
            catalog_release(folder, reviewed, receipt | changed)
    monkeypatch.setattr(
        hub, "plan_release", lambda *a, **kw: reviewed | {"source_commit": "0" * 40}
    )
    with pytest.raises(ValueError):
        catalog_release(folder, reviewed, receipt)


@pytest.mark.parametrize("parent", ["folder", "evaluation"])
def test_M_metadata_reader_rejects_symlinked_parents_before_reading(tmp_path, parent):
    from training.research_inference_release import research_inventory

    folder, _, card = package(tmp_path)
    if parent == "folder":
        actual = folder
        folder = tmp_path / "alias"
        folder.symlink_to(actual, target_is_directory=True)
    else:
        actual = folder / "evaluation"
        actual.rename(tmp_path / "outside")
        actual.symlink_to(tmp_path / "outside", target_is_directory=True)
    with pytest.raises(ValueError):
        research_inventory(
            folder,
            {
                "source_commit": SOURCE,
                "repo_id": plan_args()["repo_id"],
                "license": "apache-2.0",
            },
            card,
        )


def test_M_role_still_uses_actual_shared_inventory_hash_verification(tmp_path):
    from training.hub_release import _inventory

    folder = tmp_path / "small-opaque-hash-fixture"
    folder.mkdir()
    expected = {}
    for name in ["README.md", "LICENSE", "fp32.onnx"]:
        raw = ("opaque metadata-only fixture " + name).encode()
        (folder / name).write_bytes(raw)
        expected[name] = {
            "path": name,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    result = _inventory(
        folder, "model", expected=expected, artifact_role="research-inference-package"
    )
    assert {r["path"] for r in result} == set(expected)
    original = (folder / "fp32.onnx").read_bytes()
    (folder / "fp32.onnx").write_bytes(bytes([original[0] ^ 1]) + original[1:])
    with pytest.raises(ValueError, match="hash"):
        _inventory(
            folder,
            "model",
            expected=expected,
            artifact_role="research-inference-package",
        )


def test_history_descriptor_must_match_raw_history_even_when_selection_is_valid(
    tmp_path,
):
    args = fixture(tmp_path)
    args[0]["research"]["history"]["sha256"] = "0" * 64
    with pytest.raises(ValueError):
        review(args)


def test_actual_unique_query_counts_are_positive_and_bounded_by_observed_calls(
    tmp_path,
):
    args = fixture(tmp_path)
    args[-1]["observed_input_counts"]["neural-query/fp32/model"]["inputs"] = 0
    with pytest.raises(ValueError):
        review(args)


def test_metadata_same_length_semantically_equal_bytes_still_require_exact_hash(
    tmp_path,
):
    from training.research_inference_release import research_inventory

    folder, _, card = package(tmp_path)
    path = folder / "evaluation/fp16.json"
    raw = path.read_bytes()
    changed = raw.replace(b": ", b":\t", 1)
    assert (
        len(changed) == len(raw)
        and changed != raw
        and json.loads(changed) == json.loads(raw)
    )
    path.write_bytes(changed)
    with pytest.raises(ValueError):
        research_inventory(
            folder,
            {
                "source_commit": SOURCE,
                "repo_id": plan_args()["repo_id"],
                "license": "apache-2.0",
            },
            card,
        )


def test_fixed_final_case_seed_is_checked_independently_of_descriptor_hashes(tmp_path):
    from training.research_inference_release import final_protocol

    m, _, _, f, _, _ = fixture(tmp_path)
    f["protocol"]["cases"][0]["seed"] += 1
    with pytest.raises(ValueError):
        final_protocol(
            f,
            model_sha256=m["variants"][0]["model"]["sha256"],
            evaluation_source=SOURCE,
        )


def test_fixed_final_root_inputs_must_be_distinct(tmp_path):
    from training.research_inference_release import final_protocol

    m, _, _, f, _, _ = fixture(tmp_path)
    names = list(f["roots"])
    f["roots"][names[1]]["input"] = f["roots"][names[0]]["input"]
    with pytest.raises(ValueError):
        final_protocol(
            f,
            model_sha256=m["variants"][0]["model"]["sha256"],
            evaluation_source=SOURCE,
        )
