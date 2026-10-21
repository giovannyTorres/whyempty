"""Reuse filters and find the smallest relaxation that recovers empty results."""

import json
from typing import TypedDict

from whyempty import Pipeline


class Record(TypedDict):
    """Fields accepted by every rule in this example."""

    active: bool
    country: str
    score: int


records: list[Record] = [
    {"active": True, "country": "MX", "score": 40},
    {"active": False, "country": "MX", "score": 90},
    {"active": True, "country": "US", "score": 95},
]

rules = (
    Pipeline[Record]()
    .keep("Active", lambda row: row["active"])
    .keep("Mexico", lambda row: row["country"] == "MX")
    .keep("Score >= 80", lambda row: row["score"] >= 80)
)

print(rules.run(records).explain())
print()
audited = rules.audit(records)
print(audited.explain())
assert audited.is_empty
assert [rule.name for rule in audited.failed_filters(0)] == ["Score >= 80"]
assert audited.relax(3).remaining == 1
assert audited.matching_indices(without=(3,)) == (0,)
assert len(audited.suggest_relaxations()) == 3
print(json.dumps(audited.to_dict(), indent=2))
