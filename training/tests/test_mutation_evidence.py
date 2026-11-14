"""An isolated mutation checkout must include the public S provenance metadata."""

import os
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class MutationEvidenceTests(unittest.TestCase):
    def test_isolated_checkout_can_prepare_the_real_card_without_model_files(self):
        harness = runpy.run_path(str(ROOT / "scripts/ci/mutation-training.py"))
        with tempfile.TemporaryDirectory(prefix="voxelshogi-metadata-closure-") as tmp:
            work = Path(tmp)
            for relative in (
                "training/hub_release.py",
                "training/public_s_release.py",
                "export/public-s-approval.json",
                "export/public-s-model-card.md",
            ):
                destination = work / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, destination)
            harness["stage_metadata_evidence"](
                work, ROOT / "docs/experiments/p53-budget-extension-2026-11-04.json"
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-c",
                    "from pathlib import Path; from training.public_s_release import prepare_public_s_card; p,_=prepare_public_s_card(Path('export/public-s-model-card.md').read_text()); assert len(p['files'])==37",
                ],
                cwd=work,
                env={
                    **os.environ,
                    "PYTHONPATH": str(work),
                    "PYTHONDONTWRITEBYTECODE": "1",
                },
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(list(work.rglob("*.onnx")))
