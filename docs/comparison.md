# Comparison: whyempty and the underlying primitives

A product search returns nothing after several conditions. whyempty traces the actual elimination stages or audits every rule to show which recorded matches would return if selected conditions were relaxed.

## What is compared

| Dimension | Scope |
|---|---|
| Existing tools | Python list comprehensions and pandas boolean masks filter records directly; manual counters and masks can add diagnostics. |
| Shared result checked | Identical surviving record references in original order. The scale benchmark separates sequential filtering from full evaluation of every rule. |
| Additional package behavior | Named elimination stages, original rejection positions, independent failure counts and queries over recorded relaxation outcomes. |
| Cost / when a manual recipe fits | Tracing and auditing add metadata storage and execution overhead. Auditing evaluates every rule on every record; a short-circuit filter can do less work. |

The comparison is against Python filtering. The package provides filtering diagnostics with zero required runtime dependencies; it implements no inferential statistical tests. The comparison below measures a Python workflow; it makes no claim of feature parity or numerical parity with an R package.

## Full executable example

Save this as `comparison.py` after installing the release, or run `python examples/comparison.py` from this repository. The assertions verify the stated shared result.

```python
"""Same surviving records; trace additionally explains the first empty stage."""

from whyempty import trace


def baseline(records):
    active = [row for row in records if row["active"]]
    local = [row for row in active if row["country"] == "MX"]
    return tuple(row for row in local if row["score"] >= 80)


def library(records):
    return (
        trace(records)
        .keep("Active", lambda row: row["active"])
        .keep("Mexico", lambda row: row["country"] == "MX")
        .keep("Score >= 80", lambda row: row["score"] >= 80)
        .items
    )


if __name__ == "__main__":
    records = [
        {"active": True, "country": "MX", "score": 40},
        {"active": False, "country": "MX", "score": 90},
        {"active": True, "country": "US", "score": 95},
    ]
    assert baseline(records) == library(records) == ()
    result = (
        trace(records)
        .keep("Active", lambda row: row["active"])
        .keep("Mexico", lambda row: row["country"] == "MX")
        .keep("Score >= 80", lambda row: row["score"] >= 80)
    )
    assert result.first_empty_step.name == "Score >= 80"
    print("Both return zero records; the first empty stage is Score >= 80.")
```

## How to choose

Use the package when you need its named diagnostics, explicit policies or provenance repeatedly. Keep the underlying pandas/Python recipe when that smaller shared result meets the job. Review each recipe's data assumptions before applying it to another dtype or layout.

Tracing and auditing add metadata storage and execution overhead. Auditing evaluates every rule on every record; a short-circuit filter can do less work.

## Evidence and boundaries

All six scenarios are checked for identical survivors before timing. Trace uses a sequential Python baseline; audit uses a baseline evaluating every rule on every record.

The benchmark uses cheap integer predicates and nonempty results. It does not time suggestion ranking over many minimal failure patterns, expensive I/O predicates or concurrent mutation. Timing differences do not establish statistical accuracy or developer productivity. The benchmark checks exact fixture outputs and separately reports code-size counts as a limited usability proxy.

[Actual measured results](../benchmarks/RESULTS.md) · [Reproduce the benchmark](../benchmarks/README.md) · [Recipes](cookbook.md) · [API contracts](api.md)

## Sources and alternatives

- [pandas API documentation](https://pandas.pydata.org/docs/reference/index.html) documents the underlying grouping, masking and reshaping primitives.
- [Python filter documentation](https://docs.python.org/3/library/functions.html#filter)
- [Python comprehension semantics](https://docs.python.org/3/tutorial/datastructures.html#list-comprehensions)

Upstream references credit problem ideas and existing tools. This repository contains its own implementation and claims no upstream affiliation.
