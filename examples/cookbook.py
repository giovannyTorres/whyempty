"""Three catalog-filter debugging problems using deterministic synthetic records."""

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


if __name__ == "__main__":
    for recipe in (locate_emptying_rule, inspect_alternatives, debug_malformed_import):
        print(recipe.__name__, recipe(), sep="\n")
