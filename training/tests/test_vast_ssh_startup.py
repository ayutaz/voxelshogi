"""Actual small shell with a fake filesystem root; never contact a provider."""

import stat
import subprocess

import pytest


def apply_with_fake_root(script, folder, key):
    folder.mkdir()
    authorized = folder / "authorized_keys"
    previous = "ssh-ed25519 previously-authorized owner\n"
    authorized.write_text(previous)
    folder.chmod(0o755)
    authorized.chmod(0o644)
    # Only the destination path is a fake port; run the actual generated shell.
    sandboxed = script.replace("/root/.ssh", str(folder))
    for _ in range(2):
        subprocess.run(["/bin/sh", "-c", sandboxed], check=True)
    assert authorized.read_text() == previous + key + "\n"
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    assert stat.S_IMODE(authorized.stat().st_mode) == 0o600


def test_startup_preserves_other_keys_is_idempotent_and_quotes_comments(tmp_path):
    from training.vast_rental_control import ssh_onstart

    marker = tmp_path / "injected"
    key = f"ssh-ed25519 opaque comment'; touch {marker}; #"
    script = ssh_onstart(key)
    apply_with_fake_root(script, tmp_path / "ssh", key)
    assert not marker.exists()


@pytest.mark.parametrize(
    "key", ["", "ssh-rsa opaque", "ssh-ed25519 opaque\nsecond", "ssh-ed25519 x\ry"]
)
def test_startup_rejects_wrong_type_or_multiple_lines(key):
    from training.vast_rental_control import ssh_onstart

    with pytest.raises(ValueError):
        ssh_onstart(key)


def test_m6_create_installs_the_task_public_key_in_the_owned_container(tmp_path):
    from training.tests.test_vast_rental_control import setup

    control, api, _, _ = setup(tmp_path)
    control.rent(123, lambda: None)
    payload = next(data for method, _, data, _ in api.calls if method == "PUT")
    apply_with_fake_root(
        payload["onstart"], tmp_path / "ssh", "ssh-ed25519 opaque fixture"
    )


def test_research_create_installs_the_task_public_key_in_the_owned_container(tmp_path):
    from training.tests.test_vast_research_control import setup

    control, api, _, _ = setup(tmp_path)
    control.rent(lambda: None)
    payload = next(data for method, _, data, _ in api.calls if method == "PUT")
    apply_with_fake_root(
        payload["onstart"], tmp_path / "ssh", "ssh-ed25519 opaque-fixture"
    )
