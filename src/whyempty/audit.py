"""Independent filter evaluation and projections from recorded failure masks."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from heapq import nsmallest
from time import perf_counter
from typing import Generic, TypeVar

from .core import FilterError
from .formatting import format_audit_explanation
from .models import FilterStats, Relaxation

T = TypeVar("T")


def _indices_for_mask(mask: int) -> tuple[int, ...]:
    indices = []
    while mask:
        lowest_bit = mask & -mask
        indices.append(lowest_bit.bit_length())
        mask ^= lowest_bit
    return tuple(indices)


class AuditResult(Generic[T]):
    """Recorded independent outcomes from :meth:`Pipeline.audit`.

    Every filter was evaluated on every input occurrence, including occurrences
    that failed earlier filters. Queries use stored outcomes and never call
    predicates. Only surviving record references are retained; other occurrences
    are represented by positional failure masks.

    Relaxations project these recorded outcomes. Reproducing their counts in
    another execution requires stable predicates without relevant side effects.
    """

    __slots__ = ("_items", "_masks", "_frequencies", "_filters", "_elapsed_seconds")

    def __init__(
        self,
        items: tuple[T, ...],
        masks: tuple[int, ...],
        frequencies: Counter[int],
        filters: tuple[FilterStats, ...],
        elapsed_seconds: float,
    ) -> None:
        """Initialize internally prepared metadata; prefer ``Pipeline.audit()``."""
        self._items = items
        self._masks = masks
        self._frequencies = frequencies
        self._filters = filters
        self._elapsed_seconds = elapsed_seconds

    @property
    def items(self) -> tuple[T, ...]:
        """Surviving references in original order, without copying on access."""
        return self._items

    @property
    def initial_count(self) -> int:
        """Number of occurrences consumed from the input iterable."""
        return len(self._masks)

    @property
    def count(self) -> int:
        """Number of occurrences that passed every filter."""
        return len(self._items)

    @property
    def is_empty(self) -> bool:
        """Whether no occurrence passed every filter."""
        return not self._items

    @property
    def filters(self) -> tuple[FilterStats, ...]:
        """Immutable independent filter statistics in definition order."""
        return self._filters

    @property
    def elapsed_seconds(self) -> float:
        """Elapsed audit time, including input iteration and outcome recording."""
        return self._elapsed_seconds

    def failed_filters(self, original_index: int) -> tuple[FilterStats, ...]:
        """Return all filters failed by one zero-based input occurrence.

        Booleans and nonintegers raise TypeError; negative or out-of-range
        positions raise IndexError. Surviving occurrences return an empty tuple.
        """
        if isinstance(original_index, bool) or not isinstance(original_index, int):
            raise TypeError("Original index must be an integer, not a boolean.")
        if original_index < 0 or original_index >= self.initial_count:
            raise IndexError("Original index is out of range.")
        return tuple(
            self._filters[index - 1] for index in _indices_for_mask(self._masks[original_index])
        )

    def _disabled_mask(self, filter_indices: Iterable[int]) -> int:
        disabled = 0
        for index in filter_indices:
            if isinstance(index, bool) or not isinstance(index, int):
                raise TypeError("Filter indices must be integers, not booleans.")
            if index < 1 or index > len(self._filters):
                raise IndexError("Filter index is out of range.")
            disabled |= 1 << (index - 1)
        return disabled

    def _relaxation(self, disabled: int, remaining: int) -> Relaxation:
        indices = _indices_for_mask(disabled)
        return Relaxation(
            filter_indices=indices,
            filter_names=tuple(self._filters[index - 1].name for index in indices),
            remaining=remaining,
            rescued=remaining - self.count,
        )

    def relax(self, *filter_indices: int) -> Relaxation:
        """Project counts after disabling the supplied one-based filter indices.

        Duplicate indices are deduplicated and returned in ascending order. No
        predicates are reevaluated and this result is unchanged. Invalid index
        types raise TypeError; indices outside the filter range raise IndexError.
        """
        disabled = self._disabled_mask(filter_indices)
        remaining = sum(
            frequency for mask, frequency in self._frequencies.items() if mask & ~disabled == 0
        )
        return self._relaxation(disabled, remaining)

    def matching_indices(self, *, without: Iterable[int] = ()) -> tuple[int, ...]:
        """Return original positions matching after disabling ``without`` filters.

        Filter indices are one-based and validated as in :meth:`relax`. With no
        disabled filters, return the positions of the current survivors. Input
        order is preserved, and predicates and record values are never accessed.
        """
        disabled = self._disabled_mask(without)
        return tuple(index for index, mask in enumerate(self._masks) if mask & ~disabled == 0)

    def suggest_relaxations(self, *, limit: int = 5) -> tuple[Relaxation, ...]:
        """Suggest the fewest disabled filters that restore a recorded match.

        For an empty result with nonempty input, return up to ``limit`` distinct
        minimum-cardinality failure sets, ranked by rescued count descending,
        then filter indices lexicographically. Empty input or an existing match
        needs no suggested relaxation and returns an empty tuple.

        ``limit`` must be a positive integer; booleans and nonintegers raise
        TypeError, and nonpositive integers raise ValueError. Suggestions use
        observed failure patterns without enumerating all filter subsets.
        """
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("Limit must be an integer, not a boolean.")
        if limit <= 0:
            raise ValueError("Limit must be positive.")
        if self.initial_count == 0 or self.count > 0:
            return ()

        fewest = min(mask.bit_count() for mask in self._frequencies)
        candidates = (mask for mask in self._frequencies if mask.bit_count() == fewest)
        selected = nsmallest(
            limit,
            candidates,
            key=lambda mask: (-self._frequencies[mask], _indices_for_mask(mask)),
        )
        # A proper failed subset would have lower cardinality, so each minimum
        # pattern restores exactly its own frequency when the base result is empty.
        return tuple(self._relaxation(mask, self._frequencies[mask]) for mask in selected)

    def to_dict(self) -> dict[str, object]:
        """Return JSON-compatible counts, filter statistics, and top suggestions.

        Original records, their representations, predicates, and per-occurrence
        outcomes are excluded. Suggestions use the default limit of five.
        """
        return {
            "initial_count": self.initial_count,
            "count": self.count,
            "is_empty": self.is_empty,
            "elapsed_seconds": self.elapsed_seconds,
            "filters": [entry.to_dict() for entry in self._filters],
            "suggestions": [entry.to_dict() for entry in self.suggest_relaxations()],
        }

    def explain(self) -> str:
        """Return an independent diagnostic and recorded-outcome suggestions."""
        return format_audit_explanation(
            self.initial_count,
            self.count,
            self.filters,
            self.elapsed_seconds,
            self.suggest_relaxations(),
        )


def _evaluate_audit(
    records: Iterable[T], rules: tuple[tuple[str, Callable[[T], object]], ...]
) -> AuditResult[T]:
    started = perf_counter()
    survivors: list[T] = []
    masks: list[int] = []
    frequencies: Counter[int] = Counter()
    failures = [0] * len(rules)
    for original_index, item in enumerate(records):
        mask = 0
        for rule_index, (name, predicate) in enumerate(rules):
            try:
                passed = bool(predicate(item))
            except Exception as exc:
                raise FilterError(name, rule_index + 1, original_index) from exc
            if not passed:
                mask |= 1 << rule_index
                failures[rule_index] += 1
        masks.append(mask)
        frequencies[mask] += 1
        if mask == 0:
            survivors.append(item)

    initial_count = len(masks)
    filters = tuple(
        FilterStats(
            index=index + 1,
            name=name,
            tested=initial_count,
            passed=initial_count - failures[index],
            failed=failures[index],
            exclusive_failures=frequencies[1 << index],
        )
        for index, (name, _) in enumerate(rules)
    )
    items = tuple(survivors)
    recorded_masks = tuple(masks)
    elapsed = perf_counter() - started
    return AuditResult(items, recorded_masks, frequencies, filters, elapsed)
