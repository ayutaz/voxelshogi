"""Publication transactions over opaque fixtures; no GPU, tensors or Hub access."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from training.checkpoint import atomic_json
from training.feature_cache import file_hash
from training.tests.test_hub_release import Hub
from training.tests.test_selfplay_archive_policy import archive_fixture
from training.tests.test_selfplay_dataset import manifest


def staged(tmp_path):
    from training.hub_release import plan_release

    run, stage = tmp_path / "run", tmp_path / "stage"
    run.mkdir()
    (run / ".voxelshogi-selfplay-run-v1").touch()
    stage.mkdir()
    m = manifest()
    atomic_json(run / "run.json", m["run"])
    data, state = stage / "dataset", stage / "state"
    data.mkdir()
    (data / "episodes.parquet").write_bytes(b"opaque Parquet fixture")
    m["file"].update(
        bytes=(data / "episodes.parquet").stat().st_size,
        sha256=file_hash(data / "episodes.parquet"),
    )
    atomic_json(data / "manifest.json", m)
    atomic_json(data / "validation.json", {"complete": True})
    (data / "LICENSE").write_text("CC-BY-4.0 fixture")
    (data / "README.md").write_text(
        "---\nlicense: cc-by-4.0\n---\n"
        + "\n".join(
            f"## {title}\nOpaque fixture, not published.\n"
            for title in (
                "Generation and provenance",
                "Usage and schema",
                "Verification",
                "Access and license",
            )
        )
    )
    binding = archive_fixture(state)
    binding.update(source_commit="1" * 40, cache_sha256="4" * 64)
    binding["contract"].update(
        source_commit="1" * 40,
        parent_model_sha256="a" * 64,
        architecture="transformer-s-full-v1",
    )
    atomic_json(
        state / "config.json",
        {
            "schema": "voxelshogi-training-run-v1",
            "binding": binding,
        },
    )
    sm = json.loads((state / "manifest.json").read_text())
    sm["binding"] = binding
    sm["roles"]["latest"]["progress"] = m["run"]["generations"][0]["training_progress"]
    for entry in sm["files"]:
        entry.update(
            bytes=(state / entry["path"]).stat().st_size,
            sha256=file_hash(state / entry["path"]),
        )
    atomic_json(state / "manifest.json", sm)
    (state / "LICENSE").write_text("Apache-2.0 fixture")
    (state / "README.md").write_text(
        "---\nlicense: apache-2.0\n---\n"
        + "\n".join(
            f"## {title}\nOpaque fixture, not published.\n"
            for title in (
                "Training and provenance",
                "Resume contents",
                "Verification",
                "Access and license",
            )
        )
    )
    plans = {
        "dataset": plan_release(
            data,
            repo_id="voxelshogi/voxelshogi-selfplay-v1",
            repo_type="dataset",
            license_id="cc-by-4.0",
            license_approved=True,
            source_commit="1" * 40,
        ),
        "state": plan_release(
            state,
            repo_id="voxelshogi/voxelshogi-transformer-s-selfplay-training-state-v1",
            repo_type="model",
            license_id="apache-2.0",
            license_approved=True,
            source_commit="1" * 40,
            artifact_role="selfplay-training-state",
            state_publication_approved=True,
            expected_binding=binding,
        ),
    }
    atomic_json(
        stage / "bundle.json",
        {
            "schema": "voxelshogi-selfplay-release-v1",
            "run": m["run"],
            "plans": plans,
        },
    )
    budget = tmp_path / "budget.json"
    atomic_json(
        budget,
        {
            "schema": "voxelshogi-state-upload-budget-v1",
            "approved_maximum_new_bytes": 1024**3,
            "reservations": [],
        },
    )
    return run, stage, budget


class Remote(Hub):
    def repo_info(self, **kwargs):
        return SimpleNamespace(private=False, gated="manual", sha="c" * 40)


def execute(run, stage, budget, api=None, fetch=None):
    from training.selfplay_release import publish_staged

    def local_fetch(**kw):
        assert kw["revision"] == "c" * 40
        return (
            stage
            / ("dataset" if kw["repo_type"] == "dataset" else "state")
            / kw["filename"]
        )

    return publish_staged(
        run, stage, api or Remote(), fetch or local_fetch, upload_budget=budget
    )


@pytest.fixture(autouse=True)
def metadata_linux(monkeypatch):
    # Opaque bytes only; actual pack/restore is covered by Linux native tests.
    from training import hub_release, selfplay_release

    monkeypatch.setattr(selfplay_release.sys, "platform", "linux")
    monkeypatch.setattr(hub_release.platform, "system", lambda: "Linux")


def test_pair_commits_only_after_all_remote_hashes_and_does_not_resend(tmp_path):
    run, stage, budget = staged(tmp_path)
    api = Remote()
    pair = execute(run, stage, budget, api)
    saved = json.loads((run / "run.json").read_text())
    assert len(saved["publications"]) == 1
    assert saved["publications"][0] == {"generation": 0, **pair}
    assert all(r["verified"] and r["community_disabled"] for r in pair.values())
    assert len([n for n, _ in api.calls if n == "upload"]) == 2
    assert len(json.loads(budget.read_text())["reservations"]) == 1
    again = execute(run, stage, budget, api)
    assert again == pair
    assert len([n for n, _ in api.calls if n == "upload"]) == 2


def test_failed_hash_keeps_cursor_and_reverifies_without_upload(tmp_path):
    run, stage, budget = staged(tmp_path)
    api = Remote()
    bad = tmp_path / "bad"
    bad.write_bytes(b"broken remote artifact")

    def fail(**kw):
        return bad

    with pytest.raises(ValueError, match="hash"):
        execute(run, stage, budget, api, fail)
    assert json.loads((run / "run.json").read_text())["publications"] == []
    assert len([n for n, _ in api.calls if n == "upload"]) == 1
    execute(run, stage, budget, api)
    assert len([n for n, _ in api.calls if n == "upload"]) == 2


def test_unknown_upload_outcome_never_blindly_retries(tmp_path):
    run, stage, budget = staged(tmp_path)

    class Interrupted(Remote):
        def upload_folder(self, **kw):
            super().upload_folder(**kw)
            raise OSError("transport interrupted after submission")

    with pytest.raises(OSError):
        execute(run, stage, budget, Interrupted())
    api = Remote()
    with pytest.raises(ValueError, match="audit"):
        execute(run, stage, budget, api)
    assert api.calls == []
    assert json.loads((run / "run.json").read_text())["publications"] == []


@pytest.mark.parametrize(
    "change",
    ["source", "input", "parent", "generation", "progress", "destination", "local"],
)
def test_wrong_binding_or_changed_stage_has_no_remote_side_effects(tmp_path, change):
    run, stage, budget = staged(tmp_path)
    path = stage / "bundle.json"
    bundle = json.loads(path.read_text())
    binding = bundle["plans"]["state"]["expected_binding"]
    if change == "source":
        bundle["plans"]["dataset"]["source_commit"] = "e" * 40
    elif change == "input":
        binding["cache_sha256"] = "e" * 64
    elif change == "parent":
        binding["contract"]["parent_model_sha256"] = "e" * 64
    elif change == "generation":
        binding["contract"]["generation"] = 1
    elif change == "progress":
        sm = json.loads((stage / "state/manifest.json").read_text())
        sm["roles"]["latest"]["progress"]["step"] += 1
        atomic_json(stage / "state/manifest.json", sm)
    elif change == "destination":
        bundle["plans"]["dataset"]["repo_id"] = "voxelshogi/wrong-run"
    else:
        (stage / "dataset/episodes.parquet").write_bytes(b"changed")
    if change in ("input", "parent", "generation", "progress"):
        # Keep each archive/plan internally valid. Only the cross-artifact
        # generation binding should reject this otherwise publishable state.
        from training.hub_release import plan_release

        sm = json.loads((stage / "state/manifest.json").read_text())
        sm["binding"] = binding
        atomic_json(
            stage / "state/config.json",
            {
                "schema": "voxelshogi-training-run-v1",
                "binding": binding,
            },
        )
        for entry in sm["files"]:
            entry.update(
                bytes=(stage / "state" / entry["path"]).stat().st_size,
                sha256=file_hash(stage / "state" / entry["path"]),
            )
        atomic_json(stage / "state/manifest.json", sm)
        old = bundle["plans"]["state"]
        bundle["plans"]["state"] = plan_release(
            stage / "state",
            repo_id=old["repo_id"],
            repo_type="model",
            license_id="apache-2.0",
            license_approved=True,
            source_commit="1" * 40,
            artifact_role="selfplay-training-state",
            state_publication_approved=True,
            expected_binding=binding,
        )
    atomic_json(path, bundle)
    api = Remote()
    with pytest.raises(ValueError):
        execute(run, stage, budget, api)
    assert api.calls == []


def test_concurrent_run_change_is_rejected_before_cursor_commit(tmp_path):
    run, stage, budget = staged(tmp_path)
    before = json.loads((run / "run.json").read_text())

    class Racing(Remote):
        def upload_folder(self, **kw):
            after = deepcopy(before)
            after["complete"] = True
            atomic_json(run / "run.json", after)
            return super().upload_folder(**kw)

    with pytest.raises(ValueError, match="changed"):
        execute(run, stage, budget, Racing())
    assert json.loads((run / "run.json").read_text())["publications"] == []


def test_mac_refused_before_artifact_reads(monkeypatch, tmp_path):
    from training import selfplay_release

    monkeypatch.setattr(selfplay_release.sys, "platform", "darwin")
    with pytest.raises(ValueError, match="Linux"):
        selfplay_release.publish_staged(
            tmp_path, tmp_path, None, None, upload_budget=None
        )
