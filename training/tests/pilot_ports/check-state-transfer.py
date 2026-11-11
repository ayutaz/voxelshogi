"""Opaque small-file HF ports only: never decode or publish an actual state."""

import json
import runpy
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from training.feature_cache import file_hash
from training.research_visit_fit import VisitRunConfig
from training.tests.test_hub_release import Hub
from training.tests.test_research_state_release import research_package

module = runpy.run_path("infrastructure/research/pilot/state_transfer.py")


class FakeHub(Hub):
    def repo_info(self, **kwargs):
        self.calls.append(("info", kwargs))
        return SimpleNamespace(private=self.private, gated=self.gated, sha="c" * 40)


def fixture(root):
    folder = root / "archive"
    binding = research_package(folder)
    binding.update(
        config=VisitRunConfig().value(),
        environment={"device": "cuda"},
        contract={
            "schema": "voxelshogi-research-visit-training-v1",
            "admission_sha256": "d" * 64,
        },
    )
    (folder / "config.json").write_text(
        json.dumps({"schema": "voxelshogi-training-run-v1", "binding": binding})
    )
    manifest = json.loads((folder / "manifest.json").read_text())
    manifest["binding"] = binding
    for entry in manifest["files"]:
        if entry["path"] == "config.json":
            entry.update(
                bytes=(folder / "config.json").stat().st_size,
                sha256=file_hash(folder / "config.json"),
            )
    (folder / "manifest.json").write_text(json.dumps(manifest))
    budget = root / "budget.json"
    budget.write_text(
        json.dumps(
            {
                "schema": "voxelshogi-state-upload-budget-v1",
                "approved_maximum_new_bytes": 1024**3,
                "reservations": [],
            }
        )
    )
    return folder, binding, budget


for mode in ("complete", "corrupt-fetch", "community-on", "expired", "duplicate"):
    with tempfile.TemporaryDirectory(prefix="voxelshogi-pilot-state-fake-") as td:
        root = Path(td)
        folder, binding, budget = fixture(root)
        api, fetched, restored = FakeHub(), [], []
        if mode == "community-on":
            api.community_disabled = lambda **kw: False

        def fetch(**kw):
            assert kw["repo_id"] == "voxelshogi/voxelshogi-research-training-state-v1"
            assert kw["revision"] == "c" * 40
            fetched.append(kw["filename"])
            if mode == "corrupt-fetch" and kw["filename"] == "latest/state.safetensors":
                bad = root / "bad"
                bad.write_bytes(b"bad")
                return bad
            return folder / kw["filename"]

        def restore(archive, output, **kw):
            assert kw == {"expected_binding": binding, "profile": "research"}
            assert (archive / "manifest.json").exists()
            restored.append(str(output))
            return json.loads((archive / "manifest.json").read_text())

        control = root / "transfer"
        if mode == "duplicate":
            control.mkdir()
            (control / "publication-attempt.json").write_text("{}")
        with (
            patch.object(module["sys"], "platform", "linux"),
            patch("training.resume_archive.restore_run", side_effect=restore),
        ):
            try:
                result = module["publish_restore"](
                    folder,
                    control,
                    root / "restored",
                    api=api,
                    fetch=fetch,
                    upload_budget=budget,
                    deadline=time.time() + (-1 if mode == "expired" else 60),
                )
            except ValueError, FileExistsError, InterruptedError:
                assert mode != "complete"
                assert not restored
                if mode in ("expired", "duplicate"):
                    assert api.calls == []
            else:
                assert mode == "complete"
                assert result["receipt"]["verified"] and result["restored"]
                assert len(fetched) == result["verified_files"] == 7
                assert len(restored) == 1
                assert len(json.loads(budget.read_text())["reservations"]) == 1
try:
    module["publish_restore"](
        "opaque",
        "opaque",
        "opaque",
        api=None,
        fetch=None,
        upload_budget=None,
        deadline=1,
    )
except ValueError as error:
    assert "external Linux" in str(error)
else:
    raise AssertionError("Mac reached state publication")
print(
    "Five fake state transfers: fixed-revision all-file verification, ledger, community, corruption, expiry and duplicate rejection; actual HF/checkpoint operations0"
)
