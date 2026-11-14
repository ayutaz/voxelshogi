"""Only Card/settings may change; no model files are staged by this operation."""

import hashlib
import unittest
from types import SimpleNamespace

from training.public_s_release import ROOT, prepare_public_s_card, publish_public_s_card


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
