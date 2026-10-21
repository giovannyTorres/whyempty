"""Compare traced filtering with equivalent sequential list comprehensions.

Run from the repository after installing whyempty, for example::

    python benchmarks/benchmark.py --json-output benchmarks/results.json

Timing and allocation tracing deliberately run in separate passes. Input data,
predicates, and operation closures are created before either pass.
"""

from __future__ import annotations

import argparse
import gc
import json
import platform
import statistics
import sys
import tracemalloc
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from time import get_clock_info, perf_counter
from typing import TypedDict

from whyempty import Trace, __version__, trace


class Measurement(TypedDict):
    """Raw samples and medians for one operation and input size."""

    scenario: str
    seconds_per_operation: list[float]
    median_seconds: float
    traced_peak_bytes: list[int]
    median_peak_bytes: float
    time_ratio_to_python: float
    time_overhead_percent: float
    peak_ratio_to_python: float
    peak_overhead_percent: float


def positive_int(value: str) -> int:
    """Parse a positive integer for a benchmark argument."""
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def measure_times(
    operations: tuple[tuple[str, Callable[[], object]], ...],
    *,
    repeat: int,
    number: int,
    warmup: int,
) -> dict[str, list[float]]:
    """Time scenarios in interleaved rounds, rotating order to reduce host drift."""
    for _, operation in operations:
        for _ in range(warmup):
            operation()
    samples: dict[str, list[float]] = {name: [] for name, _ in operations}
    for round_index in range(repeat):
        offset = round_index % len(operations)
        for name, operation in operations[offset:] + operations[:offset]:
            gc.collect()
            started = perf_counter()
            for _ in range(number):
                operation()
            samples[name].append((perf_counter() - started) / number)
    return samples


def measure_memory(operation: Callable[[], object], *, repeat: int) -> list[int]:
    """Measure incremental traced allocation peaks with each result still alive."""
    peaks = []
    for _ in range(repeat):
        gc.collect()
        tracemalloc.start()
        try:
            result = operation()
            _, peak = tracemalloc.get_traced_memory()
            peaks.append(peak)
            del result
        finally:
            tracemalloc.stop()
    return peaks


def benchmark_size(
    size: int, *, repeat: int, number: int, warmup: int, memory_repeat: int
) -> list[Measurement]:
    """Validate equivalent outputs and benchmark three operations for one size."""
    data = list(range(size))
    threshold = size * 0.8
    predicates: tuple[Callable[[int], bool], ...] = (
        lambda value: value % 2 == 0,
        lambda value: value < threshold,
        lambda value: value % 5 == 0,
    )

    def conventional() -> list[int]:
        current = [value for value in data if predicates[0](value)]
        current = [value for value in current if predicates[1](value)]
        return [value for value in current if predicates[2](value)]

    def traced() -> Trace[int]:
        return (
            trace(data)
            .keep("Even", predicates[0])
            .keep("Below 80%", predicates[1])
            .keep("Divisible by 5", predicates[2])
        )

    def diagnosed() -> tuple[Trace[int], str]:
        result = traced()
        return result, result.explain()

    expected = tuple(conventional())
    trace_result = traced()
    diagnosed_result, explanation = diagnosed()
    if trace_result.items != expected or diagnosed_result.items != expected:
        raise RuntimeError(f"filtering results differ for size {size}")
    if not explanation:
        raise RuntimeError("explain() returned an empty diagnostic")
    del expected, trace_result, diagnosed_result, explanation

    operations: tuple[tuple[str, Callable[[], object]], ...] = (
        ("python", conventional),
        ("whyempty", traced),
        ("whyempty_explain", diagnosed),
    )
    timings = measure_times(operations, repeat=repeat, number=number, warmup=warmup)
    measurements: list[Measurement] = []
    for name, operation in operations:
        times = timings[name]
        peaks = measure_memory(operation, repeat=memory_repeat)
        measurements.append(
            {
                "scenario": name,
                "seconds_per_operation": times,
                "median_seconds": statistics.median(times),
                "traced_peak_bytes": peaks,
                "median_peak_bytes": statistics.median(peaks),
                "time_ratio_to_python": 1.0,
                "time_overhead_percent": 0.0,
                "peak_ratio_to_python": 1.0,
                "peak_overhead_percent": 0.0,
            }
        )
    baseline = measurements[0]
    for measurement in measurements:
        time_ratio = measurement["median_seconds"] / baseline["median_seconds"]
        peak_ratio = measurement["median_peak_bytes"] / baseline["median_peak_bytes"]
        measurement["time_ratio_to_python"] = time_ratio
        measurement["time_overhead_percent"] = (time_ratio - 1.0) * 100.0
        measurement["peak_ratio_to_python"] = peak_ratio
        measurement["peak_overhead_percent"] = (peak_ratio - 1.0) * 100.0
    return measurements


def main(argv: Sequence[str] | None = None) -> None:
    """Run the benchmark and optionally write complete results as JSON."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", nargs="+", type=positive_int, default=[1000, 10000, 100000])
    parser.add_argument("--repeat", type=positive_int, default=7)
    parser.add_argument("--number", type=positive_int, default=10)
    parser.add_argument("--warmup", type=positive_int, default=3)
    parser.add_argument("--memory-repeat", type=positive_int, default=3)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args(argv)
    if tracemalloc.is_tracing():
        parser.error("run without an external tracemalloc profiler")

    results = []
    print("Size     Scenario              Median ms   Peak KiB   Time x   Peak x")
    for size in args.sizes:
        measurements = benchmark_size(
            size,
            repeat=args.repeat,
            number=args.number,
            warmup=args.warmup,
            memory_repeat=args.memory_repeat,
        )
        results.append({"size": size, "measurements": measurements})
        for measurement in measurements:
            print(
                f"{size:>7}  {measurement['scenario']:<20}"
                f" {measurement['median_seconds'] * 1000:>10.3f}"
                f" {measurement['median_peak_bytes'] / 1024:>10.2f}"
                f" {measurement['time_ratio_to_python']:>8.2f}"
                f" {measurement['peak_ratio_to_python']:>8.2f}"
            )

    clock = get_clock_info("perf_counter")
    scenario_order = ["python", "whyempty", "whyempty_explain"]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "whyempty_version": __version__,
        "python_version": sys.version,
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "clock": {"implementation": clock.implementation, "resolution": clock.resolution},
        "parameters": {
            "sizes": args.sizes,
            "repeat": args.repeat,
            "number": args.number,
            "warmup": args.warmup,
            "memory_repeat": args.memory_repeat,
            "gc_enabled": gc.isenabled(),
        },
        "methodology": {
            "input": "prebuilt list(range(size)); construction excluded",
            "predicates": ["x % 2 == 0", "x < size * 0.8", "x % 5 == 0"],
            "baseline": "three sequential list comprehensions using identical predicates",
            "timing": "median perf_counter batch time / number; tracemalloc disabled",
            "timing_order": {
                "method": "interleaved rounds; rotate starting scenario by one each round",
                "warmup": "warmup calls for each scenario before timed rounds",
                "gc": "collect immediately before each scenario batch, outside timing",
                "rounds": [
                    scenario_order[index % 3 :] + scenario_order[: index % 3]
                    for index in range(args.repeat)
                ],
            },
            "memory": "median incremental tracemalloc peak; one live result; separate pass",
            "includes": (
                "trace materialization, provenance, stages; explain only in whyempty_explain"
            ),
            "excludes": "input construction, validation, imports, warmups, JSON and table output",
            "limitations": (
                "traced Python allocations, not RSS; synthetic integer workload; host noise"
            ),
        },
        "results": results,
    }
    if args.json_output is not None:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
