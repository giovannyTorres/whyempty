"""Independent audit statistics and exact counterfactual queries."""

import gc
import itertools
import json
import random
import weakref
from collections.abc import Iterator
from dataclasses import FrozenInstanceError

import pytest

from whyempty import AuditResult, FilterError, FilterStats, Pipeline, Relaxation


def audit_matrix(matrix: list[tuple[bool, ...]], width: int) -> AuditResult[int]:
    """Use row positions as records and cached outcomes as independent rules."""
    pipeline = Pipeline[int]()
    for column in range(width):
        pipeline.keep(f"rule {column + 1}", lambda row, column=column: matrix[row][column])
    return pipeline.audit(range(len(matrix)))


def test_audit_statistics_measure_each_rule_on_the_full_input() -> None:
    result = audit_matrix([(True, True), (False, True), (True, False), (False, False)], 2)
    assert result.initial_count == 4
    assert result.items == (0,)
    assert result.count == 1
    assert not result.is_empty
    assert result.elapsed_seconds >= 0
    assert [
        (s.index, s.name, s.tested, s.passed, s.failed, s.exclusive_failures)
        for s in result.filters
    ] == [
        (1, "rule 1", 4, 2, 2, 1),
        (2, "rule 2", 4, 2, 2, 1),
    ]
    assert all(s.retention_pct == 50 for s in result.filters)
    assert result.failed_filters(0) == ()
    assert result.failed_filters(1) == (result.filters[0],)
    assert result.failed_filters(2) == (result.filters[1],)
    assert result.failed_filters(3) == result.filters


def test_no_rules_preserves_every_record_and_has_no_failures() -> None:
    result = Pipeline[int]().audit([3, 1, 3])
    assert result.items == (3, 1, 3)
    assert result.initial_count == result.count == 3
    assert result.filters == ()
    assert result.failed_filters(0) == ()
    assert result.failed_filters(2) == ()
    assert result.matching_indices() == (0, 1, 2)
    assert result.suggest_relaxations() == ()
    assert "No filters" in result.explain()
    assert result.to_dict()["filters"] == []
    relaxation = result.relax()
    assert relaxation.filter_indices == relaxation.filter_names == ()
    assert relaxation.remaining == 3
    assert relaxation.rescued == 0


def test_empty_input_still_has_independent_zero_statistics() -> None:
    pipeline = Pipeline[object]().keep("never called", lambda _: pytest.fail("called"))
    result = pipeline.audit(iter(()))
    assert result.items == ()
    assert result.initial_count == result.count == 0
    assert result.is_empty
    assert result.filters[0].tested == 0
    assert result.filters[0].passed == result.filters[0].failed == 0
    assert result.filters[0].exclusive_failures == 0
    assert result.filters[0].retention_pct is None
    assert result.relax(1).remaining == 0
    assert result.matching_indices(without=[1]) == ()
    assert result.suggest_relaxations() == ()
    assert "empty" in result.explain().lower()


def test_relaxation_includes_existing_survivors_and_counts_only_new_rescues() -> None:
    result = audit_matrix([(True, True), (False, True), (True, False), (False, False)], 2)
    one = result.relax(1)
    assert one.filter_indices == (1,)
    assert one.filter_names == ("rule 1",)
    assert one.remaining == 2
    assert one.rescued == 1
    assert result.matching_indices(without=[1]) == (0, 1)
    both = result.relax(2, 1, 2, 1)
    assert both.filter_indices == (1, 2)
    assert both.filter_names == ("rule 1", "rule 2")
    assert both.remaining == 4
    assert both.rescued == 3
    assert result.matching_indices(without=iter([2, 1, 2])) == (0, 1, 2, 3)
    assert result.relax().remaining == result.count
    assert result.relax().rescued == 0


def test_suggestions_minimize_disabled_rule_count_before_ranking_rescues() -> None:
    matrix = [(False, True, True)] + [(True, False, False)] * 10
    result = audit_matrix(matrix, 3)
    suggestions = result.suggest_relaxations()
    assert len(suggestions) == 1
    assert suggestions[0].filter_indices == (1,)
    assert suggestions[0].rescued == 1
    assert result.relax(2, 3).rescued == 10


def test_suggestions_rank_by_rescue_then_lexicographic_rule_indices() -> None:
    matrix = (
        [(False, False, True, True)] * 3
        + [(True, True, False, False)] * 3
        + [(False, True, False, True)] * 2
    )
    result = audit_matrix(matrix, 4)
    suggestions = result.suggest_relaxations()
    assert [s.filter_indices for s in suggestions] == [(1, 2), (3, 4), (1, 3)]
    assert [s.rescued for s in suggestions] == [3, 3, 2]
    assert result.suggest_relaxations(limit=2) == suggestions[:2]


def test_default_suggestion_limit_is_five() -> None:
    matrix = [tuple(row != col for col in range(7)) for row in range(7)]
    result = audit_matrix(matrix, 7)
    assert len(result.suggest_relaxations()) == 5
    assert [s.filter_indices for s in result.suggest_relaxations(limit=10)] == [
        (n,) for n in range(1, 8)
    ]
    assert len(result.to_dict()["suggestions"]) == 5  # type: ignore[arg-type]


@pytest.mark.parametrize("seed", range(10))
def test_all_queries_match_cached_boolean_matrix_oracle(seed: int) -> None:
    rng = random.Random(seed)
    width = 5
    matrix = [tuple(bool(rng.randrange(2)) for _ in range(width)) for _ in range(25)]
    result = audit_matrix(matrix, width)
    survivor_indices = tuple(i for i, row in enumerate(matrix) if all(row))
    assert result.items == survivor_indices
    assert result.count == len(survivor_indices)
    for column, stat in enumerate(result.filters):
        assert stat.passed == sum(row[column] for row in matrix)
        assert stat.failed == sum(not row[column] for row in matrix)
        assert stat.exclusive_failures == sum(
            not row[column] and sum(not passed for passed in row) == 1 for row in matrix
        )
    failure_sets = [tuple(i + 1 for i, passed in enumerate(row) if not passed) for row in matrix]
    for original_index, failures in enumerate(failure_sets):
        assert tuple(s.index for s in result.failed_filters(original_index)) == failures
    for disabled_count in range(width + 1):
        for disabled in itertools.combinations(range(1, width + 1), disabled_count):
            expected = tuple(
                i for i, failures in enumerate(failure_sets) if set(failures) <= set(disabled)
            )
            relaxation = result.relax(*disabled)
            assert result.matching_indices(without=disabled) == expected
            assert relaxation.remaining == len(expected)
            assert relaxation.rescued == len(expected) - result.count
    if survivor_indices:
        assert result.suggest_relaxations() == ()
    else:
        minimum = min(map(len, failure_sets))
        candidates = set(failures for failures in failure_sets if len(failures) == minimum)
        expected_suggestions = sorted(
            candidates, key=lambda failures: (-failure_sets.count(failures), failures)
        )[:5]
        assert [s.filter_indices for s in result.suggest_relaxations()] == expected_suggestions


def test_duplicate_names_are_disambiguated_by_indices() -> None:
    result = (
        Pipeline[int]().keep("same", lambda n: n > 1).keep("same", lambda n: n < 1).audit([0, 2])
    )
    assert [s.name for s in result.filters] == ["same", "same"]
    assert tuple(s.index for s in result.failed_filters(0)) == (1,)
    assert tuple(s.index for s in result.failed_filters(1)) == (2,)
    assert result.relax(2, 1).filter_names == ("same", "same")
    assert result.relax(2, 1).filter_indices == (1, 2)


def test_outcomes_are_cached_without_predicate_or_truth_conversion_reevaluation() -> None:
    predicate_calls: list[int] = []
    bool_calls: list[int] = []

    class Truth:
        def __init__(self, n: int) -> None:
            self.n = n

        def __bool__(self) -> bool:
            bool_calls.append(self.n)
            return self.n % 2 == 0

    def predicate(n: int) -> Truth:
        predicate_calls.append(n)
        return Truth(n)

    result = Pipeline[int]().keep("even", predicate).audit(range(4))
    for _ in range(3):
        result.explain()
        result.to_dict()
        result.relax(1)
        result.matching_indices(without=[1])
        result.suggest_relaxations()
        result.failed_filters(1)
    assert result.items == (0, 2)
    assert predicate_calls == bool_calls == [0, 1, 2, 3]


@pytest.mark.parametrize("value", [True, 1, -1, "yes", [0], {"x": 0}])
def test_audit_accepts_truthy_return_values(value: object) -> None:
    result = Pipeline[str]().keep("truth", lambda _: value).audit(["record"])
    assert result.items == ("record",)
    assert result.filters[0].passed == 1


@pytest.mark.parametrize("value", [False, None, 0, "", [], {}, ()])
def test_audit_accepts_falsy_return_values(value: object) -> None:
    result = Pipeline[str]().keep("truth", lambda _: value).audit(["record"])
    assert result.is_empty
    assert result.filters[0].exclusive_failures == 1


def test_audit_exception_after_earlier_rule_failure_is_not_short_circuited() -> None:
    pipeline = Pipeline[dict[str, int]]().keep("none", lambda _: False)
    pipeline.keep("required", lambda row: row["required"])
    with pytest.raises(FilterError) as caught:
        pipeline.audit([{"required": 1}, {}])
    assert isinstance(caught.value.__cause__, KeyError)
    assert caught.value.original_index == 1
    assert caught.value.step_index == 2
    assert caught.value.filter_name == "required"
    assert pipeline.audit([{"required": 1}]).is_empty


def test_audit_predicate_failure_stops_calls_and_preserves_original_cause() -> None:
    calls: list[tuple[str, int]] = []
    cause = ArithmeticError("private exception text")

    def broken(n: int) -> bool:
        calls.append(("broken", n))
        raise cause

    pipeline = Pipeline[int]().keep("broken", broken)
    pipeline.keep("later", lambda n: calls.append(("later", n)))
    with pytest.raises(FilterError) as caught:
        pipeline.audit([1, 2])
    assert caught.value.__cause__ is cause
    assert "private exception text" not in str(caught.value)
    assert calls == [("broken", 1)]
    assert pipeline.audit([]).initial_count == 0


def test_audit_truth_conversion_failure_has_rule_and_record_context() -> None:
    cause = ValueError("bad truth")

    class BadTruth:
        def __bool__(self) -> bool:
            raise cause

    with pytest.raises(FilterError) as caught:
        Pipeline[int]().keep("truth", lambda _: BadTruth()).audit([0])
    assert caught.value.__cause__ is cause
    assert caught.value.filter_name == "truth"
    assert caught.value.original_index == 0
    assert caught.value.step_index == 1


@pytest.mark.parametrize("exception", [KeyboardInterrupt(), SystemExit(2), GeneratorExit()])
def test_audit_does_not_wrap_base_exceptions(exception: BaseException) -> None:
    def interrupt(_: int) -> bool:
        raise exception

    pipeline = Pipeline[int]().keep("interrupt", interrupt)
    with pytest.raises(type(exception)) as caught:
        pipeline.audit([1])
    assert caught.value is exception
    assert pipeline.audit([]).initial_count == 0


def test_input_iteration_exception_propagates_unchanged() -> None:
    cause = OSError("input failed")

    def broken_input() -> Iterator[int]:
        yield 1
        raise cause

    with pytest.raises(OSError) as caught:
        Pipeline[int]().keep("all", lambda _: True).audit(broken_input())
    assert caught.value is cause


def test_audit_snapshots_rules_before_input_is_consumed() -> None:
    pipeline = Pipeline[int]().keep("all", lambda _: True)

    def source() -> Iterator[int]:
        pipeline.keep("future only", lambda _: False)
        yield 1
        yield 2

    result = pipeline.audit(source())
    assert result.items == (1, 2)
    assert tuple(s.name for s in result.filters) == ("all",)
    assert pipeline.audit([1, 2]).is_empty


def test_audit_snapshots_rules_before_predicate_changes_pipeline() -> None:
    pipeline = Pipeline[int]()
    added = False

    def mutate(_: int) -> bool:
        nonlocal added
        if not added:
            pipeline.keep("future only", lambda _: False)
            added = True
        return True

    pipeline.keep("mutator", mutate)
    result = pipeline.audit([1, 2])
    assert result.items == (1, 2)
    assert len(result.filters) == 1
    assert pipeline.audit([1, 2]).is_empty


def test_single_pass_input_and_duplicate_unhashable_occurrences() -> None:
    shared = {"value": 1}
    values = [shared, {"value": 1}, shared, {"value": 2}]

    class OnePass:
        def __init__(self) -> None:
            self.values = iter(values)
            self.iterations = 0

        def __iter__(self) -> "OnePass":
            self.iterations += 1
            if self.iterations > 1:
                raise AssertionError("input consumed twice")
            return self

        def __next__(self) -> dict[str, int]:
            return next(self.values)

    source = OnePass()
    outcomes = iter([True, False, False, True])
    result = Pipeline[dict[str, int]]().keep("occurrence", lambda _: next(outcomes)).audit(source)
    assert result.items == (shared, values[3])
    assert result.items[0] is shared
    assert result.matching_indices() == (0, 3)
    assert tuple(s.index for s in result.failed_filters(2)) == (1,)
    assert source.iterations == 1
    assert values == [{"value": 1}, {"value": 1}, {"value": 1}, {"value": 2}]


@pytest.mark.parametrize("index", [True, False, None, 1.0, "0", []])
def test_failed_filters_rejects_noninteger_indices(index: object) -> None:
    result = audit_matrix([(False,)], 1)
    with pytest.raises(TypeError):
        result.failed_filters(index)  # type: ignore[arg-type]


@pytest.mark.parametrize("index", [-1, 1, 10])
def test_failed_filters_rejects_out_of_range_indices(index: int) -> None:
    with pytest.raises(IndexError):
        audit_matrix([(False,)], 1).failed_filters(index)


@pytest.mark.parametrize("index", [True, False, None, 1.0, "1", []])
def test_relaxation_queries_reject_noninteger_filter_indices(index: object) -> None:
    result = audit_matrix([(False,)], 1)
    with pytest.raises(TypeError):
        result.relax(index)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        result.matching_indices(without=[index])  # type: ignore[list-item]


@pytest.mark.parametrize("index", [-1, 0, 2, 100])
def test_relaxation_queries_reject_out_of_range_filter_indices(index: int) -> None:
    result = audit_matrix([(False,)], 1)
    with pytest.raises(IndexError):
        result.relax(index)
    with pytest.raises(IndexError):
        result.matching_indices(without=[index])


@pytest.mark.parametrize("limit", [True, False, None, 1.0, "1", []])
def test_suggestion_limit_must_be_integer(limit: object) -> None:
    with pytest.raises(TypeError):
        audit_matrix([(False,)], 1).suggest_relaxations(limit=limit)  # type: ignore[arg-type]


@pytest.mark.parametrize("limit", [0, -1, -100])
def test_suggestion_limit_must_be_positive(limit: int) -> None:
    with pytest.raises(ValueError):
        audit_matrix([(False,)], 1).suggest_relaxations(limit=limit)


def test_invalid_query_arguments_are_rejected_even_for_empty_audits() -> None:
    result = Pipeline[int]().audit([])
    with pytest.raises(IndexError):
        result.failed_filters(0)
    with pytest.raises(IndexError):
        result.relax(1)
    with pytest.raises(IndexError):
        result.matching_indices(without=[1])
    with pytest.raises(ValueError):
        result.suggest_relaxations(limit=0)


def test_more_than_sixty_four_filters_use_unbounded_failure_masks() -> None:
    pipeline = Pipeline[int]()
    for index in range(1, 81):
        pipeline.keep(f"rule {index}", lambda row, index=index: row != index)
    result = pipeline.audit([1, 65, 80])
    assert result.is_empty
    assert [tuple(s.index for s in result.failed_filters(i)) for i in range(3)] == [
        (1,),
        (65,),
        (80,),
    ]
    assert result.matching_indices(without=[65]) == (1,)
    assert result.relax(80).remaining == 1
    assert [s.filter_indices for s in result.suggest_relaxations()] == [(1,), (65,), (80,)]


def test_hundred_thousand_records_have_exact_independent_statistics() -> None:
    calls = [0, 0]

    def even(n: int) -> bool:
        calls[0] += 1
        return n % 2 == 0

    def small(n: int) -> bool:
        calls[1] += 1
        return n < 1000

    result = Pipeline[int]().keep("even", even).keep("small", small).audit(range(100_000))
    assert result.items == tuple(range(0, 1000, 2))
    assert result.count == 500
    assert [(s.tested, s.passed, s.failed, s.exclusive_failures) for s in result.filters] == [
        (100_000, 50_000, 50_000, 500),
        (100_000, 1000, 99_000, 49_500),
    ]
    assert result.relax(1).remaining == 1000
    assert result.relax(2).remaining == 50_000
    assert len(result.matching_indices(without=[1, 2])) == 100_000
    assert calls == [100_000, 100_000]


def test_serialization_is_data_free_and_json_compatible() -> None:
    class Private:
        def __repr__(self) -> str:
            raise AssertionError("record repr accessed")

        def __str__(self) -> str:
            raise AssertionError("record str accessed")

    result = Pipeline[Private]().keep("private rule", lambda _: False).audit([Private()])
    summary = result.to_dict()
    assert set(summary) == {
        "initial_count",
        "count",
        "is_empty",
        "elapsed_seconds",
        "filters",
        "suggestions",
    }
    assert summary["initial_count"] == 1
    assert summary["count"] == 0
    assert summary["is_empty"] is True
    assert summary["filters"] == [s.to_dict() for s in result.filters]
    assert summary["suggestions"] == [s.to_dict() for s in result.suggest_relaxations()]
    assert json.loads(json.dumps(summary, allow_nan=False)) == summary
    assert result.filters[0].to_dict() == {
        "index": 1,
        "name": "private rule",
        "tested": 1,
        "passed": 0,
        "failed": 1,
        "exclusive_failures": 1,
        "retention_pct": 0.0,
    }
    assert result.relax(1).to_dict() == {
        "filter_indices": [1],
        "filter_names": ["private rule"],
        "remaining": 1,
        "rescued": 1,
    }
    assert "private rule" in result.explain()


def test_model_metadata_is_read_only_and_summary_is_detached() -> None:
    result = audit_matrix([(False,)], 1)
    statistic = result.filters[0]
    relaxation = result.relax(1)
    assert isinstance(statistic, FilterStats)
    assert isinstance(relaxation, Relaxation)
    with pytest.raises(FrozenInstanceError):
        statistic.failed = 99  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        relaxation.remaining = 99  # type: ignore[misc]
    items = result.items
    filters = result.filters
    assert isinstance(items, tuple)
    assert isinstance(filters, tuple)
    assert result.items is items
    assert result.filters is filters
    for attribute, value in (("items", ()), ("filters", ()), ("count", 99)):
        with pytest.raises(AttributeError):
            setattr(result, attribute, value)
    summary = result.to_dict()
    summary["filters"].clear()  # type: ignore[union-attr]
    summary["suggestions"].clear()  # type: ignore[union-attr]
    assert len(result.filters) == 1
    assert len(result.suggest_relaxations()) == 1


def test_explanation_is_repeatable_side_effect_free_and_not_sequential(
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = audit_matrix([(False, True), (True, False)], 2)
    text = result.explain()
    assert result.explain() == text
    assert capsys.readouterr().out == ""
    assert "audit" in text.lower()
    assert "rule 1" in text and "rule 2" in text
    assert "Final elimination:" not in text
    assert "All records were eliminated." not in text


def test_audit_does_not_retain_rejected_records_or_predicates() -> None:
    class Record:
        pass

    class Predicate:
        def __call__(self, _: Record) -> bool:
            return False

    record = Record()
    predicate = Predicate()
    record_reference = weakref.ref(record)
    predicate_reference = weakref.ref(predicate)
    pipeline = Pipeline[Record]().keep("reject", predicate)
    result = pipeline.audit([record])
    del pipeline, predicate, record
    gc.collect()
    assert record_reference() is None
    assert predicate_reference() is None
    assert result.is_empty
    assert result.relax(1).remaining == 1
