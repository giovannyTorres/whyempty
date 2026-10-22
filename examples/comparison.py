"""Same surviving records; trace additionally explains the first empty stage."""

from whyempty import trace


def baseline(records):
    active = [row for row in records if row["active"]]
    local = [row for row in active if row["country"] == "MX"]
    return tuple(row for row in local if row["score"] >= 80)


def library(records):
    return (
        trace(records)
        .keep("Active", lambda row: row["active"])
        .keep("Mexico", lambda row: row["country"] == "MX")
        .keep("Score >= 80", lambda row: row["score"] >= 80)
        .items
    )


if __name__ == "__main__":
    records = [
        {"active": True, "country": "MX", "score": 40},
        {"active": False, "country": "MX", "score": 90},
        {"active": True, "country": "US", "score": 95},
    ]
    assert baseline(records) == library(records) == ()
    result = (
        trace(records)
        .keep("Active", lambda row: row["active"])
        .keep("Mexico", lambda row: row["country"] == "MX")
        .keep("Score >= 80", lambda row: row["score"] >= 80)
    )
    assert result.first_empty_step.name == "Score >= 80"
    print("Both return zero records; the first empty stage is Score >= 80.")
