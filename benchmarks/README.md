# Reproducing the benchmark

After installing the development environment, run from the repository root:

```sh
python benchmarks/benchmark.py --sizes 1000 10000 100000 --repeat 12 --number 20 --warmup 3 --memory-repeat 3 --json-output benchmarks/results.json
```

The six scenarios use the same three predicate callables: even integers, values
below 80% of the input size, and values divisible by five. Identical surviving
items are checked before measurement.

| Scenario | Operation | Equivalent predicate-evaluation baseline |
| --- | --- | --- |
| `python` | Three sequential list comprehensions | `python` |
| `whyempty` | Construct a trace and apply three sequential filters | `python` |
| `whyempty_explain` | Construct a trace and render its explanation | `python` |
| `python_all` | Evaluate all three predicates for every occurrence and combine their decisions | `python_all` |
| `audit` | Audit a preconfigured `Pipeline` | `python_all` |
| `audit_explain` | Audit, explain, relax rule 2, query matching indices without rule 2, and request suggestions | `python_all` |

The sequential baseline skips later predicates for items already removed. The
full-evaluation baseline materializes each occurrence's three decisions before
calling `all()`, deliberately preventing predicate short-circuiting. This matches
the number and record-major order of predicate calls made by an audit; it does
not retain the audit's decision cache or provenance. The trace baseline uses the
same stage-major evaluation order as tracing.

Integer inputs, predicates, and `Pipeline` configuration are built before
measurement; whyempty's own input materialization is included. `audit_explain`
performs its queries on the newly created audit without reevaluating predicates.
The workload has surviving items, so `suggest_relaxations()` returns no
candidates. This scenario measures the nonempty-result suggestion path, not the
search for relaxations of an empty result.

Elapsed time is the median of independent batches, divided by operations per
batch. After warming up each scenario, every timing round measures all scenarios.
The starting scenario rotates deterministically each round through the table's
six scenarios. This balances execution order and reduces drift from changing
host load. Use a multiple of six repeats to balance each scenario's position
equally. Garbage collection keeps its normal enabled
state, with a collection before each batch. Warmups, validation, imports, and
output are excluded.
`tracemalloc` is disabled for timing. Allocation peaks are measured separately,
starting after input creation, with one result still alive at the measurement.
Both intermediate allocations and retained output contribute to the peak.

The JSON records timing order, all timing and memory samples, medians, ratios,
overhead percentages, interpreter, platform, and arguments. Existing
`*_to_python` ratios and the table's `Time/Py` and `Peak/Py` columns always compare
with sequential `python`. Each measurement's `baseline_scenario` identifies its
equivalent evaluation baseline from the table; `*_to_equivalent_baseline` ratios
and `Time/Base` and `Peak/Base` columns compare with that baseline. Their
`*_overhead_percent_to_equivalent_baseline` fields express the corresponding
percentage increase. A ratio of `2.0` means twice the baseline, or 100% overhead.
The full baseline normalizes predicate calls, not the additional diagnostic
capabilities. Memory means incremental Python allocations
observed by `tracemalloc`, not process RSS. Numbers describe this synthetic
integer workload on one host; predicates, selectivity, Python version, and host
load affect results. There is no performance assertion in the test suite.

whyempty also stores original positions, first-failure metadata, stage statistics,
and timers. Its atomic trace stages build temporary partitions before committing;
audits store outcomes for every rule and occurrence to support cached queries.
These operations explain expected overhead relative to comprehensions; the
recorded measurements determine its magnitude. Rendering a diagnostic reads
stage statistics and never reruns predicates.
