"""Public API behavior, provenance, and data-free diagnostics."""

import json
from dataclasses import FrozenInstanceError

import pytest

from whyempty import Rejection, Step, Trace, __version__, trace


@pytest.fixture
def records() -> list[dict[str, object]]:
    return [
        {"id": 1, "active": True, "country": "MX", "score": 40},
        {"id": 2, "active": False, "country": "MX", "score": 90},
        {"id": 3, "active": True, "country": "US", "score": 95},
    ]


def test_version_and_public_constructor() -> None:
    assert __version__ == "0.1.0"
    assert isinstance(trace([1]), Trace)
    assert Trace([1, 2]).items == (1, 2)


def test_requested_pipeline(records: list[dict[str, object]]) -> None:
    result = (
        trace(records)
        .keep("Active", lambda row: row["active"])
        .keep("Mexico", lambda row: row["country"] == "MX")
        .keep("Score >= 80", lambda row: int(str(row["score"])) >= 80)
    )

    assert result.items == ()
    assert result.initial_count == 3
    assert result.count == 0
    assert result.is_empty
    assert [(s.name, s.before, s.removed, s.remaining) for s in result.steps] == [
        ("Active", 3, 1, 2),
        ("Mexico", 2, 1, 1),
        ("Score >= 80", 1, 1, 0),
    ]
    assert [s.index for s in result.steps] == [1, 2, 3]
    assert [s.retention_pct for s in result.steps] == pytest.approx([200 / 3, 50, 0])
    assert all(s.elapsed_seconds >= 0 for s in result.steps)
    assert result.first_empty_step is result.steps[2]
    assert [s.emptied for s in result.steps] == [False, False, True]
    assert all(not s.skipped for s in result.steps)


def test_keep_mutates_same_trace_and_returns_self() -> None:
    result = trace(range(5))
    returned = result.keep("even", lambda n: n % 2 == 0)
    assert returned is result
    assert result.items == (0, 2, 4)
    assert result.count == 3
    assert not result.is_empty
    assert result.first_empty_step is None


def test_no_filters_preserves_order_and_has_empty_history() -> None:
    result = trace([3, 1, 2])
    assert result.items == (3, 1, 2)
    assert result.steps == ()
    assert result.rejected() == ()
    assert result.initial_count == result.count == 3
    assert result.first_empty_step is None
    assert "No filters" in result.explain()


def test_all_filters_keep_every_occurrence() -> None:
    result = trace([3, 1, 3]).keep("one", lambda _: True).keep("two", lambda _: 1)
    assert result.items == (3, 1, 3)
    assert result.rejected() == ()
    assert all(s.removed == 0 and s.retention_pct == 100 for s in result.steps)
    assert result.first_empty_step is None


def test_rejections_are_in_original_order_not_stage_order() -> None:
    result = trace([10, 11, 12, 13, 14])
    result.keep("even", lambda n: n % 2 == 0).keep("large", lambda n: n >= 12)
    assert result.items == (12, 14)
    assert result.rejected() == (
        Rejection(original_index=0, step_index=2, filter_name="large"),
        Rejection(original_index=1, step_index=1, filter_name="even"),
        Rejection(original_index=3, step_index=1, filter_name="even"),
    )
    assert result.count + len(result.rejected()) == result.initial_count


def test_duplicate_names_have_unambiguous_step_indices() -> None:
    result = trace(range(4)).keep("same", lambda n: n % 2 == 0)
    result.keep("same", lambda n: n > 0).keep("same", lambda _: False)
    assert [s.name for s in result.steps] == ["same"] * 3
    assert [(r.original_index, r.step_index) for r in result.rejected()] == [
        (0, 2),
        (1, 1),
        (2, 3),
        (3, 1),
    ]
    assert result.first_empty_step is result.steps[2]


def test_public_snapshots_do_not_change_after_keep() -> None:
    result = trace([1, 2, 3])
    items = result.items
    steps = result.steps
    rejected = result.rejected()
    assert result.items is items
    result.keep("large", lambda n: n > 1)
    assert items == (1, 2, 3)
    assert steps == ()
    assert rejected == ()
    assert result.items == (2, 3)


def test_models_are_immutable() -> None:
    result = trace([1]).keep("none", lambda _: False)
    step = result.steps[0]
    rejection = result.rejected()[0]
    assert isinstance(step, Step)
    with pytest.raises(FrozenInstanceError):
        step.remaining = 99
    with pytest.raises(FrozenInstanceError):
        rejection.original_index = 99


@pytest.mark.parametrize(
    ("count", "remaining", "significant"),
    [(0, 0, False), (4, 4, False), (4, 3, False), (4, 2, True), (3, 1, True), (4, 0, True)],
)
def test_significant_reduction_has_explicit_half_threshold(
    count: int, remaining: int, significant: bool
) -> None:
    step = trace(range(count)).keep("threshold", lambda n: n < remaining).steps[0]
    assert step.significant_reduction is significant
    assert step.before == step.removed + step.remaining


def test_summary_schema_is_json_serializable() -> None:
    result = trace([1, 2]).keep("odd", lambda n: n % 2).keep("none", lambda _: False)
    summary = result.to_dict()
    assert set(summary) == {"initial_count", "count", "is_empty", "first_empty_step", "steps"}
    assert summary["initial_count"] == 2
    assert summary["count"] == 0
    assert summary["is_empty"] is True
    assert summary["first_empty_step"] == 2
    assert summary["steps"] == [s.to_dict() for s in result.steps]
    assert json.loads(json.dumps(summary, allow_nan=False)) == summary


def test_serialized_models_contain_only_metadata() -> None:
    result = trace([{"secret": "NEVER_SERIALIZE_THIS"}]).keep("reject", lambda _: False)
    rejection = result.rejected()[0].to_dict()
    assert rejection == {"original_index": 0, "step_index": 1, "filter_name": "reject"}
    step = result.steps[0].to_dict()
    for key, value in {
        "index": 1,
        "name": "reject",
        "before": 1,
        "removed": 1,
        "remaining": 0,
        "retention_pct": 0.0,
    }.items():
        assert step[key] == value
    assert "elapsed_seconds" in step
    assert "NEVER_SERIALIZE_THIS" not in json.dumps(result.to_dict())
    assert "NEVER_SERIALIZE_THIS" not in result.explain()


def test_summary_is_detached_from_internal_statistics() -> None:
    result = trace([1, 2]).keep("all", lambda _: True)
    summary = result.to_dict()
    summary["steps"].clear()  # type: ignore[union-attr]
    assert len(result.steps) == 1
    assert len(result.to_dict()["steps"]) == 1  # type: ignore[arg-type]


def test_explain_is_repeatable_and_does_not_print(capsys: pytest.CaptureFixture[str]) -> None:
    result = trace([1, 2, 3]).keep("small", lambda n: n < 3).keep("none", lambda _: False)
    first = result.explain()
    assert isinstance(first, str)
    assert result.explain() == first
    assert capsys.readouterr().out == ""
    for expected in (
        "whyempty",
        "Initial records: 3",
        "small",
        "none",
        "EMPTY",
        "Final elimination",
    ):
        assert expected in first


def test_unicode_filter_name_is_preserved() -> None:
    result = trace(["México"]).keep("País 🇲🇽", lambda _: False)
    assert result.steps[0].name == "País 🇲🇽"
    assert "País 🇲🇽" in result.explain()
    assert json.loads(json.dumps(result.to_dict()))["steps"][0]["name"] == "País 🇲🇽"


def test_explanation_identifies_earlier_significant_reductions_and_empty_later_stages() -> None:
    result = (
        trace(range(4))
        .keep("half", lambda n: n < 2)
        .keep("eliminator", lambda _: False)
        .keep("later", lambda _: True)
    )
    text = result.explain()
    significant_line = next(line for line in text.splitlines() if "Significant reductions" in line)
    assert "50%" in significant_line
    assert "1. half" in significant_line
    assert "eliminator" not in significant_line
    assert "later" not in significant_line
    skipped_line = next(line for line in text.splitlines() if "Skipped" in line)
    assert "3. later" in skipped_line
    assert "eliminator" not in skipped_line
    assert "N/A" in text


def test_significant_reduction_is_reported_when_records_remain() -> None:
    result = trace(range(4)).keep("half", lambda n: n < 2)
    assert "Result: 2 records" in result.explain()
    assert "Significant reductions" in result.explain()
    assert "Final elimination:" not in result.explain()
