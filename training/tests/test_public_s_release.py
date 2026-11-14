"""Only Card/settings may change; no model files are staged by this operation."""

import hashlib
import unittest
from types import SimpleNamespace

from training.public_s_release import (
    ROOT,
    prepare_public_s_card,
    publish_public_s_card,
    repair_public_s_card,
)


class Hub:
    def __init__(self):
        self.calls = []
        self.private, self.gated = False, "manual"
        self.sha = "f196c75236f0f0cfd028b91661b39a2c64ee448f"

    def whoami(self):
        return {"name": "ayousanz", "orgs": [{"name": "voxelshogi"}]}

    def repo_info(self, **kwargs):
        return SimpleNamespace(private=self.private, gated=self.gated, sha=self.sha)

    def update_repo_settings(self, **kwargs):
        self.calls.append(("settings", kwargs))
        self.gated = kwargs["gated"]

    def disable_community(self, **kwargs):
        self.calls.append(("community", kwargs))

    def community_disabled(self, **kwargs):
        return True

    def upload_file(self, **kwargs):
        self.calls.append(("upload", kwargs))
        return SimpleNamespace(oid="a" * 40)

    def commit_public_s_card(self, *, card, parent_commit):
        return self.upload_file(
            repo_id="voxelshogi/voxelshogi-transformer-s",
            path_in_repo="README.md",
            parent_commit=parent_commit,
            path_or_fileobj=card,
        ).oid


class PublicSReleaseTests(unittest.TestCase):
    def setUp(self):
        self.card = (ROOT / "export/public-s-model-card.md").read_text()

    def test_preserves_all_existing_weight_and_reference_hashes(self):
        plan, parent = prepare_public_s_card(self.card)
        files = {file["path"]: file for file in plan["files"]}
        self.assertEqual(len(files), 37)
        self.assertEqual(parent, "f196c75236f0f0cfd028b91661b39a2c64ee448f")
        self.assertEqual(
            files["fp32.onnx"]["sha256"],
            "8bd7bd91e38d7319f72b87495f63f0a86a85f3759d22913f787d963834b92e63",
        )
        self.assertEqual(
            files["README.md"]["sha256"], hashlib.sha256(self.card.encode()).hexdigest()
        )
        self.assertIs(plan["gated"], False)

    def test_dry_run_has_no_external_effect_and_execute_uploads_only_the_card(self):
        api = Hub()
        _, receipt = publish_public_s_card(self.card, api)
        self.assertEqual(api.calls, [])
        self.assertIs(receipt["verified"], False)
        _, receipt = publish_public_s_card(self.card, api, execute=True)
        self.assertEqual(
            [name for name, _ in api.calls], ["settings", "community", "upload"]
        )
        upload = api.calls[-1][1]
        self.assertEqual(upload["path_in_repo"], "README.md")
        self.assertEqual(
            upload["parent_commit"], "f196c75236f0f0cfd028b91661b39a2c64ee448f"
        )
        self.assertEqual(upload["repo_id"], "voxelshogi/voxelshogi-transformer-s")
        self.assertIs(
            receipt["verified"], False
        )  # Full Linux download verification still required.

    def test_wrong_account_changed_base_or_private_repo_are_not_mutated(self):
        for field, value in [
            ("private", True),
            ("sha", "b" * 40),
            ("whoami", lambda: {"name": "other"}),
        ]:
            api = Hub()
            setattr(api, field, value)
            with self.assertRaises(ValueError):
                publish_public_s_card(self.card, api, execute=True)
            self.assertEqual(api.calls, [])

    def test_failed_settings_confirmation_blocks_card_upload(self):
        api = Hub()
        api.community_disabled = lambda **kwargs: False
        with self.assertRaises(ValueError):
            publish_public_s_card(self.card, api, execute=True)
        self.assertFalse(any(name == "upload" for name, _ in api.calls))

    def test_incomplete_or_oversized_card_is_rejected(self):
        for card in [
            "incomplete",
            self.card.replace("## Evaluation", "## Missing"),
            self.card + "x" * 8192,
        ]:
            with self.assertRaises(ValueError):
                prepare_public_s_card(card)

    def test_ungated_profile_cannot_apply_to_another_repository(self):
        from training.hub_release import _policy

        plan, _ = prepare_public_s_card(self.card)
        for change in (
            {"repo_id": "voxelshogi/other"},
            {"repo_type": "dataset"},
            {"access_profile": None},
        ):
            with self.assertRaises(ValueError):
                _policy({**plan, **change})

    def repair_fixture(self):
        api = Hub()
        plan, receipt = publish_public_s_card(self.card, api, execute=True)
        tree = [
            SimpleNamespace(rfilename=f["path"], size=f["bytes"], blob_id="b" * 40)
            for f in plan["files"]
        ]
        tree.append(
            SimpleNamespace(rfilename=".gitattributes", size=50, blob_id="c" * 40)
        )
        api.repo_info = lambda **kwargs: SimpleNamespace(
            private=False,
            gated=False,
            sha=kwargs.get("revision", receipt["hub_commit"]),
            siblings=tree,
        )
        api.commit_public_s_card = lambda **kwargs: (
            api.calls.append(("repair", kwargs)) or "d" * 40
        )
        api.calls.clear()
        return api, {"plan": plan, "receipt": receipt}, tree

    def test_one_readback_correction_only_uploads_card_against_our_unchanged_tree(self):
        api, failed, _ = self.repair_fixture()
        plan, receipt = repair_public_s_card(self.card, api, failed)
        self.assertEqual(
            api.calls,
            [("repair", {"card": self.card.encode(), "parent_commit": "a" * 40})],
        )
        self.assertEqual(receipt["hub_commit"], "d" * 40)
        self.assertIs(receipt["verified"], False)
        with self.assertRaises(ValueError):
            repair_public_s_card(self.card, api, {"plan": plan, "receipt": receipt})

    def test_correction_rejects_changed_or_empty_tree(self):
        for empty in [False, True]:
            api, failed, tree = self.repair_fixture()
            baseline = list(tree)
            if empty:
                tree.clear()
            else:
                tree[0] = SimpleNamespace(
                    rfilename=tree[0].rfilename, size=tree[0].size, blob_id="e" * 40
                )
            api.repo_info = lambda **kwargs: SimpleNamespace(
                private=False,
                gated=False,
                sha=kwargs.get("revision", "a" * 40),
                siblings=baseline if "revision" in kwargs else tree,
            )
            with self.assertRaises(ValueError):
                repair_public_s_card(self.card, api, failed)
            self.assertEqual(api.calls, [])

    def test_explicit_card_commit_has_one_regular_readme_and_an_immutable_parent(self):
        import base64
        import json

        from training.hub_release import PublicationApi

        posts = []
        response = SimpleNamespace(
            raise_for_status=lambda: None, json=lambda: {"commitOid": "d" * 40}
        )
        session = SimpleNamespace(
            post=lambda *args, **kwargs: posts.append((args, kwargs)) or response
        )
        api = PublicationApi(None, session, {})
        self.assertEqual(
            api.commit_public_s_card(card=self.card.encode(), parent_commit="a" * 40),
            "d" * 40,
        )
        args, kwargs = posts[0]
        self.assertEqual(
            args,
            (
                "https://huggingface.co/api/models/voxelshogi/voxelshogi-transformer-s/commit/main",
            ),
        )
        records = [json.loads(line) for line in kwargs["content"].decode().splitlines()]
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["value"]["parentCommit"], "a" * 40)
        self.assertEqual(records[1]["key"], "file")
        self.assertEqual(records[1]["value"]["path"], "README.md")
        self.assertEqual(
            base64.b64decode(records[1]["value"]["content"]), self.card.encode()
        )

    def test_correction_can_restore_only_the_exact_card_misplaced_at_fp32(self):
        api, failed, tree = self.repair_fixture()
        baseline = list(tree)
        i = next(i for i, f in enumerate(tree) if f.rfilename == "fp32.onnx")
        descriptor = next(
            f for f in failed["plan"]["files"] if f["path"] == "fp32.onnx"
        )
        baseline[i] = SimpleNamespace(
            rfilename="fp32.onnx",
            size=descriptor["bytes"],
            blob_id="b" * 40,
            lfs=SimpleNamespace(sha256=descriptor["sha256"]),
        )
        tree[i] = SimpleNamespace(
            rfilename="fp32.onnx",
            size=len(self.card.encode()),
            blob_id="e" * 40,
            lfs=SimpleNamespace(sha256=hashlib.sha256(self.card.encode()).hexdigest()),
        )
        api.repo_info = lambda **kwargs: SimpleNamespace(
            private=False,
            gated=False,
            sha=kwargs.get("revision", "a" * 40),
            siblings=baseline if "revision" in kwargs else tree,
        )
        _, receipt = repair_public_s_card(self.card, api, failed)
        self.assertIs(receipt["restored_original_fp32"], True)
        self.assertEqual(
            api.calls[-1][1]["restore_fp32"],
            {
                "bytes": 20461391,
                "sha256": "8bd7bd91e38d7319f72b87495f63f0a86a85f3759d22913f787d963834b92e63",
            },
        )
        tree[i].lfs.sha256 = "0" * 64
        api.calls.clear()
        with self.assertRaises(ValueError):
            repair_public_s_card(self.card, api, failed)
        self.assertEqual(api.calls, [])
