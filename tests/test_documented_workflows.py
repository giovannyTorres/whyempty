"""Keep the public quickstart, comparisons, cookbook and benchmark runner executable."""

import subprocess
import sys
from pathlib import Path


def test_documented_workflows():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-I", "-X", "utf8", str(root / "scripts/check_docs.py")],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
