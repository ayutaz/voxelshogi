"""Recheck complete pilot proof/receipt/hash links before result publication.

This validates immutable evidence relationships. It does not rerun training or
replace the original Rust replay, CUDA parity and whole-input audit verifiers.
"""

import re
from pathlib import Path

from infrastructure.research.pilot.results import finite_json, read_owned
from infrastructure.research.pilot.validation import development_protocol
from training.evaluation_v2 import fingerprint
from training.feature_cache import file_hash
from training.hub_release import _policy


def verify_complete_evidence(value, base, compute):
    base = Path(base)
    source = value["job"]["source_commit"]

    def read(name):
        return finite_json(read_owned(base / name).decode())

    learning, development = (
        read("training-complete.json"),
        read("development/complete.json"),
    )
    audit = read("development/input-audit.json")
    trace = base / "development/queries.jsonl"
    if (
        learning != compute["learning"]
        or development != compute["development"]
        or learning.get("learning_complete") is not True
        or learning.get("scientific_pilots") != 2
        or len(learning["cycles"]) != 2
    ):
        raise ValueError("complete learning/development evidence differs")
    if (
        development.get("games") != 48
        or development.get("source_commit") != source
        or development.get("leakage_free") is not True
        or development.get("final_holdout_evaluated") is not False
        or file_hash(trace) != development["query_trace_sha256"]
        or len(read_owned(trace).splitlines()) != development["queries"]
        or file_hash(base / "development/input-audit.json")
        != development["input_audit_sha256"]
        or audit.get("schema") != "voxelshogi-generation-input-audit-v1"
        or audit.get("passed") is not True
    ):
        raise ValueError("complete queried/played input audit evidence differs")
    for inputs, saved_cycle in zip(
        value["job"]["inputs"], learning["cycles"], strict=True
    ):
        name = inputs["config"]["architecture"]["architecture"]
        cycle, proof = read(name + "/complete.json"), read(name + "/resume-proof.json")
        if (
            cycle != saved_cycle
            or cycle.get("source_commit") != source
            or cycle.get("architecture") != name
            or cycle.get("inputs_sha256") != fingerprint(inputs)
            or cycle.get("scientific_pilots") != 1
            or cycle.get("additional_independent_seeds") != 0
            or cycle.get("resume_proof") != proof
            or proof.get("verified") is not True
            or proof.get("source_commit") != source
            or proof.get("total_updates") != inputs["config"]["total_updates"]
        ):
            raise ValueError("complete fixed CUDA cycle proof differs")
        for stage, step in (
            ("intermediate", value["job"]["split_step"]),
            ("final", inputs["config"]["total_updates"]),
        ):
            prefix = name + "/" + stage + "-transfer/"
            plan, receipt, transfer = [
                read(prefix + n + ".json")
                for n in ("publication-plan", "publication-receipt", "complete")
            ]
            _policy(plan)
            if (
                plan.get("artifact_role") != "research-training-state"
                or plan["source_commit"] != source
                or plan["expected_binding"]["config"] != inputs["config"]
                or not plan["files"]
                or receipt.get("verified") is not True
                or receipt.get("community_disabled") is not True
                or receipt.get("dry_run") is not False
                or receipt.get("repo_id") != plan["repo_id"]
                or receipt.get("repo_type") != "model"
                or re.fullmatch(r"[0-9a-f]{40}", str(receipt.get("hub_commit"))) is None
                or receipt.get("release_sha256") != fingerprint(plan)
                or transfer != cycle[stage + "_transfer"]
                or transfer.get("receipt") != receipt
                or transfer.get("restored") is not True
                or transfer["progress"]["step"] != step
            ):
                raise ValueError("state HF roundtrip evidence differs")
        diagnostic = read(name + "/diagnostics/complete.json")
        selected = name + "/diagnostics/selected/"
        selection = read(selected + "selection.json")
        weights = base / selected / "model.safetensors"
        if (
            any(p.is_symlink() for p in (weights, *weights.parents))
            or not weights.is_file()
            or not 0 < weights.stat().st_size <= 192 * 1024**2
        ):
            raise ValueError("selected M weights escaped bounded owned source")
        if (
            diagnostic != compute["diagnostics"][name]
            or diagnostic.get("source_commit") != source
            or diagnostic.get("architecture") != name
            or file_hash(base / selected / "selection.json")
            != diagnostic["selection"]["selection_sha256"]
            or selection["weights"]["sha256"] != diagnostic["weights_sha256"]
            or file_hash(weights) != diagnostic["weights_sha256"]
        ):
            raise ValueError("same selected-best diagnostic evidence differs")
        prefix = "development/" + name + "/"
        protocol, run, summary = [
            read(prefix + n + ".json") for n in ("protocol", "run", "summary")
        ]
        expected = development_protocol(
            value["development"],
            expected_sha256=value["development_sha256"],
            source_commit=source,
            weights_sha256=diagnostic["weights_sha256"],
        )
        names = {f"{c['id']}-{s}.json" for c in expected["cases"] for s in ("b", "w")}
        if (
            protocol != expected
            or run.get("complete") is not True
            or run.get("games") != 24
            or len(run["files"]) != 24
            or {d["path"] for d in run["files"]} != names
            or run.get("protocol_sha256") != fingerprint(expected)
            or summary != development["by_architecture"][name]["summary"]
            or run.get("summary_sha256") != file_hash(base / prefix / "summary.json")
            or audit["runs"][name]["protocol_sha256"] != fingerprint(protocol)
            or audit["runs"][name]["run_sha256"]
            != file_hash(base / prefix / "run.json")
        ):
            raise ValueError("frozen24-game cohort summary/audit evidence differs")
        for entry in run["files"]:
            path = base / prefix / entry["path"]
            data = read_owned(path)
            if len(data) != entry["bytes"] or file_hash(path) != entry["sha256"]:
                raise ValueError("replay-verified match bytes changed")
