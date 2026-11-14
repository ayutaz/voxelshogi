"""Metadata-only opening of the already published S inference package.

Does not stage/download weights on the Mac. Linux must subsequently verify the
full immutable package using hub_release.verify_release before web publication.
"""

import hashlib
import json
import re
from pathlib import Path

from training.hub_release import PUBLIC_S_PROFILE, PUBLIC_S_REPO, _canonical, _policy

ROOT = Path(__file__).resolve().parents[1]


def prepare_public_s_card(card):
    approval = json.loads((ROOT / "export/public-s-approval.json").read_text())
    if (
        approval["inference_repository"] != PUBLIC_S_REPO
        or approval["access_profile"] != PUBLIC_S_PROFILE
        or approval["gated"] is not False
        or approval["browser_download_approved"] is not True
        or approval["community_disabled"] is not True
    ):
        raise ValueError("explicit public S approval is required")
    encoded = card.encode("utf-8")
    if not 1 <= len(encoded) <= 8192 or not card.startswith(
        "---\nlicense: apache-2.0\n"
    ):
        raise ValueError("concise Apache-2.0 Model Card required")
    for title in (
        "Training and provenance",
        "Evaluation",
        "Inference",
        "Access and license",
    ):
        if not re.search(rf"^## {title}\n\n\S", card, re.MULTILINE):
            raise ValueError("complete concise Model Card required")
    previous = json.loads(
        (ROOT / "docs/experiments/m6-portable-release.json").read_text()
    )["publication"]
    plan = {**previous["plan"], "gated": False, "access_profile": PUBLIC_S_PROFILE}
    plan["files"] = [
        {
            "path": "README.md",
            "bytes": len(encoded),
            "sha256": hashlib.sha256(encoded).hexdigest(),
        }
        if f["path"] == "README.md"
        else dict(f)
        for f in plan["files"]
    ]
    _policy(plan)
    return plan, previous["receipt"]["hub_commit"]


def publish_public_s_card(card, api, *, execute=False):
    plan, parent = prepare_public_s_card(card)
    receipt = {
        "dry_run": not execute,
        "verified": False,
        "release_sha256": hashlib.sha256(_canonical(plan).encode()).hexdigest(),
    }
    if not execute:
        return plan, receipt
    destination = {"repo_id": PUBLIC_S_REPO, "repo_type": "model"}
    who = api.whoami()
    if who["name"] != "ayousanz" or not any(
        org["name"] == "voxelshogi" for org in who.get("orgs", [])
    ):
        raise ValueError("expected HF account/organization required")
    info = api.repo_info(**destination)
    if info.private or info.sha != parent:
        raise ValueError("public S base revision changed; review before updating")
    api.update_repo_settings(**destination, gated=False)
    api.disable_community(**destination)
    if (
        api.repo_info(**destination).gated is not False
        or api.community_disabled(**destination) is not True
    ):
        raise ValueError("ungated public S / Community OFF not confirmed")
    commit = api.upload_file(
        **destination,
        path_or_fileobj=card.encode("utf-8"),
        path_in_repo="README.md",
        parent_commit=parent,
        commit_message="Open S inference downloads and simplify the Model Card",
    )
    return plan, {
        **receipt,
        **destination,
        "hub_commit": commit.oid,
        "metadata_only": True,
    }
