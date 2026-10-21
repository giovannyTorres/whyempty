# whyempty

**Find the filter that emptied your data.**

whyempty records what happens at each stage of a Python filter pipeline: input
count, removals, survivors, retention, elapsed time, and the first rejection of
each input occurrence. It works with ordinary iterables and has **no required
runtime dependencies**. Python 3.10 or newer is required.

## Installation

Install version 0.1.0 from PyPI:

```sh
python -m pip install whyempty==0.1.0
```

To install from source and run the example:

```sh
git clone https://github.com/giovannyTorres/whyempty.git
cd whyempty
python -m pip install -e .
python examples/basic_usage.py
```

## Quick start

```python
from whyempty import trace

records = [
    {"id": 1, "active": True, "country": "MX", "score": 40},
    {"id": 2, "active": False, "country": "MX", "score": 90},
    {"id": 3, "active": True, "country": "US", "score": 95},
]

result = (
    trace(records)
    .keep("Active", lambda row: row["active"])
    .keep("Mexico", lambda row: row["country"] == "MX")
    .keep("Score >= 80", lambda row: row["score"] >= 80)
)

print(result.explain())
assert result.items == ()
assert result.count == 0
assert result.is_empty
```

Example output; timings depend on the machine:

```text
whyempty | Filter diagnostic
Initial records: 3
Filter             Before    Removed  Remaining   Retained   Time (ms)
----------------------------------------------------------------------
1. Active               3          1          2      66.7%       0.006
2. Mexico               2          1          1      50.0%       0.004
3. Score >= 80          1          1          0       0.0%       0.002
Result: EMPTY
All records were eliminated.
Final elimination: 3. Score >= 80
Significant reductions (at least 50% removed): 2. Mexico
```

The third filter caused final elimination. Earlier filters can contribute large
reductions; the diagnostic calls a reduction significant when it removes at
least 50% of a nonempty stage's input. This is a descriptive threshold, not a
statistical significance test. Any subsequent filters receive zero records and
are marked skipped. A collection that starts empty is reported separately and
has no final-elimination filter.

## API

| API | Behavior |
| --- | --- |
| `trace(iterable)` | Eagerly consume an iterable once into a `Trace[T]`. |
| `.keep(name, predicate)` | Keep truthy matches, record a stage, and return the same trace. |
| `.items` | Tuple of surviving references in original order; reading it makes no copy. |
| `.initial_count` / `.count` / `.is_empty` | Original count, survivor count, and empty status. |
| `.steps` | Tuple snapshot of immutable `Step` statistics in execution order. |
| `.first_empty_step` | The first `Step` that eliminated all remaining records, or `None`. |
| `.rejected()` | Tuple of first-rejection metadata, in original input order. |
| `.explain()` | Deterministic string for the recorded state; never prints or reruns predicates. |
| `.to_dict()` | JSON-compatible counts and stage statistics, without records or predicates. |

`keep()` mutates its trace: assigning its return value does not create a branch.
Previously retrieved `.items`, `.steps`, and `.rejected()` tuples are snapshots.
Items themselves are shared objects; no deep copy is performed. The library
does not mutate the input collection or records. User predicates can do so.

Each input **occurrence** reaching a stage is evaluated once, including truth
conversion. Repeated references are distinct occurrences. Iterators and
generators are consumed at `trace()` construction. No predicates are retained or
reevaluated by queries. With no filters, the result contains all input records.

A `Step` exposes `index` (one-based), `name`, `before`, `removed`, `remaining`,
`retention_pct`, `elapsed_seconds`, `emptied`, `skipped`, and
`significant_reduction`. For zero-input stages, retention is `None` in Python
and JSON `null`, displayed as `N/A`. Timing uses `perf_counter` and includes
partitioning and provenance recording; formatting and `Step` creation are
excluded. Duplicate filter names are allowed; stage indices disambiguate them.
Names must be nonblank, printable strings.

## Inspect rejected occurrences

```python
for rejection in result.rejected():
    print(rejection.original_index, rejection.step_index, rejection.filter_name)

# 0 3 Score >= 80
# 1 1 Active
# 2 2 Mexico
```

`Rejection` contains a zero-based `original_index`, a one-based `step_index`,
and `filter_name`. It never contains the record. To inspect a rejected value,
retain your input and look it up explicitly:

```python
rejection = result.rejected()[0]
rejected_record = records[rejection.original_index]
```

Positions work with dictionaries, lists, repeated values, and unhashable objects;
no unique ID or object hashing is required. Provenance retains no rejected-record
references. An object can remain referenced by another surviving occurrence,
by the caller, or by an exception traceback.

## Predicate failures

A predicate exception, including an error during truth conversion, aborts the
stage and raises `FilterError` with its original cause preserved. The failed
stage commits no survivor changes, rejections, or statistics. User side effects
cannot be rolled back; retrying a failed stage executes its predicates again.

```python
from whyempty import FilterError, trace

pending = trace([{"score": 90}, {}])
try:
    pending.keep("Score >= 80", lambda row: row["score"] >= 80)
except FilterError as error:
    assert error.step_index == 1
    assert error.original_index == 1
    assert error.filter_name == "Score >= 80"
    assert isinstance(error.__cause__, KeyError)
    assert pending.count == 2
    assert pending.steps == ()
```

Missing keys are errors unless the predicate explicitly supplies a default, for
example `lambda row: row.get("score", 0) >= 80`. Exceptions are never silently
treated as rejections. `KeyboardInterrupt`, `SystemExit`, and other
`BaseException` subclasses propagate unchanged. Input iteration failures also
propagate directly because construction has not completed.

## Serialization and privacy

```python
import json

summary = result.to_dict()
assert summary["first_empty_step"] == 3
payload = json.dumps(summary, allow_nan=False)
rejection_metadata = [entry.to_dict() for entry in result.rejected()]
```

The summary contains `initial_count`, `count`, `is_empty`, `first_empty_step`
(index or `None`), and a list of `steps`. It omits per-occurrence rejections to
keep the default summary proportional to the number of stages. `Step` and
`Rejection` also provide `.to_dict()`. No method automatically serializes records
or calls their `repr()`.

Filter labels appear in diagnostics and summaries, so choose labels suitable
for your logs. `FilterError` messages omit record values and cause text; Python
tracebacks retain and may display the original exception and its data.

## Performance

The reproducible runner compares three equivalent sequential list comprehensions
using the same predicates, whyempty filtering, and whyempty filtering followed
by `explain()`. Each operation starts from a prebuilt `list(range(size))` and
keeps even values, then values below 80% of the size, then multiples of five.
The baseline replaces intermediate lists as each stage completes.

Time is measured without `tracemalloc`; incremental Python allocation peaks are
measured separately while retaining one result. Input construction is excluded;
trace materialization, rejection metadata, and stage statistics are included.
Allocation peaks are **not process RSS** and are not retained-memory sizes.

Run from an installed checkout:

```sh
python benchmarks/benchmark.py --repeat 15 --number 50 \
    --json-output benchmarks/results.json
```

Measured on 2026-10-21: CPython 3.12.14, Linux x86_64.
Medians of 15 rounds × 50 operations, with rotating scenario order:

| Records | Python ms | whyempty ms | + explain ms | Trace time / Python | + explain time / Python | Python peak KiB | Trace peak KiB |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1,000 | 0.125 | 0.224 | 0.266 | 1.78× (+78%) | 2.12× (+112%) | 7.34 | 59.95 |
| 10,000 | 1.228 | 2.400 | 2.440 | 1.95× (+95%) | 1.99× (+99%) | 73.22 | 662.48 |
| 100,000 | 12.410 | 26.100 | 26.341 | 2.10× (+110%) | 2.12× (+112%) | 776.84 | 6763.54 |

Tracing used 8.16–9.05× the baseline peak allocations in this workload.
The trace-plus-explanation peak matched trace-only: the largest temporary
partition was allocated before formatting. At 100,000 records, tracing adds
about 13.7 ms over the baseline; rendering the three-stage diagnostic adds
about 0.24 ms to the measured median. No core microoptimizations were made:
the measured costs follow from the positional provenance and atomic stage
buffers required by the API.


The benchmark JSON contains every sample, environment details, parameters, and
ratios. See [benchmark methodology](https://github.com/giovannyTorres/whyempty/blob/main/benchmarks/README.md). These are synthetic
measurements on one host, not universal performance guarantees. Small differences
between trace-only and trace-plus-explanation can reflect measurement noise.

whyempty adds a Python loop, truth conversion, positional bookkeeping, temporary
partition buffers for stage atomicity, and immutable statistics. This trades time
and memory for observability. It stores no historical record snapshots.

For N input occurrences and K filters, construction is O(N), filtering is
O(sum of records reaching each stage) plus predicate work, and persistent storage
is O(N + K). Reading `.items` is O(1). `explain()` and `to_dict()` are O(K),
excluding output size; `rejected()` scans N positions and allocates one metadata
object per rejection. See [design and invariants](https://github.com/giovannyTorres/whyempty/blob/main/docs/design.md).

## Limitations

- Eager, finite inputs only; this is not a streaming pipeline.
- The trace is mutable and not thread safe; reentrant `keep()` is rejected.
- User object mutations and predicate side effects are outside rollback guarantees.
- Rejection metadata identifies the first failed filter actually executed. Later
  filters are not evaluated on rejected records; this is not counterfactual analysis.
- Standard `len()` determines text-column widths; emoji and wide Unicode
  characters can affect visual alignment.
- No automatic capture of comprehensions, Pandas/Polars integration, CLI, remote
  services, or distributed execution is included in 0.1.0.

## Development and release

```sh
python -m pip install -e '.[dev]'
python -m pytest --cov=whyempty --cov-report=term-missing
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m build
python -m twine check dist/*
```

CI tests CPython 3.10–3.15, enforces at least 95% branch-inclusive coverage,
and checks typing, formatting, distribution contents, and wheel installation.
Publication remains manual. See [CONTRIBUTING.md](https://github.com/giovannyTorres/whyempty/blob/main/CONTRIBUTING.md)
for release instructions and TestPyPI/PyPI commands. MIT licensed.

## Related work

[Coffea cutflows](https://github.com/scikit-hep/coffea/blob/master/src/coffea/analysis_tools.py)
already describe cumulative selection counts for array-based analyses.
[more-itertools](https://github.com/more-itertools/more-itertools) provides iterable
filtering utilities, and [IceCream](https://github.com/gruns/icecream) helps inspect
expressions. whyempty focuses on explicit sequential predicates over general
Python iterables, positional first-rejection metadata, and data-free summaries
with no required dependencies. This is not a claim that filter diagnostics are new.
