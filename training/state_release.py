"""Separately approved resume archive metadata, never a normal model release."""

import fcntl
import hashlib
import json
import os
import re
from pathlib import Path

from training.resume_archive import verify_archive

MAXIMUM_NEW_BYTES = 1024**3


def reserve_state_upload(path, plan):
    from training.hub_release import _canonical

    if path is None:
        raise ValueError("training-state upload budget is required")
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError("invalid training-state upload budget")
    release = hashlib.sha256(_canonical(plan).encode()).hexdigest()
    amount = sum(file["bytes"] for file in plan["files"])
    with path.open("r+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        value = json.load(stream)
        reservations = value.get("reservations")
        if (
            value.get("schema") != "voxelshogi-state-upload-budget-v1"
            or type(value.get("approved_maximum_new_bytes")) is not int
            or value["approved_maximum_new_bytes"] != MAXIMUM_NEW_BYTES
            or not isinstance(reservations, list)
            or any(
                set(row) != {"release_sha256", "maximum_bytes"}
                or not isinstance(row["release_sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", row["release_sha256"])
                or type(row["maximum_bytes"]) is not int
                or row["maximum_bytes"] <= 0
                for row in reservations
            )
        ):
            raise ValueError("unapproved or invalid training-state upload budget")
        if any(row["release_sha256"] == release for row in reservations):
            raise ValueError(
                "state upload already reserved; audit instead of resending"
            )
        if (
            sum(row["maximum_bytes"] for row in reservations) + amount
            > MAXIMUM_NEW_BYTES
        ):
            raise ValueError("training-state upload budget exceeded")
        reservations.append({"release_sha256": release, "maximum_bytes": amount})
        stream.seek(0)
        json.dump(value, stream, indent=2)
        stream.truncate()
        stream.flush()
        os.fsync(stream.fileno())


def state_inventory(folder, plan, card):
    folder = Path(folder)
    for title in (
        "Training and provenance",
        "Resume contents",
        "Verification",
        "Access and license",
    ):
        section = re.search(
            rf"^## {re.escape(title)}[ \t]*\n(.*?)(?=^## |\Z)",
            card,
            re.MULTILINE | re.DOTALL,
        )
        if section is None or not section.group(1).strip():
            raise ValueError(f"State Card requires a populated section: {title}")
    manifest = verify_archive(
        folder,
        expected_binding=plan["expected_binding"],
        profile="selfplay"
        if plan["artifact_role"] == "selfplay-training-state"
        else "m6",
    )
    expected = {name: None for name in ("manifest.json", "README.md", "LICENSE")}
    if (folder / "NOTICE").exists():
        expected["NOTICE"] = None
    for name in ("README.md", "LICENSE", "NOTICE"):
        path = folder / name
        if path.exists() and (path.is_symlink() or path.stat().st_size > 1024 * 1024):
            raise ValueError("invalid training-state notice")
    for entry in manifest["files"]:
        expected[entry["path"]] = entry
    return expected
