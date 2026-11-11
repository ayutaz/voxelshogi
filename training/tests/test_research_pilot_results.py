"""Metadata/result byte preservation and HF harness through fake ports only."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from training.checkpoint import atomic_json
from training.evaluation_v2 import fingerprint
from training.feature_cache import file_hash
from training.tests.test_hub_release import Hub
from training.tests.test_research_pilot_workflow import setup


def fixture(tmp_path, monkeypatch):
    value, _, _, _ = setup(tmp_path, monkeypatch)
    base = Path(value["job"]["base"])
    (base / "input-m4").mkdir()
    license = base / "input-m4/LICENSE"
    license.write_text("Opaque independently fixed CC-BY-4.0 fixture\n")
    value["m4_bundle"]["plan"]["license"] = "cc-by-4.0"
    entry = next(
        e for e in value["m4_bundle"]["plan"]["files"] if e["path"] == "LICENSE"
    )
    entry.update(bytes=license.stat().st_size, sha256=file_hash(license))
    value["m4_bundle"]["receipt"]["release_sha256"] = fingerprint(
        value["m4_bundle"]["plan"]
    )
    atomic_json(
        Path("docs/experiments/m4-production-release-2026-10-29.json"),
        {"publication": {**value["m4_bundle"], "complete": True}},
    )
    atomic_json(base / "workflow-request.json", {"workflow_sha256": fingerprint(value)})
    atomic_json(
        base / "workflow-compute.json",
        {"pipeline_complete": False, "source_commit": "a" * 40},
    )
    atomic_json(base / "state-budget-final.json", {"opaque": "bounded ledger fixture"})
    (base / "full/continuous").mkdir(parents=True)
    (base / "full/continuous/events.jsonl").write_text(
        '{"step":1,"note":"日本語"}\n{"step":2}\n'
    )
    (base / "full/continuous/secret.env").write_text("never include unrelated files")
    (base / "full/continuous/model.safetensors").write_bytes(
        b"never relay checkpoint weights"
    )
    return value, base


def opaque_writer(rows, target):
    target.write_bytes(json.dumps(rows, ensure_ascii=False).encode())


def test_partial_results_preserve_exact_json_bytes_and_only_declared_paths(
    tmp_path, monkeypatch
):
    from infrastructure.research.pilot.results import build_results

    value, base = fixture(tmp_path, monkeypatch)
    with patch("sys.platform", "linux"):
        manifest = build_results(
            value,
            base,
            base / "publication",
            pipeline_complete=False,
            writer=opaque_writer,
        )
    folder = base / "publication"
    rows = json.loads((folder / "records.parquet").read_bytes())
    lines = [r for r in rows if r["path"] == "full/continuous/events.jsonl"]
    assert [r["line"] for r in lines] == [0, 1]
    assert (
        "".join(r["content"] for r in lines).encode()
        == (base / "full/continuous/events.jsonl").read_bytes()
    )
    assert all(
        hashlib.sha256(r["content"].encode()).hexdigest() == r["sha256"] for r in rows
    )
    assert all(
        "secret" not in r["path"] and not r["path"].endswith("safetensors")
        for r in rows
    )
    assert len(rows) == 5 and manifest["record_count"] == 5
    assert (
        manifest["pipeline_complete"] is False
        and manifest["scientific_pilots_completed"] == 0
    )
    assert set(p.name for p in folder.iterdir()) == {
        "records.parquet",
        "manifest.json",
        "validation.json",
        "README.md",
        "LICENSE",
        "NOTICE",
        "config.json",
    }
    card = (folder / "README.md").read_text()
    for title in (
        "Generation and provenance",
        "Usage and schema",
        "Verification",
        "Access and license",
    ):
        assert "## " + title in card
    assert "5" in card and "manual" in card and "not" in card
    assert (folder / "LICENSE").read_bytes() == (base / "input-m4/LICENSE").read_bytes()


@pytest.mark.parametrize(
    "mode",
    [
        "symlink",
        "parent-symlink",
        "nan",
        "license",
        "duplicate",
        "mac",
        "complete-without-evidence",
        "oversize",
        "wrong-root",
    ],
)
def test_result_pack_rejects_unsafe_or_unproved_inputs(tmp_path, monkeypatch, mode):
    from infrastructure.research.pilot import results

    value, base = fixture(tmp_path, monkeypatch)
    events = base / "full/continuous/events.jsonl"
    if mode == "symlink":
        events.unlink()
        events.symlink_to(tmp_path / "elsewhere")
    elif mode == "parent-symlink":
        target = tmp_path / "elsewhere"
        (base / "full").rename(target)
        (base / "full").symlink_to(target, target_is_directory=True)
    elif mode == "nan":
        events.write_text('{"loss":NaN}\n')
    elif mode == "license":
        (base / "input-m4/LICENSE").write_bytes(
            b"x" * (base / "input-m4/LICENSE").stat().st_size
        )
    elif mode == "duplicate":
        (base / "publication").mkdir()
    elif mode == "oversize":
        monkeypatch.setattr(results, "MAX_SOURCE_BYTES", 1)
    with (
        patch("sys.platform", "darwin" if mode == "mac" else "linux"),
        pytest.raises((ValueError, FileExistsError)),
    ):
        results.build_results(
            value,
            tmp_path if mode == "wrong-root" else base,
            base / "publication",
            pipeline_complete=mode == "complete-without-evidence",
            writer=opaque_writer,
        )


@pytest.mark.parametrize(
    "mode", ["complete", "corrupt-download", "ambiguous-upload", "expired"]
)
def test_result_publication_uses_fixed_revision_verification_once(
    tmp_path, monkeypatch, mode
):
    from infrastructure.research.pilot import job, results

    value, base = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(job, "check_source", lambda source: None)
    monkeypatch.setattr(results, "write_records", opaque_writer)

    class FakeHub(Hub):
        uploaded = False

        def repo_info(self, **kwargs):
            return SimpleNamespace(
                private=False, gated="manual", sha=("c" if self.uploaded else "b") * 40
            )

        def upload_folder(self, **kwargs):
            self.uploaded = True
            if mode == "ambiguous-upload":
                self.calls.append(("upload", kwargs))
                raise TimeoutError("unknown upload outcome")
            return super().upload_folder(**kwargs)

    api = FakeHub()

    def fetch(**kwargs):
        assert kwargs["repo_id"] == "voxelshogi/voxelshogi-research-pilot-results-v1"
        assert kwargs["repo_type"] == "dataset" and kwargs["revision"] == "c" * 40
        if mode == "corrupt-download" and kwargs["filename"] == "records.parquet":
            wrong = tmp_path / "corrupt"
            wrong.write_text("changed")
            return wrong
        return base / "publication" / kwargs["filename"]

    with patch("sys.platform", "linux"):
        if mode == "complete":
            result = results.publish_results(
                value,
                base,
                pipeline_complete=False,
                api=api,
                fetch=fetch,
                deadline=300,
                clock=lambda: 100,
            )
            assert (
                result["receipt"]["verified"] is True
                and result["pipeline_complete"] is False
            )
        else:
            with pytest.raises((ValueError, InterruptedError, TimeoutError)):
                results.publish_results(
                    value,
                    base,
                    pipeline_complete=False,
                    api=api,
                    fetch=fetch,
                    deadline=300,
                    clock=lambda: 300 if mode == "expired" else 100,
                )
        with pytest.raises((FileExistsError, ValueError)):
            results.publish_results(
                value,
                base,
                pipeline_complete=False,
                api=api,
                fetch=fetch,
                deadline=300,
                clock=lambda: 100,
            )
    if mode == "expired":
        assert not (base / "publication").exists()
    uploads = [c for c in api.calls if c[0] == "upload"]
    assert len(uploads) == (0 if mode == "expired" else 1)


def test_jsonl_unicode_separator_is_content_and_source_race_is_detected(
    tmp_path, monkeypatch
):
    from infrastructure.research.pilot.results import build_results

    value, base = fixture(tmp_path, monkeypatch)
    path = base / "full/continuous/events.jsonl"
    original = '{"note":"before\u2028after"}\n'.encode()
    path.write_bytes(original)
    captured = []

    def writer(rows, output):
        captured.extend(rows)
        opaque_writer(rows, output)

    with patch("sys.platform", "linux"):
        build_results(
            value, base, base / "publication", pipeline_complete=False, writer=writer
        )
    lines = [r for r in captured if r["path"].endswith("events.jsonl")]
    assert len(lines) == 1 and lines[0]["content"].encode() == original


def test_result_pack_rechecks_source_after_parquet_write(tmp_path, monkeypatch):
    from infrastructure.research.pilot.results import build_results

    value, base = fixture(tmp_path, monkeypatch)

    def racing_writer(rows, output):
        opaque_writer(rows, output)
        (base / "full/continuous/events.jsonl").write_text('{"changed":true}\n')

    with patch("sys.platform", "linux"), pytest.raises(ValueError, match="changed"):
        build_results(
            value,
            base,
            base / "publication",
            pipeline_complete=False,
            writer=racing_writer,
        )


def test_result_json_rejects_overflowing_floats():
    from infrastructure.research.pilot.results import finite_json

    with pytest.raises(ValueError):
        finite_json('{"loss":1e999}')


def test_partial_card_does_not_count_an_unverified_complete_filename(
    tmp_path, monkeypatch
):
    from infrastructure.research.pilot.results import build_results

    value, base = fixture(tmp_path, monkeypatch)
    atomic_json(base / "full/complete.json", {"scientific_pilots": 0})
    with patch("sys.platform", "linux"):
        result = build_results(
            value,
            base,
            base / "publication",
            pipeline_complete=False,
            writer=opaque_writer,
        )
    assert result["scientific_pilots_completed"] == 0
