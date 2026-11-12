"""Tiny opaque file transfer fixtures; no models, native games or generation."""

import hashlib
import json

import pytest


def raw(value):
    return (json.dumps(value, sort_keys=True) + "\n").encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def setup(tmp_path, monkeypatch):
    from training import research_release_staging as module

    monkeypatch.setattr(module.sys, "platform", "linux")
    converted, evaluated = tmp_path / "converted", tmp_path / "evaluated"
    converted.mkdir()
    evaluated.mkdir()
    payloads = {
        "model.safetensors": b"opaque original weights",
        "selection.json": b'{"opaque":"selection"}\n',
        "training-history.jsonl": b'{"opaque":"history"}\n',
        "final-protocol.json": b'{"opaque":"frozen"}\n',
        "input-audit.json": b'{"opaque":"audit"}\n',
    }
    payloads.update(
        {
            p + ".onnx": (p + " actual opaque bytes").encode()
            for p in ("fp32", "fp16", "int8")
        }
    )
    payloads.update(
        {
            "inputs/" + n + ".f32": n.encode()
            for n in ("initial-b", "after-one-w", "mate-in-one-b", "material-b")
        }
    )
    payloads.update(
        {
            f"reference/{p}/{n}-{o}.f32": (p + n + o).encode()
            for p in ("fp32", "fp16", "int8")
            for n in ("initial-b", "after-one-w", "mate-in-one-b", "material-b")
            for o in ("policy", "value")
        }
    )
    payloads.update(
        {f"evaluation/{p}.json": raw({"opaque": p}) for p in ("fp32", "fp16", "int8")}
    )
    assert len(payloads) == 39
    descriptors = {
        n: {"path": n, "bytes": len(b), "sha256": sha(b)} for n, b in payloads.items()
    }
    evaluation_names = {
        "final-protocol.json",
        "input-audit.json",
        "evaluation/fp32.json",
        "evaluation/fp16.json",
        "evaluation/int8.json",
    }
    for name, body in payloads.items():
        path = (evaluated if name in evaluation_names else converted) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    manifest = {
        "sourceCommit": "f" * 40,
        "research": {"architecture": {"architecture": "full"}},
        "opaque": "three formats retained",
    }
    manifest_raw = raw(manifest)
    (evaluated / "assembled-manifest.json").write_bytes(manifest_raw)
    (evaluated / "complete.json").write_bytes(
        raw(
            {
                "schema": "voxelshogi-research-final-evaluation-v1",
                "complete": True,
                "games": 72,
                "queries": 6,
                "source_commit": "f" * 40,
                "assembled_manifest_sha256": sha(manifest_raw),
                "input_audit_sha256": sha(payloads["input-audit.json"]),
                "frozen_sha256": sha(payloads["final-protocol.json"]),
                "inference_publication_approved": False,
            }
        )
    )
    card = tmp_path / "reviewed-card.md"
    card_raw = b"---\nlicense: apache-2.0\n---\n# Reviewed opaque card\n"
    card.write_bytes(card_raw)
    calls = []

    def review(value, *, source_commit, selection, history, frozen, reports, audit):
        assert value == manifest and source_commit == "f" * 40
        assert (
            selection == {"opaque": "selection"}
            and history == payloads["training-history.jsonl"]
        )
        assert frozen == {"opaque": "frozen"} and audit == {"opaque": "audit"}
        assert reports == {p: {"opaque": p} for p in ("fp32", "fp16", "int8")}
        calls.append("review")
        return {
            "README.md": None,
            "LICENSE": None,
            "manifest.json": None,
            **descriptors,
        }

    def plan(folder, **options):
        calls.append("plan")
        assert options == {
            "repo_id": "voxelshogi/voxelshogi-research-m-full-v1",
            "repo_type": "model",
            "license_id": "apache-2.0",
            "license_approved": True,
            "source_commit": "f" * 40,
            "artifact_role": "research-inference-package",
        }
        actual = {
            p.relative_to(folder).as_posix(): p.read_bytes()
            for p in folder.rglob("*")
            if p.is_file()
        }
        assert actual == {
            **payloads,
            "README.md": card_raw,
            "LICENSE": module.LICENSE.read_bytes(),
            "manifest.json": manifest_raw,
        }
        return {
            "files": [
                {"path": n, "bytes": len(b), "sha256": sha(b)}
                for n, b in sorted(actual.items())
            ],
            **options,
        }

    def clock():
        return clock.now

    clock.now = 100
    options = {
        "frozen": evaluated / "final-protocol.json",
        "manifest_sha256": sha(manifest_raw),
        "card_sha256": sha(card_raw),
        "expected_source": "f" * 40,
        "deadline": 200,
        "clock": clock,
        "ports": {"source": lambda: "f" * 40, "review": review, "plan": plan},
    }
    return (
        module,
        converted,
        evaluated,
        card,
        tmp_path / "stage",
        options,
        payloads,
        calls,
    )


def test_staging_preserves_all_42_exact_payloads_and_uses_typed_harness(
    tmp_path, monkeypatch
):
    module, converted, evaluated, card, output, options, payloads, calls = setup(
        tmp_path, monkeypatch
    )
    result = module.stage_release(converted, evaluated, card, output, **options)
    assert result["complete"] is True and result["files"] == 42
    assert result["uploaded"] is False and result["catalog_registered"] is False
    assert calls == ["review", "plan"]
    assert not (output / "pending").exists()
    assert {
        p.relative_to(output / "package").as_posix()
        for p in (output / "package").rglob("*")
        if p.is_file()
    } == {*payloads, "README.md", "LICENSE", "manifest.json"}
    assert result["plan_sha256"] == sha((output / "release-plan.json").read_bytes())
    assert json.loads((output / "complete.json").read_text()) == result


def test_default_ports_route_to_source_review_and_shared_publication_harness(
    tmp_path, monkeypatch
):
    module, converted, evaluated, card, output, options, _, calls = setup(
        tmp_path, monkeypatch
    )
    ports = options.pop("ports")
    monkeypatch.setattr(module, "source_commit", ports["source"])
    monkeypatch.setattr(module, "review_manifest", ports["review"])
    monkeypatch.setattr(module, "plan_release", ports["plan"])
    result = module.stage_release(converted, evaluated, card, output, **options)
    assert result["files"] == 42 and calls == ["review", "plan"]


@pytest.mark.parametrize(
    "fault",
    [
        "manifest-hash",
        "card-hash",
        "source",
        "expired",
        "stop",
        "platform",
        "existing-output",
    ],
)
def test_unfrozen_preflight_never_promotes_package(tmp_path, monkeypatch, fault):
    module, converted, evaluated, card, output, options, _, _ = setup(
        tmp_path, monkeypatch
    )
    error = ValueError
    if fault == "manifest-hash":
        options["manifest_sha256"] = "0" * 64
        receipt_path = evaluated / "complete.json"
        receipt = json.loads(receipt_path.read_bytes())
        receipt["assembled_manifest_sha256"] = "0" * 64
        receipt_path.write_bytes(raw(receipt))
    elif fault == "card-hash":
        options["card_sha256"] = "0" * 64
    elif fault == "source":
        options["expected_source"] = "e" * 40
    elif fault == "expired":
        options["deadline"] = 99
        error = InterruptedError
    elif fault == "stop":
        options["stop_requested"] = lambda: True
        error = InterruptedError
    elif fault == "platform":
        monkeypatch.setattr(module.sys, "platform", "darwin")
    else:
        output.mkdir()
    with pytest.raises(error):
        module.stage_release(converted, evaluated, card, output, **options)
    assert not (output / "package").exists()
    assert not (output / "complete.json").exists()


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "hash",
        "size",
        "symlink",
        "parent-link",
        "escaped-path",
        "unknown-path",
        "changed-source",
        "changed-card",
        "changed-source-file",
        "copy-corruption",
        "deadline-during-copy",
        "plan-failure",
    ],
)
def test_incomplete_or_changed_files_preserve_failure_without_release(
    tmp_path, monkeypatch, fault
):
    module, converted, evaluated, card, output, options, _, _ = setup(
        tmp_path, monkeypatch
    )
    target = converted / "int8.onnx"
    if fault == "missing":
        target.unlink()
    elif fault == "hash":
        body = target.read_bytes()
        target.write_bytes(bytes([body[0] ^ 1]) + body[1:])
    elif fault == "size":
        target.write_bytes(target.read_bytes() + b"x")
    elif fault == "symlink":
        body = target.read_bytes()
        target.unlink()
        other = tmp_path / "same-bytes"
        other.write_bytes(body)
        target.symlink_to(other)
    elif fault == "parent-link":
        reference = converted / "reference"
        moved = tmp_path / "moved-reference"
        reference.rename(moved)
        reference.symlink_to(moved, target_is_directory=True)
    elif fault in ("escaped-path", "unknown-path"):
        original = options["ports"]["review"]

        def changed_review(*args, **kwargs):
            value = original(*args, **kwargs)
            value["../escape" if fault == "escaped-path" else "unexpected.bin"] = {
                "path": "int8.onnx",
                "bytes": 1,
                "sha256": "0" * 64,
            }
            return value

        options["ports"]["review"] = changed_review
    elif fault == "plan-failure":

        def bad_plan(*args, **kwargs):
            raise ValueError("typed harness rejected incomplete card")

        options["ports"]["plan"] = bad_plan
    else:
        original = module.shutil.copyfile
        changed = False

        def copied(source, destination):
            nonlocal changed
            result = original(source, destination)
            if not changed:
                changed = True
                if fault == "changed-source":
                    options["ports"]["source"] = lambda: "e" * 40
                elif fault == "changed-card":
                    card.write_bytes(b"changed reviewed card")
                elif fault == "changed-source-file":
                    source.write_bytes(source.read_bytes() + b"changed")
                elif fault == "copy-corruption":
                    destination.write_bytes(destination.read_bytes() + b"changed")
                else:
                    options["clock"].now = 201
            return result

        monkeypatch.setattr(module.shutil, "copyfile", copied)
    error = InterruptedError if fault == "deadline-during-copy" else ValueError
    with pytest.raises(error):
        module.stage_release(converted, evaluated, card, output, **options)
    assert not (output / "package").exists()
    assert not (output / "complete.json").exists()
    assert json.loads((output / "failure.json").read_text())["complete"] is False


@pytest.mark.parametrize(
    "field",
    [
        "complete",
        "games",
        "queries",
        "source_commit",
        "assembled_manifest_sha256",
        "input_audit_sha256",
        "frozen_sha256",
        "inference_publication_approved",
    ],
)
def test_final_completion_receipt_must_bind_same_finished_evaluation(
    tmp_path, monkeypatch, field
):
    module, converted, evaluated, card, output, options, _, _ = setup(
        tmp_path, monkeypatch
    )
    path = evaluated / "complete.json"
    value = json.loads(path.read_bytes())
    value[field] = {
        "complete": False,
        "games": 71,
        "queries": 0,
        "source_commit": "e" * 40,
        "assembled_manifest_sha256": "0" * 64,
        "input_audit_sha256": "0" * 64,
        "frozen_sha256": "0" * 64,
        "inference_publication_approved": True,
    }[field]
    path.write_bytes(raw(value))
    with pytest.raises(ValueError):
        module.stage_release(converted, evaluated, card, output, **options)
    assert not (output / "package").exists() and not (output / "complete.json").exists()
