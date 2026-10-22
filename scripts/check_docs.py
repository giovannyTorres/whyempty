"""Check local documentation links, run complete code blocks and smoke the benchmark."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]


def anchors(path):
    text = path.read_text(encoding="utf-8")
    found = set(re.findall(r'<a id="([^"]+)"', text))
    for heading in re.findall(r"^#{1,6}\s+(.+)$", text, re.M):
        heading = re.sub(r"[^\w -]", "", heading.lower())
        found.add(heading.replace(" ", "-"))
    return found


def main():
    linked = 0
    for path in ROOT.rglob("*.md"):
        if any(part.startswith(".") for part in path.relative_to(ROOT).parts):
            continue
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if target.startswith(("http:", "https:", "mailto:")):
                continue
            file, _, fragment = unquote(target).partition("#")
            resolved = path.parent / file if file else path
            if not resolved.exists():
                raise AssertionError(f"Broken link in {path.relative_to(ROOT)}: {target}")
            if fragment and resolved.suffix == ".md" and fragment not in anchors(resolved):
                raise AssertionError(f"Missing anchor in {path.relative_to(ROOT)}: {target}")
            linked += 1
    executed = 0
    with TemporaryDirectory() as directory:
        for name in ("README.md", "docs/comparison.md", "docs/cookbook.md"):
            source = (ROOT / name).read_text(encoding="utf-8")
            for index, code in enumerate(re.findall(r"```python\s*\n(.*?)```", source, re.S)):
                target = Path(directory) / "example.py"
                target.write_text(code, encoding="utf-8")
                result = subprocess.run(
                    [sys.executable, "-I", "-X", "utf8", str(target)],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )
                if result.returncode:
                    raise AssertionError(
                        f"{name} Python block {index + 1}:\n{result.stdout}\n{result.stderr}"
                    )
                executed += 1
    subprocess.run(
        [sys.executable, "-I", "-X", "utf8", str(ROOT / "benchmarks/reproduce.py"), "--quick"],
        cwd=ROOT,
        check=True,
    )
    assert json.loads((ROOT / "benchmarks/smoke.json").read_text(encoding="utf-8"))["quick"]
    print(
        f"Documentation passed: {linked} local links, "
        f"{executed} complete Python blocks and benchmark smoke."
    )


if __name__ == "__main__":
    main()
