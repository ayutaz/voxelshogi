"""Linux CI-only model-picker fixture; never evidence of training or a release.

Reuses actual M3 ONNX/reference bytes, with deliberately synthetic M6 receipts
from the metadata unit fixtures. The catalog is intercepted only by Playwright;
neither the fixture nor its catalog enters public/ or upload artifacts.
"""

import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main():
    if sys.platform != "linux" or os.environ.get("CI") != "true":
        raise RuntimeError("synthetic arena fixture is restricted to Linux CI")
    from export.generate import descriptor, validate_package
    from export.trained import review_evaluation
    from training.tests.test_trained_metadata import fixture

    source = ROOT / "runs/m3/ci"
    base = ROOT / "runs/m6/browser-fixture"
    if base.exists():
        raise FileExistsError("use a fresh CI fixture directory")
    manifest = validate_package(source)
    if manifest["sourceDirty"] or manifest["trained"]:
        raise ValueError("fixture must start from clean untrained M3 bytes")
    base.mkdir(parents=True)
    model = base / "model"
    shutil.copytree(source, model)
    evaluated = fixture(
        base / "synthetic-evaluation",
        source_commit=manifest["sourceCommit"],
        weights_writer=lambda target: shutil.copyfile(
            source / "model.safetensors", target
        ),
    )
    review = review_evaluation(
        evaluated,
        context={"sourceCommit": manifest["sourceCommit"], "sourceDirty": False},
        seed=314159,
    )
    manifest.update(
        id=review["model_id"],
        trained=True,
        numericContract="voxelshogi-trained-numeric-v1",
        license="Apache-2.0",
        training=review["training"],
        ciFixture="Synthetic receipts; untrained M3 weights. Not a learned release.",
    )
    (model / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (model / "README.md").write_text(
        "# CI fixture, not trained\n\n"
        "These are untrained M3 model bytes and synthetic M6 metadata receipts. "
        "Used only for actual ONNX/Worker/arena E2E in Linux CI. "
        "Not a Hugging Face release, training result, or GPU measurement.\n"
    )
    shutil.copyfile(ROOT / "LICENSE", model / "LICENSE")
    validate_package(model)
    release = {
        "approved": True,
        "id": manifest["id"],
        "license": "Apache-2.0",
        "sourceCommit": manifest["sourceCommit"],
        "repo": "voxelshogi/ci-fixture-not-published",
        "revision": manifest["sourceCommit"],
        "manifest": descriptor(model, model / "manifest.json"),
        "notices": [
            descriptor(model, model / name) for name in ("README.md", "LICENSE")
        ],
    }
    (base / "catalog.json").write_text(
        json.dumps({"schema": 1, "releases": [release]}, indent=2) + "\n"
    )
    # A same-size corrupted body must fail in the Worker, after metadata loading.
    broken = base / "corrupted"
    shutil.copytree(model, broken)
    path = broken / "fp32.onnx"
    with path.open("r+b") as stream:
        byte = stream.read(1)
        stream.seek(0)
        stream.write(bytes([byte[0] ^ 1]))
    print("Prepared private synthetic arena fixture; no training or publication.")


if __name__ == "__main__":
    main()
