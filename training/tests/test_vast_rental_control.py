"""Pure provider/ledger fixtures; never rent hardware or execute models."""

import copy
import json

import pytest

from training.tests.test_m6_rental_control import setup as cloud_setup
from training.vast_rental_control import VastRental, quote_offer


def offer():
    return {
        "id": 123,
        "gpu_name": "RTX 5090",
        "num_gpus": 1,
        "gpu_ram": 32000,
        "cpu_ram": 49152,
        "cpu_cores_effective": 8,
        "disk_space": 160,
        "rentable": True,
        "rented": False,
        "verification": "verified",
        "reliability2": 0.999,
        "cuda_max_good": 13.0,
        "driver_version": "580.159.03",
        "dph_base": 0.5,
        "storage_total_cost": 0.08,
        "dph_total": 0.58,
        "inet_up_cost": 0,
        "inet_down_cost": 0,
        "direct_port_count": 2,
    }


class Provider:
    def __init__(self):
        self.calls = []
        self.offer = offer()
        self.rows = []
        self.pages = []
        self.fail_create = False
        self.retain_after_delete = False
        self.owner_id = 7
        self.balance = 10

    def __call__(self, method, path, data=None, params=None):
        self.calls.append((method, path, data, params))
        if path == "/api/v0/users/current":
            return {
                "id": self.owner_id,
                "balance": self.balance,
                "ssh_key": "never-save-this-account-key",
            }
        if path == "/api/v0/bundles":
            return {"offers": [copy.deepcopy(self.offer)]}
        if path == "/api/v1/instances":
            if self.pages:
                return self.pages.pop(0)
            return {
                "success": True,
                "instances": copy.deepcopy(self.rows),
                "instances_found": len(self.rows),
                "total_instances": len(self.rows),
                "next_token": None,
            }
        if path == "/api/v0/asks/123" and method == "PUT":
            self.rows = [
                {
                    "id": 456,
                    "label": data["label"],
                    "actual_status": "running",
                    "ssh_host": "host.invalid",
                    "ssh_port": 2200,
                    "jupyter_token": "must-not-be-recorded",
                }
            ]
            if self.fail_create:
                raise TimeoutError("observation expired")
            return {"success": True, "new_contract": 456, "id": 999}
        if path == "/api/v0/instances/456" and method == "DELETE":
            if not self.retain_after_delete:
                self.rows = []
            return {"success": True}
        if path == "/api/v0/instances/456/ssh" and method == "POST":
            return {"success": True}
        raise AssertionError((method, path, data, params))


def setup(tmp_path):
    cloud, _, budget, approval = cloud_setup(tmp_path)
    api = Provider()
    cross = []
    control = VastRental(
        cloud.state,
        api,
        tag="voxelshogi-m6-test",
        budget=budget,
        approval=approval,
        phase="trial",
        maximum_seconds=14400,
        clock=lambda: 1000,
        other_provider_idle=lambda: cross.append(True),
    )
    return control, api, budget, cross


def test_quote_is_total_hourly_compute_plus_requested_ephemeral_storage():
    result = quote_offer(offer())
    assert result == {
        "offer_id": 123,
        "gpu": "RTX 5090",
        "disk_gb": 80,
        "hourly_usd": 0.58,
        "maximum_seconds": 14400,
        "maximum_usd": 4,
        "bandwidth": "unmetered",
    }
    larger = offer()
    larger["dph_total"] = 0.5
    assert quote_offer(larger)["hourly_usd"] == 0.58


@pytest.mark.parametrize(
    "field,value",
    [
        ("gpu_name", "V100"),
        ("num_gpus", 2),
        ("gpu_ram", 12000),
        ("cpu_ram", 16000),
        ("cpu_cores_effective", 2),
        ("disk_space", 79),
        ("rentable", False),
        ("rented", True),
        ("verification", "unverified"),
        ("reliability2", 0.8),
        ("cuda_max_good", 12.9),
        ("driver_version", "570.1"),
        ("direct_port_count", 0),
        ("inet_up_cost", 0.001),
        ("inet_down_cost", 0.001),
        ("dph_base", 1.1),
        ("dph_total", 1.1),
        ("storage_total_cost", float("nan")),
    ],
)
def test_unquoted_hardware_price_or_transfer_fees_are_rejected(field, value):
    changed = offer()
    changed[field] = value
    with pytest.raises(ValueError):
        quote_offer(changed)


def test_guard_and_shared_reservation_precede_create_and_use_local_public_key(tmp_path):
    control, api, budget, cross = setup(tmp_path)
    ready_calls = []

    def ready():
        ready_calls.append(True)
        assert cross == [True]
        assert not any(method == "PUT" for method, *_ in api.calls)
        row = json.loads(budget.read_text())["reservations"][-1]
        assert row["task"] == "m6-trial" and row["maximum_usd"] == 4

    result = control.rent(123, ready)
    assert ready_calls == [True]
    assert result["instance_ids"] == [456]
    payload = next(data for method, path, data, _ in api.calls if method == "PUT")
    assert (
        payload["disk"] == 80
        and payload["label"] == "voxelshogi-m6-test"
        and payload["cancel_unavail"] is True
    )
    assert payload["runtype"] == "ssh_direct" and "HF_TOKEN" not in str(payload)
    assert json.loads((control.state / "deadline.json").read_text())["stop_at"] == 14500
    assert json.loads(budget.read_text())["reserved_total_usd"] == 45
    assert control.attach_key()["success"] is True
    assert api.calls[-1][2] == {"ssh_key": "ssh-ed25519 opaque fixture"}


def test_missing_approval_and_guard_failure_cannot_create_a_paid_instance(tmp_path):
    control, api, _, _ = setup(tmp_path)
    control.approval.unlink()
    with pytest.raises(ValueError):
        control.rent(123, lambda: None)
    assert api.calls == []


def test_guard_failure_and_an_existing_rental_prevent_create(tmp_path):
    control, api, _, _ = setup(tmp_path)

    def fail():
        raise RuntimeError("guard not ready")

    with pytest.raises(RuntimeError, match="guard"):
        control.rent(123, fail)
    assert not any(method == "PUT" for method, *_ in api.calls)


def test_paginated_owned_inventory_cannot_miss_a_second_page_voxelshogi_job(tmp_path):
    control, api, _, _ = setup(tmp_path)
    api.pages = [
        {
            "success": True,
            "instances": [{"id": 99, "label": "unrelated"}],
            "instances_found": 1,
            "total_instances": 2,
            "next_token": "next",
        },
        {
            "success": True,
            "instances": [{"id": 98, "label": "voxelshogi-m6-other"}],
            "instances_found": 1,
            "total_instances": 2,
            "next_token": None,
        },
    ]
    with pytest.raises(ValueError, match="existing"):
        control.rent(123, lambda: None)
    assert not any(method == "PUT" for method, *_ in api.calls)


def test_status_records_only_connection_metadata_and_stopped_is_not_released(tmp_path):
    control, api, _, _ = setup(tmp_path)
    control.rent(123, lambda: None)
    api.rows[0]["actual_status"] = "stopped"
    result = control.status()
    assert result["instances"][0]["actual_status"] == "stopped"
    assert "must-not-be-recorded" not in (control.state / "status.json").read_text()
    assert not (control.state / "terminal.json").exists()


def test_destroy_is_owned_and_requires_verified_absence_not_just_stopped(tmp_path):
    control, api, _, _ = setup(tmp_path)
    control.rent(123, lambda: None)
    api.rows[0]["label"] = "unrelated"
    with pytest.raises(ValueError, match="ownership"):
        control.terminate()
    assert not any(method == "DELETE" for method, *_ in api.calls)
    api.rows[0]["label"] = "voxelshogi-m6-test"
    api.rows[0]["actual_status"] = "stopped"
    result = control.terminate()
    assert result["complete"] is True
    assert json.loads((control.state / "terminal.json").read_text())["complete"] is True
    assert any(method == "DELETE" for method, *_ in api.calls)


def test_create_timeout_recovers_the_same_label_and_never_rents_twice(tmp_path):
    control, api, _, _ = setup(tmp_path)
    api.fail_create = True
    with pytest.raises(TimeoutError):
        control.rent(123, lambda: None)
    with pytest.raises(ValueError, match="request"):
        control.rent(123, lambda: None)
    result = control.terminate()
    assert result["complete"] is True
    assert sum(method == "PUT" for method, *_ in api.calls) == 1


def test_official_client_keeps_key_in_header_and_suppresses_error_body():
    import io
    import urllib.error

    from training.vast_rental_control import VastClient

    class Opener:
        def open(self, request, timeout):
            assert (
                request.full_url == "https://console.vast.ai/api/v1/instances?limit=25"
            )
            assert request.get_header("Authorization") == "Bearer opaque-key"
            assert timeout == 40
            return io.BytesIO(b'{"success":true}')

    client = VastClient("opaque-key", Opener())
    assert client("GET", "/api/v1/instances", params={"limit": 25}) == {"success": True}
    with pytest.raises(ValueError):
        client("GET", "https://other.invalid/api")

    class Failure:
        def open(self, *args, **kwargs):
            raise urllib.error.HTTPError(
                "https://console.vast.ai", 403, "secret body not for logs", {}, None
            )

    with pytest.raises(RuntimeError, match="^Vast.ai HTTP 403$"):
        VastClient("opaque-key", Failure())("GET", "/api/v1/instances")


def test_search_returns_only_narrow_quotes_without_raw_provider_metadata():
    from training.vast_rental_control import search_offers

    api = Provider()
    result = search_offers(api)
    assert result[0]["offer_id"] == 123 and "driver_version" not in result[0]
    assert api.calls[0][2]["allocated_storage"] == 80
    api.offer["inet_up_cost"] = 0.001
    assert search_offers(api) == []


def test_destroy_acknowledgement_does_not_hide_a_still_billed_stopped_instance(
    tmp_path,
):
    control, api, _, _ = setup(tmp_path)
    control.rent(123, lambda: None)
    api.rows[0]["actual_status"] = "stopped"
    api.retain_after_delete = True
    result = control.terminate()
    assert result["complete"] is False
    assert not (control.state / "terminal.json").exists()
    api.retain_after_delete = False
    assert control.terminate()["complete"] is True


def test_cross_provider_live_conflict_prevents_reservation_and_create(tmp_path):
    control, api, budget, _ = setup(tmp_path)

    def conflict():
        raise ValueError("existing CloudRift job")

    control.other_provider_idle = conflict
    with pytest.raises(ValueError, match="CloudRift"):
        control.rent(123, lambda: None)
    assert len(json.loads(budget.read_text())["reservations"]) == 1
    assert not any(method == "PUT" for method, *_ in api.calls)


def test_an_incomplete_inventory_is_not_proof_that_instances_are_absent(tmp_path):
    control, api, _, _ = setup(tmp_path)
    api.pages = [
        {
            "success": True,
            "instances": [],
            "instances_found": 0,
            "total_instances": 1,
            "next_token": None,
        }
    ]
    with pytest.raises(ValueError, match="incomplete"):
        control.rent(123, lambda: None)
    assert not any(method == "PUT" for method, *_ in api.calls)


def test_vast_quote_cannot_extend_the_four_hour_allocation(tmp_path):
    control, api, _, _ = setup(tmp_path)
    control.maximum_seconds = 7200
    with pytest.raises(ValueError, match="four hours"):
        control.rent(123, lambda: None)
    assert api.calls == []


def test_changed_api_account_cannot_prove_a_previous_instance_was_deleted(tmp_path):
    control, api, _, _ = setup(tmp_path)
    control.rent(123, lambda: None)
    api.owner_id = 8
    api.rows = []
    with pytest.raises(ValueError, match="account"):
        control.terminate()
    assert not (control.state / "terminal.json").exists()


def test_insufficient_live_balance_does_not_reserve_or_create(tmp_path):
    control, api, budget, _ = setup(tmp_path)
    api.balance = 0
    with pytest.raises(ValueError, match="balance"):
        control.rent(123, lambda: None)
    assert len(json.loads(budget.read_text())["reservations"]) == 1
    assert not any(method == "PUT" for method, *_ in api.calls)


@pytest.mark.parametrize(
    "field",
    [
        "gpu_ram",
        "cpu_ram",
        "cpu_cores_effective",
        "disk_space",
        "reliability2",
        "cuda_max_good",
        "direct_port_count",
    ],
)
def test_unknown_nonfinite_hardware_facts_do_not_form_a_quote(field):
    item = offer()
    item[field] = float("nan")
    with pytest.raises(ValueError):
        quote_offer(item)
