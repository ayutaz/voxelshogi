"""Execute actual preflight/SSH-fragment code with fake SDK/process ports."""

import ast
import contextlib
import io
import json
import runpy
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from training.hub_recovery import RecoveryApi
from training.hub_release import create_release_repository
from training.tests.test_hub_recovery import Api

WORKERS = ("browser_worker", "corpus_worker")


def source(name):
    return Path("infrastructure/research") / (name + ".py")


@pytest.mark.parametrize("name", WORKERS)
@pytest.mark.parametrize("invalid_account", [False, True])
def test_actual_worker_setup_recovers_transport_once_and_checks_identity_before_global_api(
    name, invalid_account
):
    tree = ast.parse(source(name).read_text())
    top = next(n for n in tree.body if isinstance(n, ast.Try))
    start = next(
        i
        for i, n in enumerate(top.body)
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "raw_api" for t in n.targets)
    )
    stop = next(
        i
        for i, n in enumerate(top.body[start:], start)
        if isinstance(n, ast.Expr)
        and isinstance(n.value, ast.Call)
        and isinstance(n.value.func, ast.Name)
        and n.value.func.id == "create_release_repository"
    )

    class Fake(Api):
        def whoami(self):
            return self.call(
                "whoami",
                {
                    "name": "wrong" if invalid_account else "ayousanz",
                    "orgs": [{"name": "voxelshogi"}],
                },
            )

    api = Fake()
    api.failures = {
        "whoami": 1,
        "create": 1,
        "info": 1,
        "settings": 1,
        "community-write": 1,
    }
    events = []

    def recovery(raw, **kw):
        assert kw["deadline"] == 200
        assert kw["stop_requested"].__self__ is stop_event
        assert kw["wait"].__self__ is stop_event
        return RecoveryApi(
            raw,
            deadline=200,
            transient_errors=(TimeoutError,),
            clock=lambda: 100,
            wait=lambda _: None,
            observe=events.append,
        )

    stop_event = threading.Event()
    scope = {
        "HfApi": lambda **kw: api,
        "TOKEN": "fake-not-a-credential",
        "PublicationApi": lambda raw, *_: raw,
        "get_session": lambda: None,
        "build_hf_headers": lambda **_: None,
        "RecoveryApi": recovery,
        "TRANSFER_END": 200,
        "TransportError": TimeoutError,
        "STOP": stop_event,
        "observe_hf": events.append,
        "stage": lambda _: None,
        "API": None,
        "REPO": "voxelshogi/voxelshogi-research-browser-v1",
        "SOURCE": "a" * 40,
        "create_release_repository": lambda *a, **kw: create_release_repository(
            *a, **kw, system="linux"
        ),
    }
    code = compile(
        ast.Module(body=top.body[start : stop + 1], type_ignores=[]),
        str(source(name)),
        "exec",
    )
    if invalid_account:
        with pytest.raises(AssertionError):
            exec(code, scope)
        assert scope["API"] is None and api.calls == ["whoami", "whoami"]
    else:
        exec(code, scope)
        assert isinstance(scope["API"], RecoveryApi)
        assert api.gated == "manual" and api.disabled
        assert all(
            api.calls.count(n) == 1 for n in ("create", "settings", "community-write")
        )
        assert "fake-not-a-credential" not in json.dumps(events)


@pytest.mark.parametrize("reused", [False, True])
def test_actual_collect_fragment_checks_birth_identity_and_writes_only_small_records(
    tmp_path, monkeypatch, reused
):
    tree = ast.parse(source("browser_control").read_text())
    names = next(
        ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "EVIDENCE_NAMES" for t in n.targets)
    )
    function = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "collect_evidence"
    )
    base = tmp_path / "runs/p6/research-browser"
    base.mkdir(parents=True)
    info = {"pid": 7, "create_time": 10.5, "source_commit": "a" * 40}
    (base / "job-launch.json").write_text(json.dumps(info))
    (base / "worker-finished.json").write_text('{"complete":false}')
    (base / "failure.json").write_text('{"complete":false,"error_type":"ReadTimeout"}')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(
        sys.modules,
        "psutil",
        SimpleNamespace(
            pid_exists=lambda _: True,
            Process=lambda _: SimpleNamespace(
                create_time=lambda: 11 if reused else 10.5, status=lambda: "zombie"
            ),
            STATUS_ZOMBIE="zombie",
        ),
    )

    def remote_python(code):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            exec(compile(code, "actual-remote-collection", "exec"), {})
        return json.loads(out.getvalue())

    saved = {}
    scope = {
        "EVIDENCE_NAMES": names,
        "python": remote_python,
        "save": lambda p, v: saved.update({p: v}),
    }
    exec(
        compile(
            ast.Module(body=[function], type_ignores=[]), "actual-collector", "exec"
        ),
        scope,
    )
    if reused:
        with pytest.raises(ValueError, match="reused"):
            scope["collect_evidence"]()
        assert saved == {}
    else:
        result = scope["collect_evidence"]()
        assert result["process"] == {**info, "running": False}
        assert set(saved) == {
            "evidence/worker-finished.json",
            "evidence/failure.json",
            "worker-status.json",
        }


def test_all_remote_python_fragments_compile_without_launching_processes():
    tree = ast.parse(source("browser_control").read_text())
    assignments = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id in ("code",) for t in n.targets)
    ]
    constants = {"EVIDENCE_NAMES": ("failure.json",)}
    for assignment in assignments:
        code = eval(
            compile(ast.Expression(assignment.value), "fragment-construction", "eval"),
            constants,
        )
        compile(code, "actual-remote-Python", "exec")


@pytest.mark.parametrize("kind", ["browser", "corpus"])
def test_real_publication_functions_preserve_failure_cases_and_verify_hashes_with_fake_ports(
    kind,
):
    runpy.run_path(
        str(Path(__file__).with_name(f"research_{kind}_publication_ports.py"))
    )
