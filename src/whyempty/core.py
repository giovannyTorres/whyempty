"""Eager, sequential filter tracing with positional rejection provenance."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from time import perf_counter
from typing import Generic, TypeVar

from .formatting import format_explanation
from .models import Rejection, Step

T = TypeVar("T")


def _validate_filter(name: str, predicate: Callable[[T], object]) -> None:
    if not isinstance(name, str):
        raise TypeError("Filter name must be a string.")
    if not name.strip() or not name.isprintable():
        raise ValueError("Filter name must be nonblank and printable.")
    if not callable(predicate):
        raise TypeError("Predicate must be callable.")


class FilterError(RuntimeError):
    """A predicate or its truth conversion failed; ``__cause__`` is preserved.

    Attributes identify the attempted filter and the original input occurrence.
    The message deliberately excludes the record and original exception text.
    """

    def __init__(self, filter_name: str, step_index: int, original_index: int) -> None:
        self.filter_name = filter_name
        self.step_index = step_index
        self.original_index = original_index
        super().__init__(
            f"Predicate failed at step {step_index} ({filter_name!r}), "
            f"original index {original_index}. The stage was not committed."
        )

    def __reduce__(self) -> tuple[type[FilterError], tuple[str, int, int], dict[str, object]]:
        """Preserve diagnostic attributes when copying or pickling the exception."""
        return type(self), (self.filter_name, self.step_index, self.original_index), self.__dict__


class Trace(Generic[T]):
    """A mutable filter pipeline that consumes input once and records each stage.

    Prefer :func:`trace` for construction. Only surviving record references are
    retained. Objects inside ``items`` are shared with the caller, not deep-copied.
    A trace is not thread safe; reentrant filtering on the same trace is rejected.
    """

    def __init__(self, records: Iterable[T]) -> None:
        self._items = tuple(records)
        self._initial_count = len(self._items)
        self._indices: Sequence[int] = range(self._initial_count)
        self._failed_steps = [0] * self._initial_count
        self._steps: list[Step] = []
        self._filtering = False

    @property
    def items(self) -> tuple[T, ...]:
        """Surviving references in original order, as an immutable tuple snapshot."""
        return self._items

    @property
    def initial_count(self) -> int:
        """Number of occurrences consumed from the original iterable."""
        return self._initial_count

    @property
    def count(self) -> int:
        """Number of records currently surviving."""
        return len(self._items)

    @property
    def is_empty(self) -> bool:
        """Whether no records currently survive."""
        return not self._items

    @property
    def steps(self) -> tuple[Step, ...]:
        """Immutable snapshot of completed stages in execution order."""
        return tuple(self._steps)

    @property
    def first_empty_step(self) -> Step | None:
        """First stage that emptied nonempty input, or None if none did."""
        return next((step for step in self._steps if step.emptied), None)

    def keep(self, name: str, predicate: Callable[[T], object]) -> Trace[T]:
        """Keep truthy matches and append statistics, returning this same trace.

        Each surviving occurrence is evaluated once. A predicate or truth
        conversion raising ``Exception`` aborts this stage with :class:`FilterError`
        chained from the cause. Previously recorded state remains intact; user
        side effects cannot be undone. ``BaseException`` propagates unchanged.

        Names must be nonblank, printable strings. Duplicate names are allowed;
        one-based step indices distinguish them. Empty-input stages are recorded
        without calling the predicate. Timing includes partitioning and provenance
        recording, and excludes formatting and creation of the Step object.
        """
        if self._filtering:
            raise RuntimeError("Cannot call keep() reentrantly on the same trace.")
        _validate_filter(name, predicate)

        self._filtering = True
        try:
            return self._apply(name, predicate)
        finally:
            self._filtering = False

    def _apply(self, name: str, predicate: Callable[[T], object]) -> Trace[T]:
        step_index = len(self._steps) + 1
        before = self.count
        survivors: list[T] = []
        survivor_indices: list[int] = []
        rejected_indices: list[int] = []
        started = perf_counter()
        for original_index, item in zip(self._indices, self._items, strict=True):
            try:
                passed = bool(predicate(item))
            except Exception as exc:
                raise FilterError(name, step_index, original_index) from exc
            if passed:
                survivors.append(item)
                survivor_indices.append(original_index)
            else:
                rejected_indices.append(original_index)

        # Prepare replacements before committing; exceptions above change no state.
        new_items = tuple(survivors)
        new_indices = tuple(survivor_indices)
        for original_index in rejected_indices:
            self._failed_steps[original_index] = step_index
        self._items = new_items
        self._indices = new_indices
        elapsed = perf_counter() - started
        self._steps.append(
            Step(step_index, name, before, len(rejected_indices), self.count, elapsed)
        )
        return self

    def rejected(self) -> tuple[Rejection, ...]:
        """Return first-rejection metadata in original order, without record data.

        This scans the original positional metadata; it never reruns predicates.
        If the caller needs rejected records, it must retain its own input data.
        """
        return tuple(
            Rejection(original_index, step_index, self._steps[step_index - 1].name)
            for original_index, step_index in enumerate(self._failed_steps)
            if step_index
        )

    def explain(self) -> str:
        """Return a readable diagnosis using only recorded statistics."""
        return format_explanation(self.initial_count, self.count, self.steps)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible summary containing no records or predicates.

        ``first_empty_step`` is a one-based index or None. Per-occurrence rejection
        metadata is available separately through :meth:`rejected`.
        """
        first_empty = self.first_empty_step
        return {
            "initial_count": self.initial_count,
            "count": self.count,
            "is_empty": self.is_empty,
            "first_empty_step": first_empty.index if first_empty else None,
            "steps": [step.to_dict() for step in self._steps],
        }


def trace(records: Iterable[T]) -> Trace[T]:
    """Consume an iterable once and return a mutable, chainable filter trace."""
    return Trace(records)
