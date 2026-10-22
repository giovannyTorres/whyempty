"""Reproduce checked comparisons, scale measurements and the published summary.

Usage: python benchmarks/reproduce.py [--quick] [--repeat 5]
"""

from __future__ import annotations

import argparse
import ast
import gc
import hashlib
import importlib.metadata
import json
import os
import platform
import runpy
import statistics
import subprocess
import sys
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path

PACKAGE = "whyempty"
ROOT = Path(__file__).resolve().parents[1]
SIZES = {"cellwalk": [100, 500, 2000], "nabularpy": [1000, 5000, 20000]}


def measure(operations, repeats, memory_repeats):
    timings = {name: [] for name, _ in operations}
    for _, operation in operations:
        for _ in range(2):
            operation()
    for round_index in range(repeats):
        offset = round_index % len(operations)
        for name, operation in operations[offset:] + operations[:offset]:
            gc.collect()
            start = time.perf_counter()
            result = operation()
            timings[name].append(time.perf_counter() - start)
            del result
    measurements = {}
    for name, operation in operations:
        peaks = []
        for _ in range(memory_repeats):
            gc.collect()
            tracemalloc.start()
            try:
                result = operation()
                peaks.append(tracemalloc.get_traced_memory()[1])
                del result
            finally:
                tracemalloc.stop()
        samples = timings[name]
        measurements[name] = {
            "seconds": samples,
            "median_seconds": statistics.median(samples),
            "min_seconds": min(samples),
            "max_seconds": max(samples),
            "traced_peak_bytes": peaks,
            "median_peak_bytes": statistics.median(peaks),
        }
    return measurements


def source_metrics():
    source = (ROOT / "examples/comparison.py").read_text(encoding="utf-8")
    metrics = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name in ("baseline", "library"):
            metrics[node.name] = {
                "physical_lines": node.end_lineno - node.lineno + 1,
                "statements": sum(
                    isinstance(child, ast.stmt)
                    for statement in node.body
                    for child in ast.walk(statement)
                ),
            }
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quick",
        action="store_true",
        help="small correctness/smoke run; does not overwrite published results",
    )
    parser.add_argument("--repeat", type=int, default=5)
    args = parser.parse_args()
    if args.repeat < 2:
        parser.error("--repeat must be >=2")
    repeat, memory_repeat = (2, 1) if args.quick else (args.repeat, 2)
    sizes = [100] if args.quick else SIZES.get(PACKAGE, [1000, 10000, 50000])
    output = ROOT / "benchmarks" / ("smoke.json" if args.quick else "latest.json")
    for name in ("comparison.py", "cookbook.py"):
        subprocess.run(
            [sys.executable, "-I", "-X", "utf8", str(ROOT / "examples" / name)],
            check=True,
            capture_output=True,
        )
    legacy = runpy.run_path(str(ROOT / "benchmarks/benchmark.py"))
    rows = []
    for size in sizes:
        results = legacy["benchmark_size"](
            size, repeat=repeat, number=3, warmup=2, memory_repeat=memory_repeat
        )
        rows.append(
            {
                "input_size": size,
                "accuracy": "identical survivors checked for all six scenarios",
                "measurements": results,
            }
        )
    versions = {PACKAGE: importlib.metadata.version(PACKAGE)}
    for dependency in ("pandas", "numpy", "openpyxl") if PACKAGE != "whyempty" else ():
        if dependency != "openpyxl" or PACKAGE == "cellwalk":
            versions[dependency] = importlib.metadata.version(dependency)
    try:
        parent_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        parent_commit = "unavailable"
    hashes = {
        name: hashlib.sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        for name in (
            "benchmarks/reproduce.py",
            "benchmarks/benchmark.py",
            "examples/comparison.py",
            "examples/cookbook.py",
        )
    }
    report = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "package": PACKAGE,
        "versions": versions,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "logical_cpus": os.cpu_count(),
        "base_commit": parent_commit,
        "source_sha256_lf": hashes,
        "command": f"python benchmarks/reproduce.py --repeat {repeat}",
        "quick": args.quick,
        "repeats": repeat,
        "warmup_per_operation": 2,
        "memory_repeats": memory_repeat,
        "methodology": {
            "time": (
                "interleaved rotating order; perf_counter; GC collection before s"
                "ample outside timer; input construction excluded"
            ),
            "memory": (
                "separate tracemalloc passes, result alive; Python allocation pea"
                "k, not total RSS; input construction excluded"
            ),
            "accuracy": (
                "differential assertions before timing; comparison and cookbook a"
                "ssertions also executed"
            ),
            "ease_of_use": (
                "physical lines and AST statements in comparison functions, exclu"
                "ding fixtures and imports; a code-size proxy, not a user study"
            ),
            "limitations": (
                "deterministic synthetic workloads; one host; diagnostics differ "
                "in scope; no statistical confidence intervals or R execution com"
                "parison"
            ),
        },
        "comparison_code_size": source_metrics(),
        "workloads": rows,
    }
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if not args.quick:
        lines = [
            f"# {PACKAGE}: measured benchmark results",
            "",
            (
                f"Generated {report['generated_at_utc']}. "
                f"CPython {report['python']} on {report['platform']}."
            ),
            "",
            "Exact versions: "
            + ", ".join(f"`{name}=={value}`" for name, value in versions.items())
            + ".",
            "",
            (
                f"{repeat} rotating timed rounds after two warmups; "
                f"{memory_repeat} separate allocation passes. "
                "Data construction, assertions and printing are excluded from timings."
            ),
            "",
            (
                "| Input size | Baseline ms | Package ms | Package / baseline | B"
                "aseline peak KiB | Package peak KiB |"
            ),
            "|---:|---:|---:|---:|---:|---:|",
        ]
        for row in rows:
            indexed = {m["scenario"]: m for m in row["measurements"]}
            pairs = [
                ("trace", indexed["python"], indexed["whyempty"]),
                ("audit", indexed["python_all"], indexed["audit"]),
            ]
            for label, base, package in pairs:
                size = f"{row['input_size']:,} {label}".strip()
                lines.append(
                    f"| {size} | {base['median_seconds'] * 1000:.3f} "
                    f"| {package['median_seconds'] * 1000:.3f} "
                    f"| {package['median_seconds'] / base['median_seconds']:.2f}x "
                    f"| {base['median_peak_bytes'] / 1024:.1f} "
                    f"| {package['median_peak_bytes'] / 1024:.1f} |"
                )
        lines.extend(
            [
                "",
                (
                    "Ratio = package median / baseline median. Values above 1 mean hi"
                    "gher latency. Peaks are traced Python allocations and exclude so"
                    "me native memory. Accuracy checks passed before every workload w"
                    "as timed."
                ),
                "",
                (
                    "The compared values/counts match. The package also produces vali"
                    "dation, lineage or diagnostic metadata described in [the compari"
                    "son](../docs/comparison.md); those extra outputs are not fully i"
                    "mplemented by the baseline."
                ),
                "",
                "## Ease of use: inspectable code-size proxy",
                "",
                "| Function | Physical lines (including signature) | AST statements |",
                "|---|---:|---:|",
            ]
        )
        for name, metrics in report["comparison_code_size"].items():
            lines.append(f"| {name} | {metrics['physical_lines']} | {metrics['statements']} |")
        lines.extend(
            [
                "",
                (
                    "These counts describe one checked example. They do not measure l"
                    "earning time, readability, debugging success or developer produc"
                    "tivity. Both recipes remain available for review."
                ),
                "",
                "## Interpretation and limits",
                "",
                (
                    "These are deterministic synthetic examples measured on one host."
                    " They support the stated input sizes and operations. They do not"
                    " establish universal speed, statistical accuracy, behavior on ev"
                    "ery dtype, or parity with R packages. No R runtime was benchmark"
                    "ed. Larger keys, wider tables, more failures and expensive predi"
                    "cates can change costs substantially."
                ),
                "",
                (
                    "[Raw samples, checked outcomes, environment and source hashes](l"
                    "atest.json) · [Reproduction and workload definitions](README.md)"
                ),
            ]
        )
        (ROOT / "benchmarks/RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        pins = [
            "# Recorded runtime; use CPython " + report["python"],
            *[f"{name}=={value}" for name, value in versions.items()],
        ]
        for name in ("python-dateutil", "six", "tzdata") if PACKAGE != "whyempty" else ():
            pins.append(f"{name}=={importlib.metadata.version(name)}")
        (ROOT / "benchmarks/requirements.txt").write_text("\n".join(pins) + "\n", encoding="utf-8")
    print(f"{PACKAGE}: {len(rows)} checked scales, {repeat} repeats; wrote {output.name}")


if __name__ == "__main__":
    main()
