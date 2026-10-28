"""No provider access: record one rental and its independent deadline guardian."""

import json

import pytest


class Provider:
    def __init__(self):
        self.calls = []
        self.price = 100
        self.sku = "rtx59-7-48-750-xam.1"
        self.rows = []

    def __call__(self, path, data):
        self.calls.append((path, data))
        if path.endswith("instance-types/list"):
            return {
                "instance_types": [
                    {
                        "variants": [
                            {
                                "name": self.sku,
                                "cost_per_hour": self.price,
                                "gpu_count": 1,
                                "available_nodes_per_dc": {"na_west_us_gr_1": 1},
                                "ip_availability_per_dc": {
                                    "na_west_us_gr_1": {"public_ips": True}
                                },
                            }
                        ]
                    }
                ]
            }
        if path.endswith("instances/rent"):
            self.rows = [
                {
                    "id": "owned",
                    "tags": ["voxelshogi-m4-production-test"],
                    "status": "Active",
                    "resources_released": False,
                }
            ]
            return {"instance_ids": ["owned"]}
        if path.endswith("instances/list"):
            selector = data["selector"]
            if selector.get("ByTags") == {"all": [], "any": []}:
                return {
                    "instances": []
                }  # Official API: empty tag selector matches nothing.
            return {"instances": self.rows}
        if path.endswith("instances/terminate"):
            self.rows[0].update(status="Inactive", resources_released=True)
            return {}
        raise AssertionError(path)


def setup(tmp_path):
    from training.rental_control import Rental

    state = tmp_path / "state"
    state.mkdir()
    (state / "id_ed25519.pub").write_text("ssh-ed25519 fixture test")
    budget = tmp_path / "budget.json"
    budget.write_text(
        json.dumps(
            {
                "approved_total_usd": 100,
                "reservations": [{"maximum_usd": 5}],
                "reserved_total_usd": 5,
                "remaining_unreserved_usd": 95,
            }
        )
    )
    api = Provider()
    return (
        Rental(
            state,
            api,
            tag="voxelshogi-m4-production-test",
            budget=budget,
            clock=lambda: 1000,
        ),
        api,
        budget,
    )


def test_guard_starts_before_one_rental_and_budget_includes_prior_attempts(tmp_path):
    control, api, budget = setup(tmp_path)

    def guard():
        assert not any(path.endswith("instances/rent") for path, _ in api.calls)
        assert (control.state / "deadline.json").exists()

    result = control.rent(guard)
    deadline = json.loads((control.state / "deadline.json").read_text())
    assert result["instance_ids"] == ["owned"]
    assert deadline["stop_at"] == 43300 and deadline["maximum_end_at"] == 44200
    b = json.loads(budget.read_text())
    assert b["reserved_total_usd"] == 17 and b["remaining_unreserved_usd"] == 83
    payload = next(d for p, d in api.calls if p.endswith("instances/rent"))
    assert payload["config"]["VirtualMachine"]["ports"] == ["22"]
    with pytest.raises(ValueError):
        control.rent(guard)
    assert sum(p.endswith("instances/rent") for p, _ in api.calls) == 1


def test_price_or_remaining_budget_stops_before_rental(tmp_path):
    control, api, budget = setup(tmp_path)
    api.price = 101
    with pytest.raises(ValueError):
        control.rent(lambda: None)
    assert not any(p.endswith("instances/rent") for p, _ in api.calls)
    api.price = 100
    b = json.loads(budget.read_text())
    b["reservations"] = [{"maximum_usd": 90}]
    budget.write_text(json.dumps(b))
    with pytest.raises(ValueError):
        control.rent(lambda: None)
    assert not any(p.endswith("instances/rent") for p, _ in api.calls)


def test_missing_guard_never_creates_a_paid_instance(tmp_path):
    control, api, _ = setup(tmp_path)

    def broken_guard():
        raise RuntimeError("guardian failed")

    with pytest.raises(RuntimeError):
        control.rent(broken_guard)
    assert not any(p.endswith("instances/rent") for p, _ in api.calls)


def test_smaller_cpu_quote_has_one_day_limit_and_reserves_24_dollars(tmp_path):
    control, api, budget = setup(tmp_path)
    api.sku = "rtx59-3-24-750-xam.1"
    control.sku = api.sku
    result = control.rent(lambda: None)
    assert result["stop_at"] == 86500  # 1000 + 23 h 45 min.
    deadline = json.loads((control.state / "deadline.json").read_text())
    assert deadline["maximum_end_at"] == 87400
    b = json.loads(budget.read_text())
    assert b["reserved_total_usd"] == 29 and b["remaining_unreserved_usd"] == 71
    payload = next(d for p, d in api.calls if p.endswith("instances/rent"))
    assert payload["selector"]["ByInstanceTypeAndLocation"]["instance_type"] == api.sku


def test_termination_requires_owned_id_and_real_resource_release(tmp_path):
    control, api, _ = setup(tmp_path)
    control.rent(lambda: None)
    api.rows[0]["tags"] = ["unrelated"]
    with pytest.raises(ValueError):
        control.terminate()
    assert not any(p.endswith("instances/terminate") for p, _ in api.calls)
    api.rows[0]["tags"] = ["voxelshogi-m4-production-test"]
    result = control.terminate()
    assert result["complete"] and result["instances"][0]["resources_released"] is True
    api.rows = []
    assert control.terminate()["complete"] is False  # Empty list is not proof.


def test_lost_rental_response_is_recovered_by_tag_before_termination(tmp_path):
    control, api, _ = setup(tmp_path)
    control.rent(lambda: None)
    (control.state / "rent-response.json").unlink()
    assert control.terminate()["complete"] is True
    assert json.loads((control.state / "rent-response.json").read_text())[
        "instance_ids"
    ] == ["owned"]


def test_guard_does_not_contact_provider_until_the_deadline(tmp_path):
    control, api, _ = setup(tmp_path)
    control.rent(lambda: None)
    (control.state / "deadline.json").write_text(
        json.dumps({"stop_at": 20, "maximum_end_at": 30})
    )
    now = [0]
    control.clock = lambda: now[0]

    def pause(seconds):
        now[0] += seconds

    control.pause = pause
    original = control.api

    observed = []

    def checked_api(path, data):
        observed.append(now[0])
        return original(path, data)

    control.api = checked_api
    control.guard()
    assert observed and all(t == 20 for t in observed)
    assert json.loads((control.state / "terminal.json").read_text())["complete"] is True


@pytest.mark.parametrize("status", ["Initializing", "Active", "Deactivating"])
def test_any_existing_project_rental_blocks_a_second_instance(tmp_path, status):
    control, api, budget = setup(tmp_path)
    api.rows = [
        {
            "id": "older",
            "tags": ["voxelshogi-older-task"],
            "status": status,
            "resources_released": False,
        }
    ]
    with pytest.raises(ValueError, match="another"):
        control.rent(lambda: None)
    assert not any(path.endswith("instances/rent") for path, _ in api.calls)
    assert json.loads(budget.read_text())["reserved_total_usd"] == 5
