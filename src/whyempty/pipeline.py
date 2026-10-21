"""Reusable filter definitions with sequential tracing and independent auditing."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Generic, TypeVar

from .audit import AuditResult, _evaluate_audit
from .core import Trace, _validate_filter, trace

T = TypeVar("T")


class Pipeline(Generic[T]):
    """Reusable ordered filter definitions, independent of any input collection.

    ``keep`` mutates and returns this pipeline. Each execution snapshots its
    rules before consuming input, so later configuration changes affect future
    executions only. Predicates and their state are shared, never deep-copied.
    A pipeline is not thread safe.
    """

    def __init__(self) -> None:
        self._rules: list[tuple[str, Callable[[T], object]]] = []

    @property
    def filter_names(self) -> tuple[str, ...]:
        """Return a snapshot of names in definition order; duplicates are allowed."""
        return tuple(name for name, _ in self._rules)

    def keep(self, name: str, predicate: Callable[[T], object]) -> Pipeline[T]:
        """Register a filter without evaluating it, returning this same pipeline.

        Names must be nonblank, printable strings, and predicates callable.
        Matching uses Python truth conversion, as with :meth:`Trace.keep`.
        """
        _validate_filter(name, predicate)
        self._rules.append((name, predicate))
        return self

    def run(self, records: Iterable[T]) -> Trace[T]:
        """Apply a rule snapshot sequentially, returning the usual filter trace.

        Only survivors reach later filters. Input is consumed once. Predicate
        failures raise :class:`FilterError` with their original cause; the
        pipeline remains available for future executions.
        """
        rules = tuple(self._rules)
        result = trace(records)
        for name, predicate in rules:
            result.keep(name, predicate)
        return result

    def audit(self, records: Iterable[T]) -> AuditResult[T]:
        """Evaluate every rule once per occurrence and analyze recorded outcomes.

        Input is consumed once, in original order; for each occurrence all rules
        execute in definition order. Unlike ``run``, failed guards do not skip
        later rules. Use predicates defined on every record, preferably pure and
        stable. An exception aborts the audit with :class:`FilterError`, retaining
        its original cause; no partial result is returned. The result retains no
        predicates or rejected-record references.
        """
        rules = tuple(self._rules)
        return _evaluate_audit(records, rules)
