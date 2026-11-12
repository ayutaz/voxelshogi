"""Pure manifest assembly from immutable conversion and final-evaluation bytes.

This neither runs evaluation nor authorizes publication. Linux must produce the
actual models/games/query audit; the HF harness then verifies every payload.
"""

import hashlib
import json

from training.evaluation_v2 import fingerprint
from training.research_inference_release import (
    METADATA_BYTES,
    PRECISIONS,
    review_manifest,
)
from training.research_weights import _unique_object


def _descriptor(path, raw, maximum=METADATA_BYTES):
    if type(raw) is not bytes or not 0 < len(raw) <= maximum:
        raise ValueError("bounded immutable metadata bytes required")
    return {"path": path, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _parse(raw):
    def reject_constant(_value):
        raise ValueError("nonfinite assembly metadata")

    value = json.loads(
        raw, object_pairs_hook=_unique_object, parse_constant=reject_constant
    )
    if type(value) is not dict:
        raise ValueError("metadata object required")
    return value


def assemble_manifest(
    conversion, payloads, *, conversion_sha256, final_protocol_sha256, source_commit
):
    """Keep all three measured formats; bind the seven original metadata files."""
    paths = {
        "selection.json",
        "training-history.jsonl",
        "final-protocol.json",
        "input-audit.json",
        *(f"evaluation/{p}.json" for p in PRECISIONS),
    }
    if type(payloads) is not dict or set(payloads) != paths:
        raise ValueError(
            "exact selection/history/frozen/audit and three reports required"
        )
    descriptors = {
        path: _descriptor(
            path,
            value,
            64 * 1024**2 if path == "training-history.jsonl" else METADATA_BYTES,
        )
        for path, value in payloads.items()
    }
    if (
        _descriptor("conversion.json", conversion)["sha256"] != conversion_sha256
        or descriptors["final-protocol.json"]["sha256"] != final_protocol_sha256
    ):
        raise ValueError("frozen conversion or prelearning final-protocol hash differs")
    try:
        converted = _parse(conversion)
        selection = _parse(payloads["selection.json"])
        frozen = _parse(payloads["final-protocol.json"])
        audit = _parse(payloads["input-audit.json"])
        reports = {p: _parse(payloads[f"evaluation/{p}.json"]) for p in PRECISIONS}
        if (
            converted["schema"] != "voxelshogi-research-conversion-v1"
            or converted["conversion_complete"] is not True
            or converted["inference_publication_approved"] is not False
            or converted["weight_metadata"] != selection["weights"]["metadata"]
            or converted["history"] != descriptors["training-history.jsonl"]
        ):
            raise ValueError(
                "completed conversion and unchanged selected inputs required"
            )
        model = converted["model"]
        research = model["research"]
        if research["selection"] != descriptors["selection.json"]:
            raise ValueError("original converted selection bytes differ")
        research.update(
            history=descriptors["training-history.jsonl"],
            finalProtocol=descriptors["final-protocol.json"],
            inputAudit=descriptors["input-audit.json"],
            evaluationProtocolSha256=fingerprint(frozen["protocol"]),
            finalRootsSha256=fingerprint(frozen["roots"]),
        )
        for variant in model["variants"]:
            precision = variant["precision"]
            report = reports[precision]
            variant["evaluation"] = {
                "scope": "final-holdout-v1",
                "complete": report["complete"],
                "gameCount": len(report["games"]),
                "modelSha256": report["model_sha256"],
                "weightsSha256": report["weights_sha256"],
                "report": descriptors[f"evaluation/{precision}.json"],
            }
        review_manifest(
            model,
            source_commit=source_commit,
            selection=selection,
            history=payloads["training-history.jsonl"],
            frozen=frozen,
            reports=reports,
            audit=audit,
        )
        return model
    except (KeyError, TypeError, AttributeError, json.JSONDecodeError) as error:
        raise ValueError("incomplete or invalid manifest assembly evidence") from error
