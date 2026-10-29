"""Private IP allocation uses the provider's shared SSH mapping; no real rentals."""

import json

import pytest

from training.tests.test_m6_rental_control import setup

SKU = "rtx59-7-23-800-ig.1"
DC = "ap_northeast_kr_se_1"


def korean_provider(base):
    def api(path, data):
        response = base(path, data)
        if path.endswith("instance-types/list"):
            row = response["instance_types"][0]["variants"][0]
            row.update(
                name=SKU,
                cost_per_hour=65,
                available_nodes_per_dc={DC: 1},
                ip_availability_per_dc={DC: {"public_ips": False}},
            )
        return response

    return api


def test_m6_can_quote_korean_shared_ip_rental_with_ssh_port_and_same_four_hour_cap(
    tmp_path,
):
    control, api, budget, _ = setup(tmp_path, sku=SKU)
    control.api = korean_provider(api)
    result = control.rent(lambda: None)
    assert result["instance_ids"] == ["owned"]
    request = next(data for path, data in api.calls if path.endswith("instances/rent"))
    assert request["selector"]["ByInstanceTypeAndLocation"] == {
        "instance_type": SKU,
        "datacenters": [DC],
    }
    assert request["with_public_ip"] is False
    assert request["config"]["VirtualMachine"]["ports"] == ["22"]
    preflight = json.loads((control.state / "preflight.json").read_text())
    assert preflight["datacenter"] == DC and preflight["cost_per_hour_cents"] == 65
    row = json.loads(budget.read_text())["reservations"][-1]
    assert row["maximum_usd"] == 4 and row["maximum_seconds"] == 14400
    assert (
        json.loads((control.state / "deadline.json").read_text())["hourly_usd"] == 0.65
    )


def test_the_same_shared_ip_sku_is_not_an_implicit_m4_quote(tmp_path):
    from training.tests.test_rental_control import setup as setup_m4

    control, api, _ = setup_m4(tmp_path)
    control.sku = SKU
    control.api = korean_provider(api)
    with pytest.raises(ValueError, match="quote"):
        control.rent(lambda: None)
    assert api.calls == []


def test_old_public_ip_mode_does_not_silently_switch_to_shared_ip(tmp_path):
    control, api, _, _ = setup(tmp_path)

    def no_public(path, data):
        response = api(path, data)
        if path.endswith("instance-types/list"):
            response["instance_types"][0]["variants"][0]["ip_availability_per_dc"] = {
                "na_west_us_gr_1": {"public_ips": False}
            }
        return response

    control.api = no_public
    with pytest.raises(ValueError, match="IP"):
        control.rent(lambda: None)
    assert not any(path.endswith("instances/rent") for path, _ in api.calls)


def test_guard_namespace_keeps_the_actual_shared_ip_sku():
    from training.rental_control import guard_command

    command = guard_command("state", "budget", purpose="m6", sku=SKU)
    assert command[command.index("--sku") + 1] == SKU
    assert command[command.index("--purpose") + 1] == "m6"
