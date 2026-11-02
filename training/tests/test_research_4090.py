"""Independent quote and payload expectations for the Taiwan single-4090 VM."""

import json

import pytest

from training.tests.test_research_rental_control import setup


def candidate(tmp_path):
    control, provider, budget, path = setup(tmp_path)
    plan = json.loads(path.read_text())
    plan.update(
        sku="rtx49-18-80-450-kn-packed.1",
        datacenter="ap-east-tw-kn-2",
        with_public_ip=False,
    )
    path.write_text(json.dumps(plan))

    def api(endpoint, data):
        response = provider(endpoint, data)
        if endpoint.endswith("instance-types/list"):
            response["instance_types"][0]["variants"][0].update(
                name="rtx49-18-80-450-kn-packed.1",
                cost_per_hour=39,
                available_nodes_per_dc={"ap-east-tw-kn-2": 2},
                ip_availability_per_dc={"ap-east-tw-kn-2": {"public_ips": False}},
            )
        return response

    control.api = api
    return control, provider, budget, path


def test_single_4090_uses_quoted_region_shared_ip_and_existing_guards(tmp_path):
    control, provider, budget, _ = candidate(tmp_path)
    guards = []

    def ready():
        assert not any(p.endswith("instances/rent") for p, _ in provider.calls)
        guards.append(True)

    control.rent(ready)
    catalog = next(d for p, d in provider.calls if p.endswith("instance-types/list"))
    assert catalog == {
        "selector": {
            "ByServiceAndLocation": {
                "services": ["vm"],
                "datacenters": ["ap-east-tw-kn-2"],
            }
        }
    }
    request = next(d for p, d in provider.calls if p.endswith("instances/rent"))
    assert request["selector"] == {
        "ByInstanceTypeAndLocation": {
            "instance_type": "rtx49-18-80-450-kn-packed.1",
            "datacenters": ["ap-east-tw-kn-2"],
        }
    }
    assert request["with_public_ip"] is False
    assert request["config"]["VirtualMachine"]["ports"] == ["22"]
    assert guards == [True]
    assert json.loads(budget.read_text())["reserved_total_usd"] == 65
    deadline = json.loads((control.state / "deadline.json").read_text())
    assert deadline["hourly_usd"] == 0.39
    assert deadline["maximum_end_at"] == 15340


@pytest.mark.parametrize(
    "change",
    [
        {"datacenter": "na_west_us_gr_1"},
        {"with_public_ip": True},
        {"sku": "rtx49-18-80-450-kn-packed.2"},
    ],
)
def test_4090_quote_cannot_change_region_ip_or_gpu_count(tmp_path, change):
    control, provider, budget, path = candidate(tmp_path)
    plan = json.loads(path.read_text())
    plan.update(change)
    path.write_text(json.dumps(plan))
    before = budget.read_bytes()
    with pytest.raises(ValueError, match="hardware/location/IP"):
        control.rent(lambda: None)
    assert provider.calls == [] and budget.read_bytes() == before


def test_4090_cannot_omit_live_independent_guard(tmp_path):
    control, provider, budget, _ = candidate(tmp_path)
    control.remote_guard = None
    before = budget.read_bytes()
    with pytest.raises(ValueError, match="independent"):
        control.rent(lambda: None)
    assert provider.calls == [] and budget.read_bytes() == before
