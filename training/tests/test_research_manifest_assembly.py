"""Metadata-only assembly; no model bytes, games, Torch or native execution."""

import hashlib
import json
from copy import deepcopy

import pytest

from training.tests.test_research_inference_release import SOURCE, fixture


def raw(value):
    return (json.dumps(value, indent=2) + "\n").encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def arguments(tmp_path):
    model, selection, history, frozen, reports, audit = fixture(tmp_path)
    payloads = {
        "selection.json": raw(selection),
        "training-history.jsonl": history,
        "final-protocol.json": raw(frozen),
        "input-audit.json": raw(audit),
        **{
            f"evaluation/{precision}.json": raw(report)
            for precision, report in reports.items()
        },
    }
    for key in [
        "history",
        "finalProtocol",
        "inputAudit",
        "evaluationProtocolSha256",
        "finalRootsSha256",
    ]:
        model["research"].pop(key)
    model["research"]["selection"] = {
        "path": "selection.json",
        "bytes": len(payloads["selection.json"]),
        "sha256": sha(payloads["selection.json"]),
    }
    for variant in model["variants"]:
        variant.pop("evaluation")
    conversion = raw(
        {
            "schema": "voxelshogi-research-conversion-v1",
            "conversion_complete": True,
            "inference_publication_approved": False,
            "weight_metadata": selection["weights"]["metadata"],
            "model": model,
            "history": {
                "path": "training-history.jsonl",
                "bytes": len(history),
                "sha256": sha(history),
            },
        }
    )
    return (
        conversion,
        payloads,
        {
            "conversion_sha256": sha(conversion),
            "final_protocol_sha256": sha(payloads["final-protocol.json"]),
            "source_commit": SOURCE,
        },
    )


def test_assembly_binds_all_original_metadata_and_keeps_quantization_differences(
    tmp_path,
):
    from training.research_manifest_assembly import assemble_manifest

    conversion, payloads, options = arguments(tmp_path)
    before = deepcopy(payloads)
    manifest = assemble_manifest(conversion, payloads, **options)
    assert payloads == before
    assert [v["precision"] for v in manifest["variants"]] == ["fp32", "fp16", "int8"]
    for name, path in [
        ("history", "training-history.jsonl"),
        ("finalProtocol", "final-protocol.json"),
        ("inputAudit", "input-audit.json"),
    ]:
        assert manifest["research"][name] == {
            "path": path,
            "bytes": len(payloads[path]),
            "sha256": sha(payloads[path]),
        }
    for variant in manifest["variants"]:
        path = f"evaluation/{variant['precision']}.json"
        actual = variant["evaluation"]
        assert actual["scope"] == "final-holdout-v1" and actual["complete"] is True
        assert actual["gameCount"] == 24
        assert actual["modelSha256"] == variant["model"]["sha256"]
        assert actual["report"] == {
            "path": path,
            "bytes": len(payloads[path]),
            "sha256": sha(payloads[path]),
        }
    assert (
        manifest["variants"][1]["fp32Difference"]["initial-b"]["policy"]["argmaxEqual"]
        is False
    )
    assert manifest["research"]["trainingSourceCommit"] != manifest["sourceCommit"]


@pytest.mark.parametrize(
    "path",
    [
        "selection.json",
        "training-history.jsonl",
        "final-protocol.json",
        "input-audit.json",
        "evaluation/fp32.json",
        "evaluation/fp16.json",
        "evaluation/int8.json",
    ],
)
def test_every_metadata_file_is_required(tmp_path, path):
    from training.research_manifest_assembly import assemble_manifest

    conversion, payloads, options = arguments(tmp_path)
    payloads.pop(path)
    with pytest.raises(ValueError):
        assemble_manifest(conversion, payloads, **options)


@pytest.mark.parametrize(
    "change",
    [
        "conversion-hash",
        "frozen-hash",
        "history",
        "selection",
        "incomplete-report",
        "wrong-model",
        "audit",
        "unknown-file",
        "duplicate-json",
        "nonfinite",
        "weights-metadata",
        "conversion-complete",
        "conversion-history",
        "publication-flag",
        "conversion-role",
        "conversion-mutable",
        "metadata-mutable",
        "conversion-limit",
    ],
)
def test_stale_incomplete_or_rebound_evidence_is_not_promoted(tmp_path, change):
    from training.research_manifest_assembly import assemble_manifest

    conversion, payloads, options = arguments(tmp_path)
    if change == "conversion-hash":
        options["conversion_sha256"] = "0" * 64
    elif change == "frozen-hash":
        options["final_protocol_sha256"] = "0" * 64
    elif change == "history":
        payloads["training-history.jsonl"] += b"\n"
    elif change == "selection":
        payloads["selection.json"] += b"\n"
    elif change in ["incomplete-report", "wrong-model"]:
        r = json.loads(payloads["evaluation/int8.json"])
        r.update(
            {"complete": False}
            if change == "incomplete-report"
            else {"model_sha256": "0" * 64}
        )
        payloads["evaluation/int8.json"] = raw(r)
    elif change == "audit":
        r = json.loads(payloads["input-audit.json"])
        r["passed"] = False
        payloads["input-audit.json"] = raw(r)
    elif change == "unknown-file":
        payloads["optimizer.pt"] = b"opaque"
    elif change == "duplicate-json":
        payloads["input-audit.json"] = payloads["input-audit.json"].replace(
            b'"passed": true,', b'"passed": true, "passed": true,'
        )
    elif change == "nonfinite":
        payloads["input-audit.json"] = payloads["input-audit.json"].replace(
            b"{", b'{"unrelated": NaN,', 1
        )
    elif change == "conversion-mutable":
        conversion = bytearray(conversion)
    elif change == "metadata-mutable":
        payloads["input-audit.json"] = bytearray(payloads["input-audit.json"])
    elif change == "conversion-limit":
        conversion += b" " * (1024**2 + 1)
        options["conversion_sha256"] = sha(conversion)
    elif change in [
        "weights-metadata",
        "conversion-complete",
        "conversion-history",
        "publication-flag",
        "conversion-role",
    ]:
        value = json.loads(conversion)
        if change == "weights-metadata":
            value["weight_metadata"]["step"] += 1
        elif change == "conversion-complete":
            value["conversion_complete"] = False
        elif change == "conversion-history":
            value["history"]["sha256"] = "0" * 64
        elif change == "publication-flag":
            value["inference_publication_approved"] = True
        else:
            value["schema"] = "voxelshogi-conversion-v1"
        conversion = raw(value)
        options["conversion_sha256"] = sha(conversion)
    with pytest.raises(ValueError):
        assemble_manifest(conversion, payloads, **options)
