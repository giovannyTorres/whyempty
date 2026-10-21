"""Empty pipelines, one-shot inputs, and explicit failure behavior."""

import copy
import gc
import json
import pickle
import weakref
from collections.abc import Callable, Iterator

import pytest

from whyempty import FilterError, trace


def test_initially_empty_input_has_no_eliminating_filter() -> None:
    calls: list[object] = []
    result = (
        trace([]).keep("first", lambda x: calls.append(x)).keep("later", lambda x: calls.append(x))
    )
    assert result.initial_count == result.count == 0
    assert result.is_empty
    assert result.items == ()
    assert result.first_empty_step is None
    assert result.rejected() == ()
    assert calls == []
    assert all(s.before == s.removed == s.remaining == 0 for s in result.steps)
    assert all(s.retention_pct is None and s.skipped and not s.emptied for s in result.steps)
    assert result.to_dict()["first_empty_step"] is None
    text = result.explain().lower()
    assert "initial" in text and "empty" in text
    assert "final elimination:" not in text


def test_first_elimination_is_not_attributed_to_later_empty_stages() -> None:
    calls: list[int] = []
    result = trace([1, 2]).keep("actual cause", lambda _: False)
    result.keep("later", lambda x: calls.append(x)).keep("last", lambda x: calls.append(x))
    assert calls == []
    assert result.first_empty_step is result.steps[0]
    assert result.steps[0].emptied
    assert all(s.skipped and not s.emptied for s in result.steps[1:])
    final_line = next(
        line for line in result.explain().splitlines() if "Final elimination:" in line
    )
    assert "actual cause" in final_line
    assert "later" not in final_line and "last" not in final_line


@pytest.mark.parametrize("value", [True, 1, -1, "yes", [0], {"x": 0}, (False,)])
def test_truthy_predicate_values_are_kept(value: object) -> None:
    result = trace(["record"]).keep("truth", lambda _: value)
    assert result.items == ("record",)


@pytest.mark.parametrize("value", [False, None, 0, 0.0, "", [], {}, ()])
def test_falsy_predicate_values_are_rejected(value: object) -> None:
    assert trace(["record"]).keep("truth", lambda _: value).is_empty


def test_missing_dictionary_key_has_context_and_original_cause() -> None:
    result = trace([{"key": True}, {}])
    with pytest.raises(FilterError) as caught:
        result.keep("required key", lambda row: row["key"])
    error = caught.value
    assert isinstance(error, RuntimeError)
    assert isinstance(error.__cause__, KeyError)
    assert error.__cause__.args == ("key",)
    assert error.filter_name == "required key"
    assert error.step_index == 1
    assert error.original_index == 1
    assert "required key" in str(error)
    assert "1" in str(error)
    assert result.count == 2
    assert result.steps == ()
    assert result.rejected() == ()


@pytest.mark.parametrize(
    "restore", [copy.copy, copy.deepcopy, lambda error: pickle.loads(pickle.dumps(error))]
)
def test_filter_error_reconstruction_preserves_diagnostic_context(
    restore: Callable[[FilterError], FilterError],
) -> None:
    result = trace([{"key": True}, {}])
    with pytest.raises(FilterError) as caught:
        result.keep("required key", lambda row: row["key"])
    error = caught.value
    restored = restore(error)
    assert restored is not error
    assert type(restored) is FilterError
    assert restored.args == error.args
    assert restored.filter_name == "required key"
    assert restored.step_index == 1
    assert restored.original_index == 1


def test_failed_stage_is_atomic_and_trace_can_be_reused() -> None:
    result = trace(range(6)).keep("even", lambda n: n % 2 == 0)
    items, steps, rejected, summary = (
        result.items,
        result.steps,
        result.rejected(),
        result.to_dict(),
    )
    calls: list[int] = []
    cause = ValueError("predicate failed")

    def fail(n: int) -> bool:
        calls.append(n)
        if n == 4:
            raise cause
        return False

    with pytest.raises(FilterError) as caught:
        result.keep("broken", fail)
    assert caught.value.__cause__ is cause
    assert caught.value.step_index == 2
    assert caught.value.original_index == 4
    assert calls == [0, 2, 4]
    assert result.items == items
    assert result.steps == steps
    assert result.rejected() == rejected
    assert result.to_dict() == summary
    result.keep("retry", lambda n: n > 0)
    assert result.items == (2, 4)
    assert result.steps[-1].index == 2


def test_failure_does_not_evaluate_later_occurrences() -> None:
    calls: list[int] = []

    def fail_first(n: int) -> bool:
        calls.append(n)
        raise ArithmeticError("broken")

    with pytest.raises(FilterError):
        trace([1, 2, 3]).keep("broken", fail_first)
    assert calls == [1]


def test_exception_during_truth_conversion_is_contextualized() -> None:
    cause = ValueError("cannot coerce")

    class BadTruth:
        def __bool__(self) -> bool:
            raise cause

    result = trace(["private"])
    with pytest.raises(FilterError) as caught:
        result.keep("bad truth", lambda _: BadTruth())
    assert caught.value.__cause__ is cause
    assert caught.value.original_index == 0
    assert result.items == ("private",)
    assert result.steps == ()


def test_truth_conversion_runs_once_per_occurrence() -> None:
    calls: list[int] = []

    class Truth:
        def __init__(self, value: int) -> None:
            self.value = value

        def __bool__(self) -> bool:
            calls.append(self.value)
            return self.value % 2 == 0

    result = trace([1, 2, 3]).keep("truth", Truth)
    result.explain()
    result.to_dict()
    result.rejected()
    assert result.items == (2,)
    assert calls == [1, 2, 3]


@pytest.mark.parametrize("exception", [KeyboardInterrupt(), SystemExit(2), GeneratorExit()])
def test_control_flow_base_exceptions_are_not_wrapped(exception: BaseException) -> None:
    result = trace([1])

    def interrupt(_: int) -> bool:
        raise exception

    with pytest.raises(type(exception)) as caught:
        result.keep("interrupt", interrupt)
    assert caught.value is exception
    assert result.items == (1,)
    assert result.steps == ()
    result.keep("after interrupt", lambda _: True)
    assert len(result.steps) == 1


def test_generator_is_consumed_exactly_once() -> None:
    yielded: list[int] = []

    def source() -> Iterator[int]:
        for value in range(4):
            yielded.append(value)
            yield value

    generator = source()
    result = trace(generator)
    assert yielded == [0, 1, 2, 3]
    assert next(generator, None) is None
    result.keep("large", lambda n: n > 1)
    result.explain()
    result.to_dict()
    result.rejected()
    assert yielded == [0, 1, 2, 3]
    assert result.items == (2, 3)


def test_one_pass_iterator_does_not_require_len_or_sequence_protocol() -> None:
    class OnePass:
        def __init__(self) -> None:
            self.values = iter([3, 1, 2])
            self.iterations = 0

        def __iter__(self) -> "OnePass":
            self.iterations += 1
            if self.iterations > 1:
                raise AssertionError("input iterated twice")
            return self

        def __next__(self) -> int:
            return next(self.values)

    source = OnePass()
    result = trace(source).keep("large", lambda n: n >= 2)
    assert result.items == (3, 2)
    assert source.iterations == 1


def test_repeated_equal_and_identical_unhashable_elements_keep_occurrence_identity() -> None:
    shared = [1]
    values = [shared, [1], shared, [2]]
    decisions = iter([True, False, False, True])
    result = trace(values).keep("by occurrence", lambda _: next(decisions))
    assert result.items == ([1], [2])
    assert result.items[0] is shared
    assert [r.original_index for r in result.rejected()] == [1, 2]
    assert values == [[1], [1], [1], [2]]


def test_user_collection_is_not_mutated_and_later_membership_changes_are_isolated() -> None:
    values = [{"value": 1}, {"value": 2}]
    first, second = values
    result = trace(values)
    values.append({"value": 3})
    result.keep("large", lambda item: item["value"] > 1)
    assert values == [{"value": 1}, {"value": 2}, {"value": 3}]
    assert result.items == (second,)
    assert result.initial_count == 2
    first["value"] = 99
    second["value"] = 20
    assert result.items[0]["value"] == 20


def test_diagnostics_never_call_repr_or_str_on_records() -> None:
    class Private:
        def __repr__(self) -> str:
            raise AssertionError("repr leaked")

        def __str__(self) -> str:
            raise AssertionError("str leaked")

    result = trace([Private(), Private()]).keep("reject", lambda _: False)
    assert "reject" in result.explain()
    json.dumps(result.to_dict(), allow_nan=False)
    json.dumps([r.to_dict() for r in result.rejected()], allow_nan=False)


def test_error_message_does_not_render_record() -> None:
    class Private:
        def __repr__(self) -> str:
            raise AssertionError("repr leaked")

    def fail(_: Private) -> bool:
        raise ValueError("failed")

    with pytest.raises(FilterError) as caught:
        trace([Private()]).keep("broken", fail)
    assert "broken" in str(caught.value)
    assert isinstance(caught.value.__cause__, ValueError)


def test_rejected_records_are_not_retained_for_provenance() -> None:
    class Record:
        pass

    record = Record()
    reference = weakref.ref(record)
    result = trace([record])
    del record
    result.keep("reject", lambda _: False)
    gc.collect()
    assert reference() is None
    assert result.rejected()[0].original_index == 0


def test_side_effect_predicates_are_not_reexecuted_by_any_diagnostic() -> None:
    calls: list[tuple[str, int]] = []

    def first(n: int) -> bool:
        calls.append(("first", n))
        return n > 0

    def second(n: int) -> bool:
        calls.append(("second", n))
        return n < 2

    result = trace(range(3)).keep("first", first).keep("second", second)
    expected = [("first", 0), ("first", 1), ("first", 2), ("second", 1), ("second", 2)]
    assert calls == expected
    for _ in range(3):
        result.explain()
        result.to_dict()
        result.rejected()
        assert result.count == 1
        assert result.items == (1,)
        assert len(result.steps) == 2
    assert calls == expected


@pytest.mark.parametrize("name", [None, 1, b"name", ["name"]])
def test_filter_name_must_be_string_even_on_empty_input(name: object) -> None:
    with pytest.raises(TypeError):
        trace([]).keep(name, lambda _: True)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "name", ["", "   ", "\t", "two\nlines", "escape\x1b", "nul\x00", "delete\x7f"]
)
def test_filter_name_must_be_nonempty_and_printable(name: str) -> None:
    with pytest.raises(ValueError):
        trace([]).keep(name, lambda _: True)


@pytest.mark.parametrize("predicate", [None, 0, True, "callable", []])
def test_predicate_must_be_callable_even_on_empty_input(predicate: object) -> None:
    with pytest.raises(TypeError):
        trace([]).keep("name", predicate)  # type: ignore[arg-type]


def test_reentrant_keep_is_rejected_and_outer_stage_rolls_back() -> None:
    result = trace([1, 2])

    def reenter(_: int) -> bool:
        result.keep("inner", lambda _: True)
        return True

    with pytest.raises(FilterError) as caught:
        result.keep("outer", reenter)
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert result.items == (1, 2)
    assert result.steps == ()
    result.keep("recovered", lambda n: n == 2)
    assert result.items == (2,)
