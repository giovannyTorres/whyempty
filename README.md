# whyempty

**Find why your filters returned nothing—and which changes would recover matches.**

A typed Python toolkit to trace actual eliminations, reuse filtering rules,
audit every failed condition, and explore alternatives from recorded decisions.
Python 3.10+, MIT licensed, **zero required runtime dependencies**.

## Install

```sh
python -m pip install whyempty==0.2.0
```

For a source checkout:

```sh
git clone https://github.com/giovannyTorres/whyempty.git
cd whyempty
python -m pip install -e .
python examples/basic_usage.py
python examples/audit_usage.py
```

## Trace actual eliminations

The original 0.1 API works unchanged:

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
```

Example output; timings vary:

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

Only survivors reach the next stage. Later zero-input stages are marked skipped,
never blamed for an earlier elimination. Initially empty input is identified
separately. Significant reduction means at least 50% removed from a nonempty
stage; it is a descriptive threshold, not statistical significance.

## Reuse rules and audit every failure

```python
from whyempty import Pipeline

rules = (
    Pipeline()
    .keep("Active", lambda row: row["active"])
    .keep("Mexico", lambda row: row["country"] == "MX")
    .keep("Score >= 80", lambda row: row["score"] >= 80)
)
traced = rules.run(records)  # Sequential Trace, as above.
audited = rules.audit(records)  # Every rule on every occurrence.
print(audited.explain())
```

Use the same pipeline with different datasets. In typed applications use
`Pipeline[Record]()` with your record type, such as a `TypedDict`; see the
[executable audit example](https://github.com/giovannyTorres/whyempty/blob/main/examples/audit_usage.py).

Independent counts for the example:

| Filter | Evaluated | Passed | Failed | Only blocker |
| --- | ---: | ---: | ---: | ---: |
| 1. Active | 3 | 2 | 1 | 1 |
| 2. Mexico | 3 | 2 | 1 | 1 |
| 3. Score >= 80 | 3 | 2 | 1 | 1 |

`Only blocker` counts occurrences failing that filter alone. Mexico passes two
records independently, although only one reached it in the sequential trace.
Inspect all failures of an occurrence using its zero-based original position:

```python
assert [rule.name for rule in audited.failed_filters(0)] == ["Score >= 80"]
assert audited.filters[1].exclusive_failures == 1
```

`audit()` evaluates in input order and, within each occurrence, rule-definition
order. Every predicate and its truth conversion execute once. It does not
short-circuit: **each predicate must be defined on every record**. A first rule
checking `"score" in row` does not protect a later `row["score"]` access during
an audit. Use `row.get("score", 0)` if a default is your intended rule.
Sequential `run()` continues to support guards protecting later filters.

## Explore changes without rerunning predicates

```python
change = audited.relax(3)  # Disable one-based filter index 3.
assert change.filter_names == ("Score >= 80",)
assert change.remaining == 1
assert change.rescued == 1
assert audited.matching_indices(without=(3,)) == (0,)

# Multiple identities are normalized to sorted unique indices.
assert audited.relax(3, 2, 3).filter_indices == (2, 3)
assert audited.relax(2, 3).remaining == 2
assert audited.is_empty  # Queries do not change the result.
```

`remaining` includes current matches; `rescued` counts additional matches.
`matching_indices()` returns original positions; retain your input if you need
the corresponding records. Names may repeat, so rule identities are one-based
indices. Boolean/noninteger indices raise `TypeError`; out-of-range indices
raise `IndexError`. Negative original positions are also rejected.

Projections are exact for the **recorded decisions**. Repeating them in another
execution requires stable predicates and unchanged records. Prefer pure rules;
queries never execute predicates or read record fields.

## Find the smallest change that restores matches

```python
suggestions = audited.suggest_relaxations(limit=3)
assert [entry.filter_indices for entry in suggestions] == [(1,), (2,), (3,)]
assert all(entry.rescued == 1 for entry in suggestions)
```

For an empty result with nonempty input, suggestions disable the **fewest
filters** needed to recover at least one recorded match. Among equally small
sets, more rescued records rank first, then filter indices lexicographically.
The default limit is five and must be a positive integer.

This is minimum **cardinality**, not every set minimal by inclusion. If `{A}`
recovers one record and `{B, C}` recovers ten, only `{A}` is a fewest-filter
suggestion. Inspect other combinations explicitly with `relax()`.
Empty input or an already nonempty result needs no suggestions.

Suggestions describe the supplied dataset, not logical incompatibility for all
possible inputs. They do not automatically change your rules. The implementation
groups observed failure sets into integer bitmasks instead of searching all 2^K
subsets. There is no 64-filter limit.

## API

| API | Behavior |
| --- | --- |
| `trace(iterable)` / `Trace(iterable)` | Consume input once into an eager mutable trace. |
| `Trace.keep(name, predicate)` | Keep truthy matches, record statistics, return the same trace. |
| `Trace.items`, `.initial_count`, `.count`, `.is_empty` | Survivor tuple and counts. |
| `Trace.steps`, `.first_empty_step` | Frozen `Step` snapshot and first emptying stage or `None`. |
| `Trace.rejected()` | First-rejection metadata, in original order. |
| `Pipeline[T]().keep(name, predicate)` | Configure reusable rules and return the same pipeline. |
| `Pipeline.filter_names` | Tuple snapshot of configured names. |
| `Pipeline.run(iterable)` / `.audit(iterable)` | Sequential `Trace[T]` or independent `AuditResult[T]`. |
| `AuditResult.items`, `.initial_count`, `.count`, `.is_empty` | References passing every rule and counts. |
| `AuditResult.filters`, `.elapsed_seconds` | Frozen `FilterStats` and total audit time. |
| `AuditResult.failed_filters(original_index)` | All failed filter statistics for one occurrence. |
| `AuditResult.relax(*filter_indices)` | Frozen `Relaxation` with projected counts. |
| `AuditResult.matching_indices(without=())` | Original positions matching the selected combination. |
| `AuditResult.suggest_relaxations(limit=5)` | Fewest-filter suggestions for an empty result. |
| Results: `.explain()` / `.to_dict()` | Recorded diagnostics as text / JSON-compatible metadata. |

`Step`: `index`, `name`, `before`, `removed`, `remaining`, `retention_pct`,
`elapsed_seconds`, `emptied`, `skipped`, `significant_reduction`. Stage time
includes partitioning and provenance, excluding formatting and `Step` creation.

`FilterStats`: `index`, `name`, `tested`, `passed`, `failed`, `exclusive_failures`,
`retention_pct`. Audit time includes input iteration, evaluation, and outcome
recording; it is not per-filter timing. Retention is `None` for zero input,
serialized as `null` and displayed as `N/A` in sequential traces.

`Rejection`: `original_index`, `step_index`, `filter_name`.
`Relaxation`: `filter_indices`, `filter_names`, `remaining`, `rescued`.
All four models are frozen dataclasses with `.to_dict()`.

Both kinds of `keep()` mutate and return their object. Tuples already retrieved
remain snapshots. Each pipeline execution snapshots its rules **before consuming
input**; configuration changes affect future runs. Survivor references are
shared, not deep-copied. Labels must be nonblank printable strings. Repeated
values and labels are supported.

## Errors, rejected records, and privacy

```python
from whyempty import FilterError, trace

pending = trace([{"score": 90}, {}])
try:
    pending.keep("Score >= 80", lambda row: row["score"] >= 80)
except FilterError as error:
    assert error.step_index == 1 and error.original_index == 1
    assert isinstance(error.__cause__, KeyError)
    assert pending.count == 2 and pending.steps == ()
```

Predicate and truth-conversion errors preserve their original cause. Failed
trace stages commit no state; failed audits return no partial result. Side
effects cannot be rolled back, and retrying an execution runs predicates again.
`BaseException` and input-iteration failures propagate directly. Exceptions are
never silently converted into rejections.

```python
import json

payload = json.dumps(audited.to_dict(), allow_nan=False)
for rejection in result.rejected():
    print(rejection.original_index, rejection.step_index, rejection.filter_name)
    original_record = records[rejection.original_index]
```

Summaries omit original records, record representations, predicates, and
per-occurrence decisions. Audit summaries include at most five suggestions.
Diagnostics never call record `repr()` or print anything themselves. Labels are
visible, so choose names suitable for logs. Tracebacks may retain and display
original exception data.

Results retain survivor references and metadata, not predicates or rejected
records. An object may remain referenced by another surviving occurrence, the
caller, or a traceback. A `Pipeline` intentionally retains its configured
callables. Retain your input if you need rejected values later.

## Performance and storage

Measured with CPython 3.12.14 on Linux x86_64, using 12 rotating rounds
of 20 operations per scenario. Times are medians in milliseconds:

| Records | Python sequential | Trace | Trace + explain | Python all rules | Audit | Audit + queries |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1,000 | 0.103 | 0.197 | 0.224 | 0.264 | 0.645 | 0.694 |
| 10,000 | 0.990 | 1.850 | 1.925 | 2.554 | 6.259 | 6.973 |
| 100,000 | 10.072 | 21.810 | 21.740 | 24.864 | 62.197 | 67.562 |

At 100,000 records, tracing costs 2.17× its sequential Python baseline.
Auditing costs 2.50× the full-evaluation baseline, which also runs every rule
for every record. Audit plus diagnostic queries takes 67.562 ms. Its peak
allocation is 1,693.95 KiB versus 65.83 KiB for the full-evaluation baseline;
tracing peaks at 6,763.54 KiB versus 776.84 KiB for sequential Python.

Auditing is more expensive because it evaluates all conditions and records
positional failure masks and aggregate statistics. The smaller audit peak
than trace in this three-rule workload reflects compact masks and one-pass
recording; it is not a general memory guarantee. Full evaluation without
observability stores only its final survivors, so its memory baseline is low.

`Audit + queries` builds a new audit, formats its explanation, calls
`relax(2)`, obtains `matching_indices(without=(2,))`, and asks for suggestions.
This benchmark has surviving records, so suggestions return an empty tuple;
it does not time ranking large collections of minimal failure patterns.
Small differences such as trace plus explanation being slightly faster than
trace alone reflect host noise. These synthetic results are not performance
guarantees for other predicates, filter counts, or selectivity.

Reproduce the six-scenario benchmark from an installed checkout:

```sh
python benchmarks/benchmark.py --repeat 12 --number 20 \
    --json-output benchmarks/results.json
```

Equivalent sequential and full-evaluation Python baselines are measured.
Timing runs without instrumentation; incremental `tracemalloc` peaks are
measured separately with one live result. Peaks are not RSS or retained memory.
Input construction and pipeline configuration are excluded. See the full
[methodology](https://github.com/giovannyTorres/whyempty/blob/main/benchmarks/README.md)
and [samples](https://github.com/giovannyTorres/whyempty/blob/main/benchmarks/results.json).
Historical 0.1.0 measurements are preserved separately.

Sequential filters evaluate stage survivors; audits make exactly N×K predicate
calls. Audit metadata stores masks and their frequencies. `relax()` scans U
observed patterns; `matching_indices()` scans N positions. Suggestions rank
observed patterns with a bounded heap, without a 2^K search. Bitmask operations
scale with the number of filter bits. See
[design and invariants](https://github.com/giovannyTorres/whyempty/blob/main/docs/design.md).

## Limitations and development

Finite inputs only. Traces materialize input; audits consume it in one pass but
retain positional metadata. Pipelines and traces are mutable and not thread
safe; reentrant `Trace.keep()` is rejected. Wide Unicode names may affect visual
column alignment. There is no automatic comprehension capture, native
Pandas/Polars integration, CLI, or distributed execution.

```sh
python -m pip install -e '.[dev]'
python -m pytest --cov=whyempty --cov-report=term-missing
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m build
python -m twine check dist/*
```

CI tests CPython 3.10–3.15 and requires at least 95% branch-inclusive coverage.
It also checks distributions and isolated wheel installation. Publication uses
a maintainer-triggered workflow; see
[CONTRIBUTING.md](https://github.com/giovannyTorres/whyempty/blob/main/CONTRIBUTING.md)
and the [changelog](https://github.com/giovannyTorres/whyempty/blob/main/CHANGELOG.md).

## Related work

[Coffea cutflows](https://github.com/scikit-hep/coffea/blob/master/src/coffea/analysis_tools.py)
describe cumulative array-based selections.
[more-itertools](https://github.com/more-itertools/more-itertools) supplies iterable
utilities, and [IceCream](https://github.com/gruns/icecream) inspects expressions.
whyempty combines general predicates, positional provenance, independent audits,
and cached filter-relaxation analysis. This is not a claim of novelty.
