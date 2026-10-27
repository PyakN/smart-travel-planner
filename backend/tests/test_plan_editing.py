import pytest

from app.services.plan_editing import SPARSE_SHRINK_MIN, dominant_category, is_sparse


@pytest.mark.parametrize(
    ("now", "before", "sparse"),
    [
        ((4, 300), (4, 300), False),
        ((4, 300 - SPARSE_SHRINK_MIN), (4, 300), False),
        ((4, 300 - SPARSE_SHRINK_MIN - 1), (4, 300), True),  # much shorter
        ((3, 300), (4, 300), True),  # fewer stops
        ((5, 200), (4, 300), True),
    ],
)
def test_is_sparse(now: tuple[int, int], before: tuple[int, int], sparse: bool) -> None:
    assert is_sparse(*now, *before) is sparse


@pytest.mark.parametrize(
    ("categories", "interests", "expected"),
    [
        (["religious"] * 3 + ["park"], ["viewpoint"], "religious"),
        (["religious"] * 2 + ["park", "museum"], ["viewpoint"], None),  # half is fine
        (["religious"] * 3, ["viewpoint"], None),  # too short a day to judge
        (["religious"] * 4 + ["park"], ["religious"], None),  # exactly what was asked for
        (["museum"] * 3 + ["park"], ["museum", "park"], "museum"),
    ],
)
def test_dominant_category(
    categories: list[str], interests: list[str], expected: str | None
) -> None:
    assert dominant_category(categories, interests) == expected
