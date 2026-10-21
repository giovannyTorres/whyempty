"""Immutable diagnostic metadata; these models never contain user records."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Step:
    """Statistics for one completed filter; ``index`` starts at one."""

    index: int
    name: str
    before: int
    removed: int
    remaining: int
    elapsed_seconds: float

    @property
    def retention_pct(self) -> float | None:
        """Return percent retained, or None when the stage received no records."""
        return 100.0 * self.remaining / self.before if self.before else None

    @property
    def emptied(self) -> bool:
        """Whether this stage eliminated a previously nonempty collection."""
        return self.before > 0 and self.remaining == 0

    @property
    def skipped(self) -> bool:
        """Whether no records reached this stage and no predicate was invoked."""
        return self.before == 0

    @property
    def significant_reduction(self) -> bool:
        """Whether at least 50 percent of a nonempty stage input was removed."""
        return self.before > 0 and self.removed * 2 >= self.before

    def to_dict(self) -> dict[str, int | float | str | bool | None]:
        """Return JSON-compatible statistics without original record data."""
        return {
            "index": self.index,
            "name": self.name,
            "before": self.before,
            "removed": self.removed,
            "remaining": self.remaining,
            "retention_pct": self.retention_pct,
            "elapsed_seconds": self.elapsed_seconds,
            "emptied": self.emptied,
            "skipped": self.skipped,
            "significant_reduction": self.significant_reduction,
        }


@dataclass(frozen=True, slots=True)
class Rejection:
    """First rejection of an occurrence, identified by its zero-based input index."""

    original_index: int
    step_index: int
    filter_name: str

    def to_dict(self) -> dict[str, int | str]:
        """Return JSON-compatible positional rejection metadata."""
        return {
            "original_index": self.original_index,
            "step_index": self.step_index,
            "filter_name": self.filter_name,
        }
