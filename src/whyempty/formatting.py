"""Pure formatting of already recorded filter statistics."""

from __future__ import annotations

from collections.abc import Sequence

from .models import Step


def format_explanation(initial_count: int, count: int, steps: Sequence[Step]) -> str:
    """Format a diagnostic without accessing records or evaluating predicates."""
    labels = [f"{step.index}. {step.name}" for step in steps]
    name_width = max([len("Filter"), *(len(label) for label in labels)])
    number_width = max(len("Remaining"), len(str(initial_count)))
    header = (
        f"{'Filter':<{name_width}}  {'Before':>{number_width}}  "
        f"{'Removed':>{number_width}}  {'Remaining':>{number_width}}  "
        f"{'Retained':>9}  {'Time (ms)':>10}"
    )
    lines = [
        "whyempty | Filter diagnostic",
        f"Initial records: {initial_count}",
        header,
        "-" * len(header),
    ]
    for label, step in zip(labels, steps, strict=True):
        retention = step.retention_pct
        retained = f"{retention:.1f}%" if retention is not None else "N/A"
        lines.append(
            f"{label:<{name_width}}  {step.before:>{number_width}}  "
            f"{step.removed:>{number_width}}  {step.remaining:>{number_width}}  "
            f"{retained:>9}  {step.elapsed_seconds * 1000:>10.3f}"
        )
    if not steps:
        lines.append("No filters applied.")
    lines.append("Result: EMPTY" if count == 0 else f"Result: {count} records")
    first_empty = next((step for step in steps if step.emptied), None)
    if initial_count == 0:
        lines.append("The collection was empty from the start.")
    elif first_empty:
        lines.extend(
            [
                "All records were eliminated.",
                f"Final elimination: {first_empty.index}. {first_empty.name}",
            ]
        )
    significant = [
        f"{step.index}. {step.name}"
        for step in steps
        if step.significant_reduction and (first_empty is None or step.index < first_empty.index)
    ]
    if significant:
        lines.append("Significant reductions (at least 50% removed): " + ", ".join(significant))
    skipped = [f"{step.index}. {step.name}" for step in steps if step.skipped]
    if skipped:
        lines.append("Skipped (received zero records): " + ", ".join(skipped))
    return "\n".join(lines)
