# whyempty

**Find the rule that emptied your filters, then inspect recorded alternatives.**

A product search returns nothing after several conditions. whyempty traces the actual elimination stages or audits every rule to show which recorded matches would return if selected conditions were relaxed.

## Try it in two minutes

Requires Python 3.10+. Install the [published release](https://pypi.org/project/whyempty/0.2.1/):

```sh
python -m pip install "whyempty==0.2.1"
```

Copy this complete example into a Python session or save it as `demo.py` and run `python demo.py`:

```python
from whyempty import trace

records = [
    {"active": True, "country": "MX", "score": 40},
    {"active": False, "country": "MX", "score": 90},
    {"active": True, "country": "US", "score": 95},
]
result = (
    trace(records)
    .keep("Active", lambda row: row["active"])
    .keep("Mexico", lambda row: row["country"] == "MX")
    .keep("Score >= 80", lambda row: row["score"] >= 80)
)
assert result.items == ()
assert result.first_empty_step.name == "Score >= 80"
print(result.explain())
```

The example returns **zero matches** and identifies **Score >= 80** as the first rule that empties the remaining records.

## What you gain

Named stages retain first-rejection positions. A reusable Pipeline can also record all failures and answer relaxation queries without rerunning predicates.

| Existing approach | What this package adds | Tradeoff |
|---|---|---|
| Python list comprehensions and pandas boolean masks filter records directly; manual counters and masks can add diagnostics. | Named elimination stages, original rejection positions, independent failure counts and queries over recorded relaxation outcomes. | Tracing and auditing add metadata storage and execution overhead. Auditing evaluates every rule on every record; a short-circuit filter can do less work. |

[Run the side-by-side comparison](docs/comparison.md): both implementations are included and their shared outputs are asserted equal. The comparison is against Python filtering. The package provides filtering diagnostics with zero required runtime dependencies; it implements no inferential statistical tests.

## Solve a real workflow problem

These small, synthetic operational fixtures make the workflows reproducible without external services or private records. Each recipe includes expected results and a failure or interpretation boundary.

| Recipe | Verified outcome |
|---|---|
| [Debug an empty hotel catalog search](docs/cookbook.md#locate-emptying-rule) | Identify Budget <= 1000 as the emptying stage with two records entering it. |
| [Inspect catalog alternatives without rerunning rules](docs/cookbook.md#inspect-alternatives) | Audit both rules, inspect each single-rule relaxation and retrieve the original position of the alternative. |
| [Find a malformed imported record](docs/cookbook.md#debug-malformed-import) | Read original position 1 and the original cause from FilterError; verify the failed trace stage leaves state unchanged. |

From a checkout, after installing the package:

```sh
python examples/comparison.py
python examples/cookbook.py
```

## Measured performance, accuracy and usability

Recorded on Windows-11-10.0.26200-SP0, CPython 3.13.5, with five rotating timed rounds. At the largest measured input size (50,000; see workload definition):

| Compared operation | Baseline median ms | Package median ms | Package / baseline |
|---|---:|---:|---:|
| Trace / sequential Python | 5.809 | 13.164 | 2.27x |
| Audit / all-rules Python | 12.809 | 33.630 | 2.63x |

Ratio = package median / baseline median; above 1 means higher latency. The package performs the extra diagnostic or provenance work described above. These single-host synthetic results have no universal speed guarantee. Allocation measurements and the smaller scales are in the full table.

[Measured table](benchmarks/RESULTS.md) · [Raw repeated samples](benchmarks/latest.json) · [Reproduction instructions](benchmarks/README.md)

Accuracy means agreement on the stated fixture outputs: All six scenarios are checked for identical survivors before timing. Trace uses a sequential Python baseline; audit uses a baseline evaluating every rule on every record. Code-size counts are an inspectable usability proxy; no developer-time study was performed.

## Scope and limits

- Inputs are materialized in memory. Survivor references are shared rather than deep-copied.
- Use stable predicates for projected alternatives. Queries describe recorded outcomes; changing predicate state can change a rerun.
- Filter indices are one-based; original record positions are zero-based.
- Predicate errors raise FilterError with the original cause; labels are visible in diagnostic summaries.

## Documentation

- [Start here](docs/index.md): choose a workflow and find the relevant guide.
- [Comparison and alternatives](docs/comparison.md): full code, shared behavior and added outputs.
- [Cookbook](docs/cookbook.md): three complete problem-solving recipes.
- [API and behavioral contracts](docs/api.md): exact semantics and errors.
- [Benchmark methodology](benchmarks/README.md): inputs, correctness checks, environment and limits.
- [Design notes](docs/design.md): tracing, audit storage and recorded outcomes.

## Develop and validate

```sh
python -m pip install -e ".[dev]"
python scripts/check_docs.py
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy src
```

MIT licensed. Contributions should include a reproducing example and the expected behavior. See [CONTRIBUTING.md](CONTRIBUTING.md).
