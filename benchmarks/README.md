# Reproducing the benchmark

After installing the development environment, run from the repository root:

```sh
python benchmarks/benchmark.py --sizes 1000 10000 100000 --repeat 15 --number 50 --warmup 3 --memory-repeat 3 --json-output benchmarks/results.json
```

The baseline performs three sequential list comprehensions. All three scenarios
use the same predicate callables, in the same order, and validate identical
survivors before measurement. The other scenarios construct a trace, or construct
a trace and call `explain()` once. Integer inputs and predicates are built before
measurement; whyempty's own input materialization is included.

Elapsed time is the median of independent batches, divided by operations per
batch. After warming up each scenario, every timing round measures all scenarios.
The starting scenario rotates deterministically each round: Python, whyempty,
whyempty with explanation; then whyempty, whyempty with explanation, Python; then
whyempty with explanation, Python, whyempty. This balances execution order and
reduces drift from changing host load. Use a multiple of three repeats to balance
each scenario's position equally. Garbage collection keeps its normal enabled
state, with a collection before each batch. Warmups, validation, imports, and
output are excluded.
`tracemalloc` is disabled for timing. Allocation peaks are measured separately,
starting after input creation, with one result still alive at the measurement.
Both intermediate allocations and retained output contribute to the peak.

The JSON records timing order, all timing and memory samples, medians, ratios, overhead
percentages, interpreter, platform, and arguments. A ratio of `2.0` means twice
the baseline, or 100% overhead. Memory means incremental Python allocations
observed by `tracemalloc`, not process RSS. Numbers describe this synthetic
integer workload on one host; predicates, selectivity, Python version, and host
load affect results. There is no performance assertion in the test suite.

whyempty also stores original positions, first-failure metadata, stage statistics,
and timers. Its atomic stages build temporary partitions before committing.
These operations explain expected overhead relative to comprehensions; the
recorded measurements determine its magnitude. Rendering a diagnostic reads
stage statistics and never reruns predicates.
