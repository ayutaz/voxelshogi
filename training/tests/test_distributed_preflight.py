"""Four physical devices, independently selected and probed; fake ports only."""

from copy import deepcopy

import pytest

from training.tests.test_cuda_preflight import facts


def inventory():
    return [
        {
            "uuid": f"GPU-00000000-0000-0000-0000-{i:012d}",
            "name": "NVIDIA GeForce RTX 5090",
            "driver": "595.80",
            "vram_mib": 32607,
        }
        for i in range(4)
    ]


def probe(row):
    runtime = facts()
    runtime.update(driver=row["driver"], gpu=row["name"], vram_mib=row["vram_mib"])
    return {
        "uuid": row["uuid"],
        "facts": runtime,
        "kernel": {
            "device": "cuda",
            "product": [[19.0, 22.0], [43.0, 50.0]],
            "left_gradient": [[11.0, 15.0], [11.0, 15.0]],
            "right_gradient": [[4.0, 4.0], [6.0, 6.0]],
        },
    }


def test_four_unique_physical_devices_are_each_selected_once_and_verified():
    from training.distributed_preflight import probe_group

    devices, seen = inventory(), []

    def run(row):
        seen.append(row["uuid"])
        return probe(row)

    result = probe_group(devices, probe=run)
    assert result["physical_gpu_count"] == 4 and result["verified"] is True
    assert seen == [row["uuid"] for row in devices] and len(set(seen)) == 4
    assert [row["facts"]["gpu_count"] for row in result["devices"]] == [1] * 4
    assert (
        result["scope"]
        == "four physical UUIDs, each probed in its own one-visible-device process"
    )


@pytest.mark.parametrize(
    "change", ["missing", "extra", "duplicate", "gpu", "memory", "driver"]
)
def test_bad_physical_inventory_is_rejected_before_probing(change):
    from training.distributed_preflight import probe_group

    rows = inventory()
    seen = []
    if change == "missing":
        rows.pop()
    elif change == "extra":
        rows.append(deepcopy(rows[0]))
    elif change == "duplicate":
        rows[1]["uuid"] = rows[0]["uuid"]
    elif change == "gpu":
        rows[1]["name"] = "NVIDIA GeForce RTX 4090"
    elif change == "memory":
        rows[1]["vram_mib"] = 24000
    else:
        rows[1]["driver"] = "570.1"
    with pytest.raises(ValueError):
        probe_group(rows, probe=lambda row: seen.append(row))
    assert not seen


@pytest.mark.parametrize(
    "change",
    ["wrong-uuid", "visible-count", "boolean-count", "cuda", "kernel", "missing-field"],
)
def test_each_child_must_attest_its_assigned_uuid_runtime_and_hand_kernel(change):
    from training.distributed_preflight import probe_group

    def altered(row):
        value = deepcopy(probe(row))
        if change == "wrong-uuid":
            value["uuid"] = "GPU-99999999-0000-0000-0000-000000000000"
        elif change == "visible-count":
            value["facts"]["gpu_count"] = 4
        elif change == "boolean-count":
            value["facts"]["gpu_count"] = True
        elif change == "cuda":
            value["facts"]["cuda_available"] = False
        elif change == "kernel":
            value["kernel"]["product"][1][1] = 49.0
        else:
            del value["facts"]["driver"]
        return value

    with pytest.raises(ValueError):
        probe_group(inventory(), probe=altered)


def test_actual_probe_and_inventory_are_rejected_on_mac_before_spawning(monkeypatch):
    from types import SimpleNamespace

    from training import distributed_preflight as preflight

    monkeypatch.setattr(preflight, "sys", SimpleNamespace(platform="darwin"))
    with pytest.raises(ValueError, match="Linux"):
        preflight.isolated_probe(inventory()[0])
    with pytest.raises(ValueError, match="Linux"):
        preflight.collect_four_gpu()


def test_isolated_children_get_only_their_uuid_and_no_service_credentials(monkeypatch):
    import ast
    import json
    from types import SimpleNamespace

    from training import distributed_preflight as preflight

    monkeypatch.setattr(
        preflight, "sys", SimpleNamespace(platform="linux", executable="/fake/python")
    )
    for name in ("HF_TOKEN", "VAST_API_KEY", "CLOUDRIFT_API_KEY"):
        monkeypatch.setenv(name, "opaque-fixture")
    selected = []

    def run(args, **kwargs):
        assert args[:2] == ["/fake/python", "-c"]
        ast.parse(args[2])
        uuid = args[3]
        selected.append(uuid)
        assert kwargs["env"]["CUDA_VISIBLE_DEVICES"] == uuid
        assert not any(
            name in kwargs["env"]
            for name in ("HF_TOKEN", "VAST_API_KEY", "CLOUDRIFT_API_KEY")
        )
        assert kwargs["check"] is True and kwargs["timeout"] == 120
        row = next(row for row in inventory() if row["uuid"] == uuid)
        return SimpleNamespace(stdout=json.dumps(probe(row)))

    monkeypatch.setattr(preflight.subprocess, "run", run)
    result = preflight.probe_group(inventory(), probe=preflight.isolated_probe)
    assert result["verified"] and selected == [row["uuid"] for row in inventory()]
