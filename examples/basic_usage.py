"""Run with ``python examples/basic_usage.py`` after installing whyempty."""

import json
from typing import TypedDict

from whyempty import trace


class Record(TypedDict):
    """Fields in this example's application records."""

    id: int
    active: bool
    country: str
    score: int


records: list[Record] = [
    {"id": 1, "active": True, "country": "MX", "score": 40},
    {"id": 2, "active": False, "country": "MX", "score": 90},
    {"id": 3, "active": True, "country": "US", "score": 95},
]

result = (
    trace(records)
    .keep("Active", lambda row: row["active"])
    .keep("Mexico", lambda row: row["country"] == "MX")
    .keep("Score >= 80", lambda row: row["score"] >= 80)
)

print(result.explain())
print()
for rejection in result.rejected():
    print(
        f"Original index {rejection.original_index}: "
        f"step {rejection.step_index} ({rejection.filter_name})"
    )
print(json.dumps(result.to_dict(), indent=2))
