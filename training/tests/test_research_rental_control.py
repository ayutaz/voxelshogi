"""Purpose/budget/guardian metadata only; no provider calls or real resources."""

import hashlib
import json

import pytest

from training.tests.test_rental_control import Provider


def setup(tmp_path):
    from training.research_rental_control import ResearchRental

    state = tmp_path / "eval-pilot"
    state.mkdir()
    (state / "id_ed25519.pub").write_text("ssh-ed25519 opaque-fixture")
    budget = tmp_path / "budget.json"
    budget.write_text(
        json.dumps(
            {
                "approved_total_usd": 100,
                "reservations": [
                    {"task": "m4", "maximum_usd": 41},
                    {"task": "m6-main", "maximum_usd": 20},
                ],
            }
        )
    )
    workload = tmp_path / "workload.json"
    workload.write_text(
        json.dumps({"source_commit": "a" * 40, "purpose": "evaluation"})
    )
    workload_hash = hashlib.sha256(workload.read_bytes()).hexdigest()
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "schema": "voxelshogi-research-rental-plan-v1",
                "purpose": "phase5-evaluation",
                "source_commit": "a" * 40,
                "workload_sha256": workload_hash,
                "sku": "rtx59-7-48-750-xam.1",
                "datacenter": "na_west_us_gr_1",
                "with_public_ip": True,
                "maximum_seconds": 14400,
                "maximum_hourly_usd": 1,
                "maximum_usd": 4,
                "estimated_seconds": 7200,
            }
        )
    )
    api = Provider()
    control = ResearchRental(
        state,
        api,
        tag="voxelshogi-phase5-eval-pilot",
        budget=budget,
        plan=plan,
        phase="phase5",
        clock=lambda: 1000,
        other_provider_idle=lambda: None,
        workload=workload,
        source_check=lambda commit: None,
    )
    return control, api, budget, plan


def test_existing_project_and_new_purpose_caps_preserve_all_m6_reservations(tmp_path):
    control, api, budget, plan = setup(tmp_path)

    def guard():
        assert not any(path.endswith("instances/rent") for path, _ in api.calls)
        assert (control.state / "deadline.json").exists()
        row = json.loads(budget.read_text())["reservations"][-1]
        assert row["task"] == "phase5-evaluation" and row["maximum_usd"] == 4

    control.rent(guard)
    ledger = json.loads(budget.read_text())
    assert (
        ledger["reserved_total_usd"] == 65 and ledger["remaining_unreserved_usd"] == 35
    )
    assert ledger["reservations"][:2] == [
        {"task": "m4", "maximum_usd": 41},
        {"task": "m6-main", "maximum_usd": 20},
    ]
    row = ledger["reservations"][-1]
    assert row["plan_sha256"] == hashlib.sha256(plan.read_bytes()).hexdigest()
    assert (
        row["workload_sha256"]
        == hashlib.sha256((tmp_path / "workload.json").read_bytes()).hexdigest()
    )
    deadline = json.loads((control.state / "deadline.json").read_text())
    assert deadline["maximum_end_at"] == 15400 and deadline["stop_at"] == 14500
    with pytest.raises(ValueError):
        control.rent(guard)


@pytest.mark.parametrize(
    "key,value",
    [
        ("purpose", "m6-main"),
        ("purpose", "phase6-training"),
        ("maximum_seconds", 86400),
        ("maximum_seconds", True),
        ("maximum_hourly_usd", 2),
        ("maximum_usd", 3),
        ("estimated_seconds", 14000),
        ("estimated_seconds", 0),
        ("source_commit", "short"),
        ("workload_sha256", "short"),
        ("datacenter", "unquoted"),
        ("with_public_ip", False),
        ("sku", "unquoted"),
    ],
)
def test_invalid_scope_or_unbounded_plan_fails_before_api_calls(tmp_path, key, value):
    control, api, _, path = setup(tmp_path)
    plan = json.loads(path.read_text())
    plan[key] = value
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError):
        control.rent(lambda: None)
    assert api.calls == []


@pytest.mark.parametrize("case", ["project", "phase", "duplicate", "nan", "negative"])
def test_cumulative_and_phase_budgets_are_checked_under_shared_ledger_lock(
    tmp_path, case
):
    control, api, path, _ = setup(tmp_path)
    ledger = json.loads(path.read_text())
    row = {"task": "previous", "maximum_usd": 36}
    if case == "phase":
        row = {"task": "phase5-data", "maximum_usd": 17}
    if case == "duplicate":
        row = {"task": "phase5-evaluation", "maximum_usd": 1, "tag": control.tag}
    if case == "nan":
        row["maximum_usd"] = float("nan")
    if case == "negative":
        row["maximum_usd"] = -1
    ledger["reservations"].append(row)
    path.write_text(json.dumps(ledger))
    with pytest.raises(ValueError):
        control.rent(lambda: None)
    assert not any(p.endswith("instances/rent") for p, _ in api.calls)
    assert len(json.loads(path.read_text())["reservations"]) == 3


def test_cross_provider_conflict_and_missing_guard_do_not_create_paid_resource(
    tmp_path,
):
    control, api, budget, _ = setup(tmp_path)

    def conflict():
        raise ValueError("Vast.ai owned rental exists")

    control.other_provider_idle = conflict
    with pytest.raises(ValueError, match="Vast.ai"):
        control.rent(lambda: None)
    assert api.calls == [] and len(json.loads(budget.read_text())["reservations"]) == 2
    control.other_provider_idle = lambda: None

    def failed_guard():
        raise RuntimeError("guardian failed")

    with pytest.raises(RuntimeError, match="guardian"):
        control.rent(failed_guard)
    assert not any(p.endswith("instances/rent") for p, _ in api.calls)


def test_shared_ip_choice_is_explicit_and_keeps_same_four_hour_cap(tmp_path):
    control, base, budget, path = setup(tmp_path)
    plan = json.loads(path.read_text())
    plan.update(
        sku="rtx59-7-23-800-ig.1",
        datacenter="ap_northeast_kr_se_1",
        with_public_ip=False,
    )
    path.write_text(json.dumps(plan))

    def api(endpoint, data):
        response = base(endpoint, data)
        if endpoint.endswith("instance-types/list"):
            response["instance_types"][0]["variants"][0].update(
                name=plan["sku"],
                cost_per_hour=65,
                available_nodes_per_dc={plan["datacenter"]: 1},
                ip_availability_per_dc={plan["datacenter"]: {"public_ips": False}},
            )
        return response

    control.api = api
    control.rent(lambda: None)
    request = next(d for p, d in base.calls if p.endswith("instances/rent"))
    assert request["with_public_ip"] is False
    assert request["selector"]["ByInstanceTypeAndLocation"]["datacenters"] == [
        plan["datacenter"]
    ]
    assert json.loads(budget.read_text())["reserved_total_usd"] == 65
    assert (
        json.loads((control.state / "deadline.json").read_text())["hourly_usd"] == 0.65
    )


def test_workload_or_plan_change_and_source_failure_precede_provider_access(tmp_path):
    control, api, _, path = setup(tmp_path)
    control.read_plan()
    plan = json.loads(path.read_text())
    plan["estimated_seconds"] = 7000
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="plan changed"):
        control.rent(lambda: None)
    assert api.calls == []


def test_workload_hash_and_clean_source_are_required(tmp_path):
    control, api, _, _ = setup(tmp_path)
    control.workload.write_text('{"source_commit":"changed"}')
    with pytest.raises(ValueError, match="workload"):
        control.rent(lambda: None)
    assert api.calls == []


def test_source_and_cross_provider_check_cannot_be_omitted(tmp_path):
    control, api, _, _ = setup(tmp_path)

    def dirty_source(commit):
        raise ValueError("dirty source")

    control.source_check = dirty_source
    with pytest.raises(ValueError, match="dirty source"):
        control.rent(lambda: None)
    control.source_check = lambda commit: None
    control.other_provider_idle = None
    with pytest.raises(ValueError, match="cross-provider"):
        control.rent(lambda: None)
    assert api.calls == []


def test_research_guard_is_independent_of_missing_plan_and_preserves_phase_namespace(
    tmp_path,
):
    from training.research_rental_control import ResearchRental, guard_command

    command = guard_command(tmp_path / "state", tmp_path / "budget", phase="phase5")
    assert command[command.index("-m") + 1] == "training.research_rental_control"
    assert command[command.index("--phase") + 1] == "phase5"
    assert "--plan" not in command and "--workload" not in command
    control = ResearchRental(
        tmp_path / "state",
        lambda *args: None,
        tag="voxelshogi-phase5-state",
        budget=tmp_path / "budget",
    )
    assert control.plan is None and control.workload is None


def test_cleanup_uses_owned_identity_even_after_plan_and_workload_are_gone(tmp_path):
    control, api, _, path = setup(tmp_path)
    control.rent(lambda: None)
    api.rows[0]["tags"] = [control.tag]
    path.unlink()
    control.workload.unlink()
    result = control.terminate()
    assert result["complete"] is True
    assert result["instances"][0]["resources_released"] is True
    assert (control.state / "terminal.json").exists()


def test_phase6_does_not_spend_phase5_allocation_and_has_its_own_cap(tmp_path):
    control, api, budget, path = setup(tmp_path)
    control.phase = "phase6"
    control.tag = "voxelshogi-phase6-eval-pilot"
    plan = json.loads(path.read_text())
    plan["purpose"] = "phase6-training"
    path.write_text(json.dumps(plan))
    ledger = json.loads(budget.read_text())
    ledger["reservations"].append({"task": "phase5-selfplay", "maximum_usd": 20})
    budget.write_text(json.dumps(ledger))
    control.rent(lambda: None)
    assert json.loads(budget.read_text())["reserved_total_usd"] == 85


def test_consistent_but_overlong_quote_is_still_rejected(tmp_path):
    control, api, _, path = setup(tmp_path)
    plan = json.loads(path.read_text())
    plan.update(maximum_seconds=18000, maximum_usd=5, estimated_seconds=14400)
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError):
        control.rent(lambda: None)
    assert api.calls == []


def test_workload_digest_detects_changes_even_when_source_is_the_same(tmp_path):
    control, api, _, _ = setup(tmp_path)
    control.workload.write_text(
        json.dumps({"source_commit": "a" * 40, "purpose": "different"})
    )
    with pytest.raises(ValueError, match="workload"):
        control.rent(lambda: None)
    assert api.calls == []


def test_phase6_own_allocation_cannot_be_exceeded(tmp_path):
    control, api, budget, path = setup(tmp_path)
    control.phase, control.tag = "phase6", "voxelshogi-phase6-eval-pilot"
    plan = json.loads(path.read_text())
    plan["purpose"] = "phase6-training"
    path.write_text(json.dumps(plan))
    ledger = json.loads(budget.read_text())
    ledger["reservations"].append({"task": "phase6-operators", "maximum_usd": 17})
    budget.write_text(json.dumps(ledger))
    with pytest.raises(ValueError, match="budget"):
        control.rent(lambda: None)
    assert not any(p.endswith("instances/rent") for p, _ in api.calls)


def test_real_source_check_compares_commit_and_dirty_status(monkeypatch):
    from training.research_rental_control import _source_check

    def outputs(commit, dirty):
        return lambda args, **kwargs: commit if "rev-parse" in args else dirty

    monkeypatch.setattr(
        "training.research_rental_control.subprocess.check_output",
        outputs("a" * 40, ""),
    )
    _source_check("a" * 40)
    for commit, dirty in (("b" * 40, ""), ("a" * 40, " M training/changed.py")):
        monkeypatch.setattr(
            "training.research_rental_control.subprocess.check_output",
            outputs(commit, dirty),
        )
        with pytest.raises(ValueError, match="clean source"):
            _source_check("a" * 40)
