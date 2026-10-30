"""Known Python boundary/data/resource regressions; require executed failures."""

import json
import os
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "crates/voxelshogi-python/python/voxelshogi"
MUTATIONS = [
    (
        "evaluation-v2-runner-terminal-priority",
        "training/evaluation_v2_runner.py",
        'if snapshot["finished"]:',
        'if snapshot["finished"] and len(game.record()["moves"]) - prefix_length < case["max_additional_plies"]:',
        "test_evaluation_v2_runner.py",
    ),
    (
        "evaluation-v2-runner-additional-limit",
        "training/evaluation_v2_runner.py",
        'len(game.record()["moves"]) - prefix_length >= case["max_additional_plies"]',
        'len(game.record()["moves"]) >= case["max_additional_plies"]',
        "test_evaluation_v2_runner.py",
    ),
    (
        "evaluation-v2-runner-color-route",
        "training/evaluation_v2_runner.py",
        'choose_model if snapshot["side"] == model_side else choose_opponent',
        'choose_opponent if snapshot["side"] == model_side else choose_model',
        "test_evaluation_v2_runner.py",
    ),
    (
        "evaluation-v2-runner-interruption",
        "training/evaluation_v2_runner.py",
        "if stop_requested():",
        "if False:",
        "test_evaluation_v2_runner.py",
    ),
    (
        "evaluation-v2-runner-position-ply",
        "training/evaluation_v2_runner.py",
        '"position": " ".join(parts[:3])',
        '"position": " ".join(parts)',
        "test_evaluation_v2_runner.py",
    ),
    (
        "evaluation-v2-runner-position-hands",
        "training/evaluation_v2_runner.py",
        '"position": " ".join(parts[:3])',
        '"position": " ".join(parts[:2])',
        "test_evaluation_v2_runner.py",
    ),
    (
        "evaluation-v2-runner-search-binding",
        "training/evaluation_v2_runner.py",
        '"search_limits": limits,',
        '"search_limits": {},',
        "test_evaluation_v2_runner.py",
    ),
    (
        "evaluation-v2-cutoff-score",
        "training/evaluation_v2.py",
        'points = counts["win"] + 0.5 * counts["draw"]',
        'points = counts["win"] + 0.5 * (counts["draw"] + counts["cutoff"])',
        "test_evaluation_v2.py",
    ),
    (
        "evaluation-v2-condition-binding",
        "training/evaluation_v2.py",
        'row["protocol_sha256"] != digest',
        "False",
        "test_evaluation_v2.py",
    ),
    (
        "evaluation-v2-participant-binding",
        "training/evaluation_v2.py",
        'model_sha256 != protocol["participants"]["model"]["artifact_sha256"]',
        "False",
        "test_evaluation_v2.py",
    ),
    (
        "evaluation-v2-opening-prefix",
        "training/evaluation_v2.py",
        'or record["moves"][: len(opening["moves"])] != opening["moves"]',
        "or False",
        "test_evaluation_v2.py",
    ),
    (
        "evaluation-v2-cutoff-length",
        "training/evaluation_v2.py",
        'or plies != case["max_additional_plies"]',
        "or False",
        "test_evaluation_v2.py",
    ),
    (
        "evaluation-v2-position-leakage",
        "training/evaluation_v2.py",
        "if groups[left] & groups[right]:",
        "if False:",
        "test_evaluation_v2.py",
    ),
    (
        "evaluation-v2-color-pair-bootstrap",
        "training/evaluation_v2.py",
        "for _ in pair_wins) / (2 * len(pair_wins))",
        "for _ in ordered) / (2 * len(pair_wins))",
        "test_evaluation_v2.py",
    ),
    (
        "evaluation-v2-size-screen",
        "training/evaluation_v2.py",
        'len(cases) >= sensitivity["minimum_pairs"]',
        "True",
        "test_evaluation_v2.py",
    ),
    (
        "evaluation-v2-termination-screen",
        "training/evaluation_v2.py",
        'and overall["termination_rate"] >= sensitivity["minimum_termination_rate"]',
        "and True",
        "test_evaluation_v2.py",
    ),
    (
        "export-explicit-training-role",
        "export/trained.py",
        '"trainingSourceCommit", context.get("sourceCommit", "")',
        '"sourceCommit", ""',
        "test_export_lineage.py",
    ),
    (
        "export-lineage-export-role",
        "export/trained.py",
        'or provenance["export_source_commit"] != manifest["sourceCommit"]',
        "or False",
        "test_export_lineage.py",
    ),
] + [
    (
        "m6-shared-payload-ip",
        "training/rental_control.py",
        '"with_public_ip": public_ip,\n            "tags":',
        '"with_public_ip": True,\n            "tags":',
        "test_m6_shared_ip.py",
    ),
    (
        "m6-shared-payload-region",
        "training/rental_control.py",
        '"instance_type": self.sku,\n                    "datacenters": [dc]',
        '"instance_type": self.sku,\n                    "datacenters": [DC]',
        "test_m6_shared_ip.py",
    ),
    (
        "m6-shared-public-validation",
        "training/rental_control.py",
        'not public_ip\n                or offer["ip_availability_per_dc"]',
        'True\n                or offer["ip_availability_per_dc"]',
        "test_m6_shared_ip.py",
    ),
    (
        "vast-canonical-api-route",
        "training/vast_rental_control.py",
        'url = "https://console.vast.ai" + path.rstrip("/") + "/"',
        'url = "https://console.vast.ai" + path',
        "test_vast_rental_control.py",
    ),
    (
        "vast-storage-price",
        "training/vast_rental_control.py",
        'offer["dph_total"], offer["dph_base"] + offer["storage_total_cost"]',
        'offer["dph_base"], offer["dph_base"]',
        "test_vast_rental_control.py",
    ),
    (
        "vast-transfer-fee",
        "training/vast_rental_control.py",
        'or offer["inet_up_cost"] != 0',
        "or False",
        "test_vast_rental_control.py",
    ),
    (
        "vast-gpu-identity",
        "training/vast_rental_control.py",
        'or offer["gpu_name"] not in ("RTX 5090", "RTX_5090")',
        "or False",
        "test_vast_rental_control.py",
    ),
    (
        "vast-guard-before-create",
        "training/vast_rental_control.py",
        "        start_guard()",
        "        pass",
        "test_vast_rental_control.py",
    ),
    (
        "vast-contract-id",
        "training/vast_rental_control.py",
        'identity = response.get("new_contract")',
        'identity = response.get("id")',
        "test_vast_rental_control.py",
    ),
    (
        "vast-owned-destruction",
        "training/vast_rental_control.py",
        'if any(row.get("label") != self.tag for row in selected):',
        "if False:",
        "test_vast_rental_control.py",
    ),
    (
        "vast-destroy-absence",
        "training/vast_rental_control.py",
        'and not result["instances"]',
        "and True",
        "test_vast_rental_control.py",
    ),
    (
        "vast-account-identity",
        "training/vast_rental_control.py",
        'if path.exists() and json.loads(path.read_text()).get("id") != identity:',
        "if False:",
        "test_vast_rental_control.py",
    ),
    (
        "vast-live-balance",
        "training/vast_rental_control.py",
        "if minimum_usd and (",
        "if False and (",
        "test_vast_rental_control.py",
    ),
    (
        "trained-export-numeric-contract",
        "export/generate.py",
        "numeric_contract=TRAINED_NUMERIC_CONTRACT if review else None,",
        "numeric_contract=None,",
        "test_trained_export.py",
    ),
    (
        "trained-numeric-marker",
        "export/trained.py",
        'or manifest.get("numericContract") != TRAINED_NUMERIC_CONTRACT',
        "or False",
        "test_trained_metadata.py",
    ),
    (
        "m6-rental-approval",
        "training/m6_rental_control.py",
        'or approval.get("approved") is not True',
        "or False",
        "test_m6_rental_control.py",
    ),
    (
        "m6-rental-quote",
        "training/m6_rental_control.py",
        "return validate_m6_approval(\n            self.approval, self.tag, self.phase, self.maximum_seconds\n        )",
        "return QUOTES[self.sku]",
        "test_m6_rental_control.py",
    ),
    (
        "m6-rental-shared-budget",
        "training/m6_rental_control.py",
        "reserved + cap > 100",
        "False",
        "test_m6_rental_control.py",
    ),
    (
        "m6-rental-allocation",
        "training/m6_rental_control.py",
        'or sum(row["maximum_usd"] for row in owned) + cap > 24',
        "or False",
        "test_m6_rental_control.py",
    ),
    (
        "m6-rental-main-estimate",
        "training/m6_rental_control.py",
        'if phase == "main":',
        "if False:",
        "test_m6_rental_control.py",
    ),
    (
        "m6-rental-phase-limit",
        "training/m6_rental_control.py",
        "or not 1800 <= maximum_seconds <= limit",
        "or False",
        "test_m6_rental_control.py",
    ),
    (
        "m6-guard-namespace",
        "training/rental_control.py",
        '"--purpose",\n        purpose,',
        '"--purpose",\n        "m4",',
        "test_m6_rental_control.py",
    ),
    (
        "m6-guard-readiness",
        "training/rental_control.py",
        'value != {\n                "pid": child.pid,\n                "tag": tag,\n                "deadline_sha256": deadline_sha256,\n            }',
        "False",
        "test_m6_rental_control.py",
    ),
    (
        "m6-control-stale-terminal",
        "training/rental_control.py",
        '"terminal.json",\n                "deadline.json",',
        '"unused-terminal.json",\n                "deadline.json",',
        "test_m6_rental_control.py",
    ),
    (
        "state-release-separate-approval",
        "training/hub_release.py",
        'plan.get("state_publication_approved") is not True',
        "False",
        "test_training_state_release.py",
    ),
    (
        "state-release-separate-repo",
        "training/hub_release.py",
        'or plan["repo_id"] != "voxelshogi/voxelshogi-transformer-s-training-state"',
        "or False",
        "test_training_state_release.py",
    ),
    (
        "state-release-upload-budget",
        "training/hub_release.py",
        "reserve_state_upload(upload_budget, plan)",
        "pass",
        "test_training_state_release.py",
    ),
    (
        "state-release-budget-duplicate",
        "training/state_release.py",
        'if any(row["release_sha256"] == release for row in reservations):',
        "if False:",
        "test_training_state_release.py",
    ),
    (
        "state-release-budget-total",
        "training/state_release.py",
        'sum(row["maximum_bytes"] for row in reservations) + amount\n            > MAXIMUM_NEW_BYTES',
        "False",
        "test_training_state_release.py",
    ),
    (
        "inference-inventory-complete",
        "training/hub_release.py",
        "if names != set(expected):",
        "if False:",
        "test_inference_release.py",
    ),
    (
        "inference-inventory-hash",
        "training/hub_release.py",
        "file[key] != value for key, value in descriptor.items()",
        "False for key, value in descriptor.items()",
        "test_inference_release.py",
    ),
    (
        "inference-ci-not-publishable",
        "training/inference_release.py",
        '"ciFixture" in manifest',
        "False",
        "test_inference_release.py",
    ),
    (
        "inference-source-bound",
        "training/inference_release.py",
        'or manifest["sourceCommit"] != plan["source_commit"]',
        "or False",
        "test_inference_release.py",
    ),
    (
        "inference-license-bound",
        "training/inference_release.py",
        'or manifest["license"].lower() != plan["license"]',
        "or False",
        "test_inference_release.py",
    ),
    (
        "inference-all-formats",
        "training/inference_release.py",
        "] != list(PRECISIONS):",
        '] != [entry["precision"] for entry in variants]:',
        "test_inference_release.py",
    ),
    (
        "inference-catalog-verified",
        "training/inference_release.py",
        'or receipt.get("verified") is not True',
        "or False",
        "test_inference_release.py",
    ),
    (
        "inference-catalog-revision",
        "training/inference_release.py",
        'or not re.fullmatch(r"[0-9a-f]{40}", receipt.get("hub_commit", ""))',
        "or False",
        "test_inference_release.py",
    ),
    (
        "resume-archive-publication-link",
        "training/hub_release.py",
        "if manifest_path.is_symlink():",
        "if False:",
        "test_resume_archive_policy.py",
    ),
    (
        "resume-archive-tensor-value",
        "training/resume_archive.py",
        'return value\n        if kind in ("dict", "ordered_dict"):',
        'return value * 0\n        if kind in ("dict", "ordered_dict"):',
        "test_resume_archive.py",
    ),
    (
        "resume-archive-hash",
        "training/resume_archive.py",
        'or file_hash(path) != entry["sha256"]',
        "or False",
        "test_resume_archive.py",
    ),
    (
        "resume-archive-best-validation",
        "training/resume_archive.py",
        'if role == "best" and descriptor["progress"]["best_val_loss"] is None:',
        "if False:",
        "test_resume_archive_policy.py",
    ),
    (
        "resume-archive-publication-purpose",
        "training/hub_release.py",
        'and manifest.get("schema") == "voxelshogi-resume-archive-v1"',
        "and False",
        "test_resume_archive_policy.py",
    ),
    (
        "trained-evaluated-bytes",
        "export/trained.py",
        'raise ValueError("evaluated artifact size/hash differs")',
        "pass",
        "test_trained_metadata.py",
    ),
    (
        "trained-complete-cohort",
        "export/trained.py",
        "or len(files) != 60",
        "or False",
        "test_trained_metadata.py",
    ),
    (
        "trained-load-weights",
        "export/generate.py",
        "model.load_state_dict(state, strict=True)",
        "pass",
        "test_trained_export.py",
    ),
    (
        "trained-replay-summary",
        "export/trained.py",
        'raise ValueError("evaluated cohort summary differs from replayed games")',
        "pass",
        "test_trained_replay.py",
    ),
    (
        "trained-package-provenance",
        "export/generate.py",
        "validate_training_manifest(manifest)",
        "pass",
        "test_trained_export.py",
    ),
    (
        "evaluation-cutoff",
        "training/evaluation.py",
        'return "cutoff"',
        'return "draw"',
        "test_evaluation_stats.py",
    ),
    (
        "evaluation-model-color",
        "training/evaluation.py",
        '{"b": "Black", "w": "White"}[model_side]',
        '{"b": "White", "w": "Black"}[model_side]',
        "test_evaluation_stats.py",
    ),
    (
        "evaluation-bootstrap-unit",
        "training/evaluation.py",
        "rng.choice(pair_wins)",
        'rng.choice([2 * int(game["outcome"] == "win") for game in games.values()])',
        "test_evaluation_stats.py",
    ),
    (
        "evaluation-natural-first",
        "training/evaluation.py",
        'if snapshot["finished"]:',
        'if snapshot["finished"] and len(game.record()["moves"]) < max_plies:',
        "test_evaluation_native.py",
    ),
    (
        "evaluation-record-outcome",
        "training/evaluation.py",
        'or row["outcome"] != outcome',
        "or False",
        "test_evaluation_cohort.py",
    ),
    (
        "student-legal-argmax",
        "training/students.py",
        "return legal[policy[0, legal].argmax().item()]",
        "return policy[0].argmax().item()",
        "test_students.py",
    ),
    (
        "student-canonical-tie",
        "training/students.py",
        "legal = sorted(game.legal_actions())",
        "legal = sorted(game.legal_actions(), reverse=True)",
        "test_students.py",
    ),
    (
        "evaluation-selected-config",
        "training/evaluate.py",
        'or binding["config"] != config.value()',
        "or False",
        "test_evaluation_selection.py",
    ),
    (
        "evaluation-completed-epoch",
        "training/evaluate.py",
        'or progress["epoch"] < 1',
        "or False",
        "test_evaluation_selection.py",
    ),
    (
        "cuda-resume-floating-drift",
        "training/cuda_trial.py",
        'raise ValueError(f"resume floating tensors differ: {path}")',
        "pass",
        "test_cuda_trial.py",
    ),
    (
        "cuda-resume-counter",
        "training/cuda_trial.py",
        'or (path and path[-1] == "step")',
        "or False",
        "test_cuda_trial.py",
    ),
    (
        "cuda-compiled-architecture",
        "training/cuda_preflight.py",
        'or "sm_120" not in facts["compiled_arches"]',
        "or False",
        "test_cuda_preflight.py",
    ),
    (
        "cuda-driver-minimum",
        "training/cuda_preflight.py",
        'or int(facts["driver"].split(".")[0]) < 580',
        "or False",
        "test_cuda_preflight.py",
    ),
    (
        "cuda-available",
        "training/cuda_preflight.py",
        'or facts["cuda_available"] is not True',
        "or False",
        "test_cuda_preflight.py",
    ),
    (
        "cuda-lock-source",
        "training/cuda_preflight.py",
        'raise ValueError(\n            "CUDA lock/source differs from pinned CPU-compatible environment"\n        )',
        "pass",
        "test_cuda_lock.py",
    ),
    (
        "cuda-kernel-gradient",
        "training/cuda_preflight.py",
        "product.sum().backward()",
        "(2 * product.sum()).backward()",
        "test_cuda_kernel.py",
    ),
    (
        "checkpoint-optimizer",
        "training/checkpoint.py",
        'optimizer.load_state_dict(state["optimizer"])',
        "pass",
        "test_checkpoint.py",
    ),
    (
        "checkpoint-rng",
        "training/checkpoint.py",
        '_restore_rng(state["rng"])',
        "pass",
        "test_checkpoint.py",
    ),
    (
        "checkpoint-binding-before-load",
        "training/checkpoint.py",
        'if receipt["binding"] != binding:',
        "if False:",
        "test_checkpoint.py",
    ),
    (
        "checkpoint-hash",
        "training/checkpoint.py",
        'raise ValueError("checkpoint state size/hash differs")',
        "pass",
        "test_checkpoint.py",
    ),
    (
        "checkpoint-weights-only",
        "training/checkpoint.py",
        'torch.load(path, map_location="cpu", weights_only=True)',
        'torch.load(path, map_location="cpu", weights_only=False)',
        "test_checkpoint.py",
    ),
    (
        "checkpoint-retention",
        "training/checkpoint.py",
        "prune_checkpoints(folder, binding=binding)",
        "pass",
        "test_checkpoint.py",
    ),
    (
        "fit-resume-cursor",
        "training/fit.py",
        'start_batch=progress["next_batch"],',
        "start_batch=0,",
        "test_training_runner.py",
    ),
    (
        "fit-validation-split",
        "training/fit.py",
        '"val", batch_size=config.batch_size, seed=config.seed',
        '"test", batch_size=config.batch_size, seed=config.seed',
        "test_training_runner.py",
    ),
    (
        "fit-best-selection",
        "training/fit.py",
        'metrics["loss"] < progress["best_val_loss"]',
        'metrics["loss"] > progress["best_val_loss"]',
        "test_training_runner.py",
    ),
    (
        "fit-initial-stop",
        "training/fit.py",
        'if stop_requested():\n        return finish("stopped")',
        'if False:\n        return finish("stopped")',
        "test_training_runner.py",
    ),
    (
        "fit-cursor-example-count",
        "training/fit.py",
        "min(cursor * config.batch_size, count)",
        "cursor",
        "test_runner_config.py",
    ),
    (
        "learning-legal-mask",
        "training/learning.py",
        "logits[i, legal].unsqueeze(0),",
        "logits[i].unsqueeze(0),",
        "test_learning.py",
    ),
    (
        "learning-value-loss",
        "training/learning.py",
        '"total": policy + value',
        '"total": policy',
        "test_learning.py",
    ),
    (
        "learning-eval-mode",
        "training/learning.py",
        "model.eval()",
        "model.train()",
        "test_learning.py",
    ),
    (
        "learning-eval-weight",
        "training/learning.py",
        "sums[key] += value * count",
        "sums[key] += value",
        "test_learning.py",
    ),
    (
        "learning-update-before-gradient-check",
        "training/learning.py",
        'terms["total"].backward()',
        'terms["total"].backward()\n    optimizer.step()',
        "test_learning.py",
    ),
    (
        "learning-gradient-clip",
        "training/learning.py",
        "parameters, max_norm=1.0, error_if_nonfinite=True",
        "parameters, max_norm=10.0, error_if_nonfinite=True",
        "test_learning.py",
    ),
    (
        "learning-train-split",
        "training/learning.py",
        '_validate_batch(batch, "train")',
        "_validate_batch(batch, batch.split)",
        "test_learning.py",
    ),
    (
        "cache-replay",
        "training/feature_cache.py",
        'raise ValueError("feature replay differs from verified row")',
        "pass",
        "test_feature_cache.py",
    ),
    (
        "cache-hash",
        "training/feature_cache.py",
        'raise ValueError("cache file size/hash differs")',
        "pass",
        "test_feature_cache.py",
    ),
    (
        "cache-split",
        "training/feature_cache.py",
        'if item["split"] == split',
        'if item["split"] != split',
        "test_feature_cache.py",
    ),
    (
        "sampler-partial-batch",
        "training/learning.py",
        "yield indices[offset : offset + batch_size]",
        "yield indices[offset : offset + batch_size] if offset + batch_size <= size else []",
        "test_sampler.py",
    ),
    (
        "sampler-resume-cursor",
        "training/learning.py",
        "range(start_batch * batch_size, size, batch_size)",
        "range(0, size, batch_size)",
        "test_sampler.py",
    ),
    (
        "supervision-side",
        "training/supervision.py",
        'return index if side == "b" else 728 - index',
        "return index",
        "test_supervision.py",
    ),
    (
        "supervision-value-sign",
        "training/supervision.py",
        "return math.tanh(score / VALUE_SCALE)",
        "return -math.tanh(score / VALUE_SCALE)",
        "test_supervision.py",
    ),
    (
        "supervision-played-move",
        "training/supervision.py",
        'action=move_action(teacher["best_move"], row["side"]),',
        'action=move_action(row["played_move"], row["side"]),',
        "test_supervision.py",
    ),
    (
        "supervision-completed-depth",
        "training/supervision.py",
        'valid = teacher is not None and teacher["completed_depth"] >= 1',
        'valid = teacher is not None and teacher["completed_depth"] >= 0',
        "test_supervision.py",
    ),
    (
        "supervision-duplicate-target",
        "training/supervision.py",
        'if row["duplicate_of"] is not None or row["termination"] is not None or not valid:',
        'if row["termination"] is not None or not valid:',
        "test_supervision.py",
    ),
    (
        "supervision-legal-actions",
        "training/supervision.py",
        'raise ValueError("legal moves and canonical IDs differ")',
        "pass",
        "test_supervision.py",
    ),
    (
        "supervision-source",
        "training/supervision.py",
        'raise ValueError("only search rows may have search teachers")',
        "pass",
        "test_supervision.py",
    ),
    (
        "supervision-leakage",
        "training/supervision.py",
        'raise ValueError("duplicate marker differs; possible cross-split leakage")',
        "pass",
        "test_supervision.py",
    ),
    (
        "supervision-empty-split",
        "training/supervision.py",
        'raise ValueError("every split requires nonduplicate search teachers")',
        "pass",
        "test_supervision.py",
    ),
    (
        "supervision-file-hash",
        "training/supervision.py",
        'raise ValueError("corpus file hash differs")',
        "pass",
        "test_supervision.py",
    ),
    (
        "supervision-manifest-inventory",
        "training/supervision.py",
        'raise ValueError("manifest differs from verified inventory")',
        "pass",
        "test_supervision.py",
    ),
    (
        "rental-small-cpu-quote",
        "training/rental_control.py",
        '"rtx59-3-24-750-xam.1": 86400',
        '"rtx59-3-24-750-xam.1": 43200',
        "test_rental_control.py",
    ),
    (
        "rental-existing-instance",
        "training/rental_control.py",
        'raise ValueError("another VoxelShogi rental is active")',
        "pass",
        "test_rental_control.py",
    ),
    (
        "release-data-contract",
        "training/production_release.py",
        'raise ValueError("production schema or ruleset differs")',
        "pass",
        "test_production_release.py",
    ),
    (
        "release-download-revision",
        "training/production_release.py",
        'revision=receipt["hub_commit"],',
        'revision="main",',
        "test_production_release.py",
    ),
    (
        "release-hub-parent",
        "training/production_release.py",
        'if not kwargs.get("revision") and info.sha != self.parent:',
        "if False:",
        "test_production_release.py",
    ),
    (
        "release-eligible-target",
        "training/production_release.py",
        'validation["eligible_rows"] < 100000',
        "False",
        "test_production_release.py",
    ),
    (
        "release-full-regeneration",
        "training/production_release.py",
        'report.get("regenerated_bytes_match") is not True',
        "False",
        "test_production_release.py",
    ),
    (
        "release-file-bytes",
        "training/production_release.py",
        'raise ValueError("production file hashes differ")',
        "pass",
        "test_production_release.py",
    ),
    (
        "rental-budget",
        "training/rental_control.py",
        "reserved + cap > 100",
        "False",
        "test_rental_control.py",
    ),
    (
        "rental-guardian-first",
        "training/rental_control.py",
        "start_guard()  # Must be alive before the API can create a paid resource.",
        "pass  # Mutation: do not start the independent guardian.",
        "test_rental_control.py",
    ),
    (
        "rental-ownership",
        "training/rental_control.py",
        'raise ValueError("instance ownership differs; refuse to terminate")',
        "pass",
        "test_rental_control.py",
    ),
    (
        "rental-deadline",
        "training/rental_control.py",
        'while self.clock() < limits["stop_at"]:',
        'while self.clock() <= limits["stop_at"]:',
        "test_rental_control.py",
    ),
    (
        "shogitter-hand-owner",
        "training/shogitter.py",
        "amount, side, kind = change",
        "side, amount, kind = change",
        "test_shogitter.py",
    ),
    (
        "shogitter-layer",
        "training/shogitter.py",
        "(packed_y - 1) // 9",
        "(packed_y - 1) // 8",
        "test_shogitter.py",
    ),
    (
        "shogitter-source-board",
        "training/shogitter.py",
        'if actual["board"] != board or actual["hands"] != hands:',
        "if False:",
        "test_shogitter.py",
    ),
    (
        "shogitter-capture-hand",
        "training/shogitter.py",
        "if hands != expected:",
        "if False:",
        "test_shogitter.py",
    ),
    (
        "hub-community-after-upload",
        "training/hub_release.py",
        'if (\n        api.community_disabled(repo_id=plan["repo_id"], repo_type=plan["repo_type"])\n        is not True\n    ):',
        "if False:",
        "test_hub_release.py",
    ),
    (
        "hub-community-disabled",
        "training/hub_release.py",
        "if api.community_disabled(**destination) is not True:",
        "if False:",
        "test_hub_release.py",
    ),
    (
        "hub-dataset-card",
        "training/hub_release.py",
        "if section is None or not section.group(1).strip():",
        "if False:",
        "test_hub_release.py",
    ),
    (
        "mutation-runtime-exclude",
        "scripts/ci/mutation-training.py",
        'stream.write("\\n/results.xml\\n")',
        "pass",
        "test_mutation_harness.py",
    ),
    (
        "production-opening-diversity",
        "training/production.py",
        "ply >= opening_plies",
        "True",
        "test_production.py",
    ),
    (
        "production-global-duplicate",
        "training/production.py",
        'row["duplicate_of"] = seen.get(key)',
        'row["duplicate_of"] = None',
        "test_production.py",
    ),
    (
        "production-regeneration-cost",
        "training/production.py",
        "generate_seconds + validate_seconds + regenerate_seconds",
        "generate_seconds + validate_seconds",
        "test_production.py",
    ),
    (
        "production-cost-approval",
        "training/production.py",
        'if not smoke and job.get("approved") is not True:',
        "if False:",
        "test_production.py",
    ),
    (
        "production-eligible-target",
        "training/production.py",
        '100000 if job["purpose"] == "production" else 1',
        '1 if job["purpose"] == "production" else 1',
        "test_production.py",
    ),
    (
        "hub-namespace",
        "training/hub_release.py",
        'r"voxelshogi/[A-Za-z0-9][A-Za-z0-9._-]*"',
        'r"[A-Za-z0-9]+/[A-Za-z0-9][A-Za-z0-9._-]*"',
        "test_hub_release.py",
    ),
    (
        "hub-public-creation",
        "training/hub_release.py",
        "api.create_repo(**destination, private=False)",
        "api.create_repo(**destination, private=True)",
        "test_hub_release.py",
    ),
    (
        "hub-manual-gate",
        "training/hub_release.py",
        'if info.private or info.gated != "manual":',
        "if info.private:",
        "test_hub_release.py",
    ),
    (
        "hub-reviewed-inventory",
        "training/hub_release.py",
        "if current != plan:",
        "if False:",
        "test_hub_release.py",
    ),
    (
        "hub-transfer-hash",
        "training/hub_release.py",
        'digest.hexdigest() != file["sha256"]',
        "False",
        "test_hub_release.py",
    ),
    (
        "pilot-selected-gpu",
        "training/pilot.py",
        'gpu["name"] not in names',
        "False",
        "test_pilot.py",
    ),
    (
        "pilot-vram-boundary",
        "training/pilot.py",
        '"rtx5090": ("RTX 5090", 30000)',
        '"rtx5090": ("RTX 5090", 29999)',
        "test_pilot.py",
    ),
    (
        "pilot-throughput",
        "training/pilot.py",
        '"samples_per_second": len(samples) / total',
        '"samples_per_second": teachers / total',
        "test_pilot.py",
    ),
    (
        "pilot-teacher-depth",
        "training/pilot.py",
        'sample["completed_depth"] >= 1',
        'sample["completed_depth"] >= 0',
        "test_pilot.py",
    ),
    (
        "pilot-single-gpu",
        "training/pilot.py",
        "len(rows) != 1",
        "len(rows) < 1",
        "test_pilot.py",
    ),
    (
        "pilot-linux-only",
        "training/pilot.py",
        'system != "linux"',
        'system not in ("linux", "darwin")',
        "test_pilot.py",
    ),
    (
        "atomic-initial-ownership",
        "training/data.py",
        "(directory / OWNER_FILE).touch(exist_ok=False)",
        "pass",
        "test_data.py",
    ),
    (
        "interrupted-group-cleanup",
        "training/runner.py",
        "if process is not None and not cleaned:",
        "if process is not None and process.poll() is None and not cleaned:",
        "test_runner.py",
    ),
    (
        "teacher-verification",
        "training/data.py",
        'if row["teacher"] != (canonical(teacher) if teacher is not None else None):',
        "if False:",
        "test_data.py",
    ),
    (
        "white-features",
        f"{PACKAGE}/__init__.py",
        "board = board[::-1]",
        "board = board",
        "test_engine.py",
    ),
    (
        "white-actions",
        f"{PACKAGE}/__init__.py",
        "else 728 - index",
        "else index",
        "test_engine.py",
    ),
    (
        "promoted-action",
        f"{PACKAGE}/__init__.py",
        '+ text.endswith("+")',
        "+ 0",
        "test_engine.py",
    ),
    (
        "actor-reward",
        f"{PACKAGE}/env.py",
        "1.0 if winner == actor else -1.0",
        "-1.0 if winner == actor else 1.0",
        "test_engine.py",
    ),
    (
        "resume-config",
        "training/data.py",
        "if old.value() != config.value():",
        "if False:",
        "test_data.py",
    ),
    (
        "shard-hash",
        "training/data.py",
        'if digest(directory / entry["file"]) != entry["sha256"]:',
        "if False:",
        "test_data.py",
    ),
    (
        "duplicate-exclusion",
        "training/data.py",
        'if row["duplicate_of"] != seen.get(key):',
        "if False:",
        "test_data.py",
    ),
    (
        "teacher-eligibility",
        "training/data.py",
        '"teacher_valid": teacher is not None\n                and teacher["completed_depth"] >= 1\n                and teacher["score"] is not None,',
        '"teacher_valid": teacher is not None,',
        "test_data.py",
    ),
    (
        "time-boundary",
        "training/runner.py",
        "if elapsed >= seconds:",
        "if elapsed > seconds:",
        "test_runner.py",
    ),
    (
        "rss-boundary",
        "training/runner.py",
        "if rss >= rss_limit",
        "if rss > rss_limit",
        "test_runner.py",
    ),
    (
        "session-budget",
        "training/runner.py",
        "if remaining <= 0:",
        "if remaining < 0:",
        "test_runner.py",
    ),
    (
        "pressure-stop",
        "training/runner.py",
        'if observation["pressure"]',
        "if False",
        "test_runner.py",
    ),
]


def prepare_baseline_checkout(work):
    if (work / ".git").exists():
        raise ValueError("mutation baseline must have its own new Git checkout")

    def git(*args):
        return subprocess.run(
            ["git", *args],
            cwd=work,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.strip()

    git("init", "--quiet", "--initial-branch=mutation-baseline")
    with (work / ".git/info/exclude").open("a") as stream:
        stream.write("\n/results.xml\n")
    git("add", ".")
    git(
        "-c",
        "user.name=VoxelShogi CI",
        "-c",
        "user.email=ci@voxelshogi.invalid",
        "commit",
        "--quiet",
        "-m",
        "Isolated mutation baseline",
    )
    return git("rev-parse", "HEAD")


def main():
    output = ROOT / "coverage/training-mutations"
    output.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(prefix="voxelshogi-training-mutations-") as tmp:
        work = Path(tmp)
        for name in ("pyproject.toml", "uv.lock", ".python-version", ".gitignore"):
            shutil.copy2(ROOT / name, work / name)
        for name in ("training", "export", "crates", "infrastructure"):
            shutil.copytree(
                ROOT / name,
                work / name,
                ignore=shutil.ignore_patterns("target", "pkg", "__pycache__", ".venv"),
            )
        (work / "scripts/ci").mkdir(parents=True)
        shutil.copy2(Path(__file__), work / "scripts/ci/mutation-training.py")
        prepare_baseline_checkout(work)
        env = {
            **os.environ,
            "UV_PROJECT_ENVIRONMENT": str(ROOT / ".venv"),
            "PYTHONPATH": os.pathsep.join(
                [str(work / "crates/voxelshogi-python/python"), str(work)]
            ),
            "PYTHONDONTWRITEBYTECODE": "1",
        }

        def run(name, tests=""):
            report = work / "results.xml"
            report.unlink(missing_ok=True)
            result = subprocess.run(
                [
                    "uv",
                    "run",
                    "--locked",
                    "--no-sync",
                    "pytest",
                    "-q",
                    f"training/tests/{tests}",
                    f"--junitxml={report}",
                ],
                cwd=work,
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            (output / f"{name}.log").write_text(result.stdout + result.stderr)
            suites = ET.parse(report).getroot()
            cases = suites.findall(".//testcase")
            failures, errors = suites.findall(".//failure"), suites.findall(".//error")
            if (
                result.returncode == 0
                and cases
                and not failures
                and not errors
                and not suites.findall(".//skipped")
            ):
                return "passed"
            if result.returncode == 1 and failures and not errors:
                return "caught"
            raise RuntimeError(
                f"{name}: collection/infrastructure/timeouts are not caught mutations"
            )

        assert run("baseline") == "passed"
        for name, file, before, after, tests in MUTATIONS:
            path = work / file
            original = path.read_text()
            # Eligibility is deliberately duplicated in the independent verifier;
            # mutate the producer only and let the verifier/tests detect it.
            assert original.count(before) == 1, f"stale/ambiguous mutation: {name}"
            try:
                path.write_text(original.replace(before, after, 1))
                outcome = run(name, tests)
                results.append({"name": name, "outcome": outcome})
                print(f"{name}: {outcome}", flush=True)
                assert outcome == "caught", f"surviving mutation: {name}"
            finally:
                path.write_text(original)
    (output / "results.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
