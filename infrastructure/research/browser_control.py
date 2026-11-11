"""Operate one API-verified diagnosis host; never copy data/checkpoints to Mac."""

import argparse
import base64
import hashlib
import json
import re
import runpy
import shlex
import subprocess
import sys
import time
from pathlib import Path

from training.vast_rental_control import VastClient, instance_inventory, project_key

ROOT = Path.cwd()
parser = argparse.ArgumentParser(__doc__)
parser.add_argument("control")
parser.add_argument(
    "mode",
    choices=[
        "start-bootstrap",
        "bootstrap-status",
        "host-admission",
        "upload-inputs",
        "start-worker",
        "collect",
        "progress",
        "log",
        "review-hf-metadata",
        "watch",
    ],
)
args = parser.parse_args()
assert re.fullmatch(r"research-browser[1-9]-control", args.control)
STATE = ROOT / "runs/p6" / args.control
BASE = "runs/p6/research-browser"
REMOTE = "/root/voxelshogi"
W = json.loads((STATE / "workload.json").read_text())
assert (
    hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    == W["control_operator_sha256"]
)
assert (
    W["admitted"] is True
    and W["stage"] == "research-browser"
    and W["expected_architectures"] == 4
)
assert W["run_label"] == "voxelshogi-phase6-" + args.control
assert not subprocess.check_output(["git", "status", "--porcelain"], text=True)
assert (
    subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    == W["source_commit"]
)
ids = json.loads((STATE / "rent-response.json").read_text())["instance_ids"]
assert len(ids) == 1 and type(ids[0]) is int
client = VastClient(project_key(ROOT, "VAST_API_KEY"))
account = client("GET", "/api/v0/users/current/")
assert account["id"] == json.loads((STATE / "account.json").read_text())["id"]
all_rows = instance_inventory(client)
rows = [row for row in all_rows if row["id"] in ids]
assert len(rows) == 1
row = rows[0]
assert row["label"] == W["run_label"] and row["actual_status"] == "running"
assert isinstance(row["ssh_host"], str) and re.fullmatch(
    r"[a-zA-Z0-9.-]+", row["ssh_host"]
)
assert type(row["ssh_port"]) is int and 1 <= row["ssh_port"] <= 65535
(STATE / "status.json").write_text(
    json.dumps({"checked_at": time.time(), "instances": rows}, indent=2) + "\n"
)
known = STATE / "known_hosts"
SSH = [
    "ssh",
    "-T",
    "-i",
    str(STATE / "id_ed25519"),
    "-p",
    str(row["ssh_port"]),
    "-o",
    "IdentitiesOnly=yes",
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=20",
    "-o",
    "ServerAliveInterval=30",
    "-o",
    "ServerAliveCountMax=3",
    "-o",
    "UserKnownHostsFile=" + str(known),
    "-o",
    "StrictHostKeyChecking=" + ("yes" if known.exists() else "accept-new"),
    "root@" + row["ssh_host"],
]


def save(name, value):
    target = STATE / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2) + "\n")


def ssh(command, data=None):
    result = subprocess.run(
        SSH + [command], input=data, capture_output=True, check=True
    )
    return result.stdout


def python(code, data=None):
    compile(code, "owned-comparison-operation", "exec")
    return json.loads(
        ssh(
            "cd "
            + REMOTE
            + " && /root/.local/bin/uv run --project infrastructure/cuda --locked --no-sync python -c "
            + shlex.quote(code),
            data,
        )
    )


EVIDENCE_NAMES = (
    "cuda-preflight.json",
    "hf-preflight.json",
    "hf-operation.json",
    "job-status.json",
    "complete.json",
    "failure.json",
    "publication-receipt.json",
    "resource-summary.json",
    "resource-samples.json",
    "partial-publication-failure.json",
    "worker-finished.json",
    "browser-output/result.json",
    "browser-validation.json",
    "input-verification.json",
    "feature-preparation.json",
    "corpus-audit-complete.json",
    "corpus-audit-failure.json",
    "corpus/complete.json",
    "corpus/failure.json",
    "corpus/partial-publication-failure.json",
    "corpus/worker-finished.json",
    "corpus/publication-receipt.json",
    "corpus/audit-result.json",
    "corpus/admission-summary.json",
    "corpus/diagnosis/target-diagnosis.json",
    "corpus/diagnosis/development-protection.json",
    "corpus/resource-summary.json",
)


def collect_evidence():
    code = (
        """from pathlib import Path
import json,psutil
b=Path('runs/p6/research-browser');info=json.loads((b/'job-launch.json').read_text())
p=psutil.Process(info['pid']) if psutil.pid_exists(info['pid']) else None
if p is not None and p.create_time()!=info['create_time']:raise ValueError('worker PID reused')
active=p is not None and p.status()!=psutil.STATUS_ZOMBIE
out={'process':{**info,'running':active},'records':{}}
for name in """
        + repr(EVIDENCE_NAMES)
        + """:
 f=b/name
 if f.exists():
  assert f.is_file() and not f.is_symlink() and f.stat().st_size<4*1024**2
  out['records'][name]=json.loads(f.read_text())
print(json.dumps(out))
"""
    )
    result = python(code)
    for name, value in result["records"].items():
        save("evidence/" + name, value)
    save("worker-status.json", result["process"])
    return result


if args.mode == "start-bootstrap":
    raw = (STATE / "bootstrap.sh").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == W["files"]["bootstrap.sh"]
    assert (
        ssh(
            "test ! -e /root/voxelshogi-browser-bootstrap-request && printf ready"
        ).strip()
        == b"ready"
    )
    ssh("umask 077; cat > /root/voxelshogi-browser-bootstrap.sh", raw)
    assert (
        ssh("sha256sum /root/voxelshogi-browser-bootstrap.sh").decode().split()[0]
        == hashlib.sha256(raw).hexdigest()
    )
    inner = 'printf "%s\\n" "$$" > /root/voxelshogi-browser-bootstrap.pid\nbash /root/voxelshogi-browser-bootstrap.sh\nresult=$?\nprintf "%s\\n" "$result" > /root/voxelshogi-browser-bootstrap-exit\nexit "$result"'
    outer = (
        "umask 077\n: > /root/voxelshogi-browser-bootstrap-request\nnohup setsid bash -c "
        + shlex.quote(inner)
        + ' > /root/voxelshogi-browser-bootstrap.log 2>&1 < /dev/null &\nprintf "started\\n"'
    )
    print(ssh("bash -c " + shlex.quote(outer)).decode().strip())
elif args.mode == "bootstrap-status":
    print(
        ssh(
            'if test -f /root/voxelshogi-browser-bootstrap.pid; then pid=$(cat /root/voxelshogi-browser-bootstrap.pid); if kill -0 "$pid" 2>/dev/null; then printf "running=true\\n"; else printf "running=false\\n"; fi; fi; if test -f /root/voxelshogi-browser-bootstrap-exit; then printf "exit="; cat /root/voxelshogi-browser-bootstrap-exit; fi; tail -12 /root/voxelshogi-browser-bootstrap.log'
        ).decode(errors="replace")
    )
elif args.mode == "host-admission":
    code = """from pathlib import Path
import json,os,platform,subprocess,time,psutil
limits={}
for name in ('cpu.max','memory.max'):
 p=Path('/sys/fs/cgroup')/name
 limits[name]=p.read_text().strip() if p.is_file() else None
quota=limits['cpu.max'].split() if limits['cpu.max'] else None
effective=float(len(os.sched_getaffinity(0)))
if quota and quota[0]!='max':effective=min(effective,int(quota[0])/int(quota[1]))
elif not quota:
 q=Path('/sys/fs/cgroup/cpu/cpu.cfs_quota_us');p=Path('/sys/fs/cgroup/cpu/cpu.cfs_period_us')
 if q.is_file() and p.is_file() and int(q.read_text())>0:effective=min(effective,int(q.read_text())/int(p.read_text()))
memory=psutil.virtual_memory().total
if limits['memory.max'] and limits['memory.max']!='max':memory=min(memory,int(limits['memory.max']))
elif not limits['memory.max']:
 p=Path('/sys/fs/cgroup/memory/memory.limit_in_bytes')
 if p.is_file():memory=min(memory,int(p.read_text()))
result={'checked_at':time.time(),'platform':platform.platform(),'effective_cpus':effective,'memory_limit_bytes':memory,'affinity_count':len(os.sched_getaffinity(0)),'cgroup':limits,'gpu_query':subprocess.check_output(['nvidia-smi','--query-gpu=uuid,name,driver_version,memory.total','--format=csv,noheader,nounits'],text=True).strip(),'cuda_preflight':json.loads(Path('runs/p6/research-browser/cuda-preflight.json').read_text())}
print(json.dumps(result))
"""
    result = python(code)
    assert result["effective_cpus"] >= W["minimum_effective_cpus"]
    assert result["memory_limit_bytes"] >= W["minimum_memory_bytes"]
    assert (
        len(result["gpu_query"].splitlines()) == 1 and "RTX 5090" in result["gpu_query"]
    )
    result.update(
        instance_id=ids[0],
        verified=True,
        workload_sha256=hashlib.sha256(
            (STATE / "workload.json").read_bytes()
        ).hexdigest(),
        source_commit=W["source_commit"],
        maximum_workers=W["max_workers"],
        scope="container affinity/cgroup and GPU facts; not a performance measurement or exclusive CPU guarantee",
    )
    save("host-admission.json", result)
    save(
        "owner.json",
        {"provider": "vast.ai", "instance_id": ids[0], "tag": W["run_label"]},
    )
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "instance_id",
                    "verified",
                    "effective_cpus",
                    "memory_limit_bytes",
                    "platform",
                )
            }
        )
    )
elif args.mode == "upload-inputs":
    names = [
        *W["files"],
        "workload.json",
        "deadline.json",
        "owner.json",
        "host-admission.json",
        "preflight.json",
    ]
    payload = {}
    for name in names:
        raw = (STATE / name).read_bytes()
        assert len(raw) < 4 * 1024**2
        payload[name] = {
            "data": base64.b64encode(raw).decode(),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    code = """from pathlib import Path
import json,sys,hashlib,base64
b=Path('runs/p6/research-browser')
assert json.loads((b/'bootstrap-complete.json').read_text())['complete']
payload=json.load(sys.stdin)
for name,item in payload.items():
 p=Path(name);assert not p.is_absolute() and '..' not in p.parts
 raw=base64.b64decode(item['data']);assert hashlib.sha256(raw).hexdigest()==item['sha256']
 dest=b/p;dest.parent.mkdir(parents=True,exist_ok=True)
 assert not dest.exists() or dest.read_bytes()==raw
 dest.write_bytes(raw);dest.chmod(0o600)
print(json.dumps({'uploaded':len(payload)}))
"""
    print(json.dumps(python(code, json.dumps(payload).encode())))
elif args.mode == "start-worker":
    source, token = runpy.run_path(str(ROOT / "runs/m4/auth_source.py"))[
        "get_hf_token"
    ](ROOT)
    code = """from pathlib import Path
import json,sys,os,subprocess,time,hashlib,psutil
b=Path('runs/p6/research-browser');payload=json.load(sys.stdin)
token=payload.pop('hf_token');assert token and not payload
assert not (b/'job-launch.json').exists()
w=json.loads((b/'workload.json').read_text())
for name,digest in w['files'].items():assert hashlib.sha256((b/name).read_bytes()).hexdigest()==digest
assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()==w['source_commit']
env={**os.environ,'HF_TOKEN':token,'HF_TOKEN_PATH':'/dev/null','HF_HUB_DISABLE_IMPLICIT_TOKEN':'1','HF_HUB_DISABLE_PROGRESS_BARS':'1','HF_HUB_VERBOSITY':'error','PYTHONPATH':'/root/voxelshogi','CUBLAS_WORKSPACE_CONFIG':':4096:8','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1'}
assert not env.get('VAST_API_KEY') and not env.get('CLOUDRIFT_API_KEY')
(b/'job-launch-request.json').open('x').write(json.dumps({'at':time.time(),'source_commit':w['source_commit']}))
child=subprocess.Popen(['/root/.local/bin/uv','run','--project','infrastructure/cuda','--locked','--no-sync','python','-u',str(b/'worker.py')],env=env,stdout=(b/'job.log').open('xb'),stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
info={'pid':child.pid,'create_time':psutil.Process(child.pid).create_time(),'at':time.time(),'source_commit':w['source_commit']}
(b/'job-launch.json').write_text(json.dumps(info));print(json.dumps(info))
"""
    # The request marker is deliberately not resent if its SSH observation fails.
    result = python(code, json.dumps({"hf_token": token}).encode())
    save("job-launch.json", result)
    # Start a separate control-side watcher immediately after successful launch.
    # It collects small terminal evidence and retires this owned host promptly;
    # the independent Actions deadline and local guardian remain armed.
    with (STATE / "completion-watcher.log").open("xb") as log:
        watcher = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "infrastructure.research.browser_control",
                args.control,
                "watch",
            ],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    save("completion-watcher-launch.json", {"pid": watcher.pid, "at": time.time()})
    print(json.dumps(result))
elif args.mode == "watch":
    from training.research_retirement import watch_browser
    from training.vast_phase6_control import Phase6VastRental

    control = Phase6VastRental(
        STATE,
        client,
        tag=W["run_label"],
        budget=ROOT / "runs/m4/cost-budget.json",
        plan=STATE / "plan.json",
        workload=STATE / "workload.json",
        phase="phase6",
    )
    # Reading/retirement only: this watcher never invokes rent or reserves cost.
    expected = json.loads((STATE / "job-launch.json").read_text())

    def observe_job():
        result = collect_evidence()
        assert all(
            result["process"][k] == expected[k]
            for k in ("pid", "create_time", "source_commit")
        )
        return result

    def record_completion(value):
        save("completion-watcher-status.json", value)

    deadline = (
        json.loads((STATE / "deadline.json").read_text())["maximum_end_at"] - 1260
    )
    result = watch_browser(
        observe_job,
        collect_evidence,
        control.terminate,
        deadline=deadline,
        save=record_completion,
    )
    print(json.dumps(result))
elif args.mode == "collect":
    result = collect_evidence()
    print(
        json.dumps(
            {
                "process": result["process"],
                "stage": result["records"].get("job-status.json"),
                "complete": result["records"].get("complete.json"),
                "failure": result["records"].get("failure.json"),
                "corpus_complete": result["records"].get("corpus-audit-complete.json"),
                "corpus_failure": result["records"].get("corpus-audit-failure.json"),
                "records_collected": len(result["records"]),
            }
        )
    )
elif args.mode == "progress":
    code = """from pathlib import Path
import json
b=Path('runs/p6/research-browser');p=b/'browser-output/result.json'
if not p.is_file():print(json.dumps({'browser_report_exists':False}))
else:
 v=json.loads(p.read_text());print(json.dumps({'browser_report_exists':True,'matrix_complete':v.get('matrix_complete'),'all_backends_passed':v.get('complete'),'rows':[{'name':r.get('name'),'backend':r.get('backend'),'status':r.get('status'),'error_message':r.get('error_message')} for r in v.get('rows',[])]}))
"""
    result = python(code)
    save("probe-progress.json", result)
    print(json.dumps(result))
elif args.mode == "review-hf-metadata":
    code = """from pathlib import Path
import json
b=Path('runs/p6/research-browser/publication');out={}
for name in ('README.md','LICENSE','manifest.json','validation.json','config.json'):
 f=b/name;assert f.is_file() and not f.is_symlink() and f.stat().st_size<4*1024**2
 out[name]=f.read_text()
print(json.dumps(out))
"""
    result = python(code)
    target = STATE / "hf-metadata-review"
    target.mkdir(exist_ok=True)
    for name, content in result.items():
        (target / name).write_text(content)
    print(json.dumps({"metadata_files": len(result), "data_or_models_relayed": 0}))
else:
    print(ssh("tail -45 " + REMOTE + "/" + BASE + "/job.log").decode(errors="replace"))
