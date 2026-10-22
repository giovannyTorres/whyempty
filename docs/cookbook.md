# Cookbook: whyempty

Three common operational problems, with complete Python code and asserted outcomes. The records are **synthetic fixtures modeled on real workflows**, not measurements from a business or real customer data.

Install `python -m pip install "whyempty==0.2.1"`. From a checkout, run all three with `python examples/cookbook.py`.

<a id="locate-emptying-rule"></a>
## Debug an empty hotel catalog search

**Problem.** Two CDMX hotels pass the city rule, but both exceed the chosen budget.

**Expected result.** Identify Budget <= 1000 as the emptying stage with two records entering it.

Copy the complete block into a fresh Python file and run it:

```python
from whyempty import FilterError, Pipeline, trace


def locate_emptying_rule():
    hotels = [
        {"id": "A", "city": "CDMX", "price": 1200},
        {"id": "B", "city": "CDMX", "price": 1800},
        {"id": "C", "city": "Puebla", "price": 800},
    ]
    result = (
        trace(hotels)
        .keep("CDMX", lambda row: row["city"] == "CDMX")
        .keep("Budget <= 1000", lambda row: row["price"] <= 1000)
    )
    assert result.items == ()
    assert result.first_empty_step.name == "Budget <= 1000"
    assert result.first_empty_step.before == 2
    return result.explain()


print(locate_emptying_rule())
```

**Apply it to your data.** Trace shows sequential effects. Later rules on zero input cannot explain the earlier elimination.

<a id="inspect-alternatives"></a>
## Inspect catalog alternatives without rerunning rules

**Problem.** One offer is affordable but out of stock; another is in stock but over budget.

**Expected result.** Audit both rules, inspect each single-rule relaxation and retrieve the original position of the alternative.

Copy the complete block into a fresh Python file and run it:

```python
from whyempty import FilterError, Pipeline, trace


def inspect_alternatives():
    offers = [{"price": 800, "in_stock": False}, {"price": 1500, "in_stock": True}]
    rules = (
        Pipeline()
        .keep("In stock", lambda row: row["in_stock"])
        .keep("Budget <= 1000", lambda row: row["price"] <= 1000)
    )
    result = rules.audit(offers)
    assert result.is_empty
    assert result.relax(2).remaining == 1
    assert result.matching_indices(without=(2,)) == (1,)
    assert result.matching_indices(without=(1,)) == (0,)
    assert len(result.suggest_relaxations()) == 2
    return result.explain()


print(inspect_alternatives())
```

**Apply it to your data.** The queries do not change stock, prices, rules or the audit. They are recorded what-if projections.

<a id="debug-malformed-import"></a>
## Find a malformed imported record

**Problem.** One imported row has no price field, so a predicate raises KeyError.

**Expected result.** Read original position 1 and the original cause from FilterError; verify the failed trace stage leaves state unchanged.

Copy the complete block into a fresh Python file and run it:

```python
from whyempty import FilterError, Pipeline, trace


def debug_malformed_import():
    result = trace([{"price": 500}, {}])
    try:
        result.keep("Budget", lambda row: row["price"] < 1000)
    except FilterError as error:
        assert error.original_index == 1
        assert isinstance(error.__cause__, KeyError)
        assert result.count == 2 and result.steps == ()
        return "Malformed source row 1; the failed stage committed no filtering changes."
    raise AssertionError("Expected FilterError")


print(debug_malformed_import())
```

**Apply it to your data.** Predicate side effects cannot be rolled back. Validate or quarantine the bad input before retrying.

[API details and error policies](api.md) · [Comparison with primitives](comparison.md) · [Benchmark evidence](../benchmarks/RESULTS.md)
