"""Reusable pipelines preserve Trace behavior and snapshot their rule set."""

import gc
import weakref
from collections.abc import Iterator

import pytest

from whyempty import Pipeline, Trace


def test_pipeline_is_fluent_with_detached_filter_name_snapshots() -> None:
    pipeline = Pipeline[int]()
    assert pipeline.filter_names == ()
    assert pipeline.keep("even", lambda n: n % 2 == 0) is pipeline
    names = pipeline.filter_names
    pipeline.keep("positive", lambda n: n > 0)
    assert names == ("even",)
    assert pipeline.filter_names == ("even", "positive")


def test_run_produces_independent_sequential_traces() -> None:
    pipeline = Pipeline[int]().keep("even", lambda n: n % 2 == 0)
    pipeline.keep("positive", lambda n: n > 0)
    first = pipeline.run([0, 1, 2, 3])
    second = pipeline.run([2, 4, 5])
    assert isinstance(first, Trace)
    assert first.items == (2,)
    assert second.items == (2, 4)
    assert first.initial_count == 4
    assert second.initial_count == 3
    assert [(s.before, s.remaining) for s in first.steps] == [(4, 2), (2, 1)]
    first.keep("none", lambda _: False)
    assert second.items == (2, 4)
    assert pipeline.filter_names == ("even", "positive")


def test_run_snapshots_rules_before_consuming_input() -> None:
    pipeline = Pipeline[int]().keep("all", lambda _: True)

    def source() -> Iterator[int]:
        pipeline.keep("added while consuming", lambda _: False)
        yield 1
        yield 2

    result = pipeline.run(source())
    assert result.items == (1, 2)
    assert tuple(s.name for s in result.steps) == ("all",)
    assert pipeline.run([1, 2]).is_empty


def test_run_snapshots_rules_before_predicate_mutates_pipeline() -> None:
    pipeline = Pipeline[int]()
    added = False

    def mutate(_: int) -> bool:
        nonlocal added
        if not added:
            pipeline.keep("future only", lambda _: False)
            added = True
        return True

    pipeline.keep("mutator", mutate)
    first = pipeline.run([1, 2])
    assert first.items == (1, 2)
    assert len(first.steps) == 1
    assert pipeline.run([1, 2]).is_empty


def test_run_short_circuits_while_audit_tests_every_rule() -> None:
    calls: list[tuple[str, int]] = []

    def none(n: int) -> bool:
        calls.append(("none", n))
        return False

    def all_records(n: int) -> bool:
        calls.append(("all", n))
        return True

    pipeline = Pipeline[int]().keep("none", none).keep("all", all_records)
    assert pipeline.run([1, 2]).is_empty
    assert calls == [("none", 1), ("none", 2)]
    calls.clear()
    assert pipeline.audit([1, 2]).is_empty
    assert sorted(calls) == [("all", 1), ("all", 2), ("none", 1), ("none", 2)]


def test_run_without_rules_and_run_on_empty_input() -> None:
    pipeline = Pipeline[int]()
    result = pipeline.run(iter([3, 1, 2]))
    assert result.items == (3, 1, 2)
    assert result.steps == ()
    pipeline.keep("unused", lambda _: pytest.fail("must not execute on empty input"))
    empty = pipeline.run([])
    assert empty.initial_count == empty.count == 0
    assert empty.steps[0].skipped


@pytest.mark.parametrize("name", [None, 1, True, b"name", ["name"]])
def test_pipeline_rejects_nonstring_filter_names(name: object) -> None:
    with pytest.raises(TypeError):
        Pipeline().keep(name, lambda _: True)  # type: ignore[arg-type]


@pytest.mark.parametrize("name", ["", "   ", "\t", "two\nlines", "escape\x1b", "nul\x00"])
def test_pipeline_rejects_blank_or_unprintable_filter_names(name: str) -> None:
    with pytest.raises(ValueError):
        Pipeline().keep(name, lambda _: True)


@pytest.mark.parametrize("predicate", [None, 0, True, "callable", []])
def test_pipeline_validates_predicate_before_any_run(predicate: object) -> None:
    with pytest.raises(TypeError):
        Pipeline().keep("name", predicate)  # type: ignore[arg-type]


def test_run_result_does_not_retain_predicates() -> None:
    class Predicate:
        def __call__(self, _: int) -> bool:
            return True

    predicate = Predicate()
    reference = weakref.ref(predicate)
    pipeline = Pipeline[int]().keep("all", predicate)
    result = pipeline.run([1])
    del pipeline, predicate
    gc.collect()
    assert reference() is None
    assert result.items == (1,)
