"""Large-input correctness without machine-dependent timing assertions."""

from whyempty import trace


def test_hundred_thousand_records_have_exact_counts_and_single_evaluations() -> None:
    calls = [0, 0, 0]

    def even(n: int) -> bool:
        calls[0] += 1
        return n % 2 == 0

    def divisible_by_three(n: int) -> bool:
        calls[1] += 1
        return n % 3 == 0

    def small(n: int) -> bool:
        calls[2] += 1
        return n < 1_000

    result = (
        trace(range(100_000))
        .keep("even", even)
        .keep("divisible by three", divisible_by_three)
        .keep("small", small)
    )
    expected = tuple(n for n in range(100_000) if n % 2 == 0 and n % 3 == 0 and n < 1_000)
    assert result.items == expected
    assert result.count == 167
    assert calls == [100_000, 50_000, 16_667]
    assert [(s.before, s.removed, s.remaining) for s in result.steps] == [
        (100_000, 50_000, 50_000),
        (50_000, 33_333, 16_667),
        (16_667, 16_500, 167),
    ]
    rejections = result.rejected()
    assert len(rejections) == 99_833
    assert rejections[0].original_index == 1
    assert rejections[-1].original_index == 99_999
    assert all(
        a.original_index < b.original_index
        for a, b in zip(rejections, rejections[1:], strict=False)
    )
    result.explain()
    result.to_dict()
    assert calls == [100_000, 50_000, 16_667]
