"""Small local generation only; external production execution is a later phase."""

import argparse
import json
import subprocess
from pathlib import Path

from .data import GenerationConfig
from .runner import generate_bounded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser(
        "generate", help="generate or resume a small dataset"
    )
    generate.add_argument("output", type=Path)
    generate.add_argument("--seed", type=int, default=17)
    generate.add_argument("--games", type=int, default=3)
    generate.add_argument("--max-plies", type=int, default=2)
    generate.add_argument("--max-depth", type=int, default=1)
    generate.add_argument("--max-nodes", type=int, default=1000)
    generate.add_argument("--seconds", type=float, default=60)
    validate = commands.add_parser(
        "validate", help="validate under the same resource limits"
    )
    validate.add_argument("output", type=Path)
    validate.add_argument("--seconds", type=float, default=60)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if status:
        parser.error(
            "commit task-owned source changes before recording engine provenance"
        )
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if args.command == "generate":
        config = GenerationConfig(
            engine_commit=commit,
            seed=args.seed,
            games=args.games,
            max_plies=args.max_plies,
            max_depth=args.max_depth,
            max_nodes=args.max_nodes,
        )
    else:
        manifest_path = args.output / "manifest.json"
        if manifest_path.stat().st_size > 65536:
            parser.error("local manifest exceeds 64 KiB")
        config = GenerationConfig(**json.loads(manifest_path.read_text())["config"])
        if config.engine_commit != commit:
            parser.error("validate with the dataset's recorded source commit")
    result = generate_bounded(
        args.output,
        config,
        ledger=root / "runs/m4/session-budget.json",
        seconds=args.seconds,
        validate_only=args.command == "validate",
    )
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["reason"] == "completed" else 1)


if __name__ == "__main__":
    main()
