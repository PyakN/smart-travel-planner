import pytest

from app.optimizer.geometry import LatLon
from app.optimizer.polyline import decode

# The examples of the format's specification (github.com/heremaps/flexible-polyline).
EXPECTED = [
    LatLon(50.10228, 8.69821),
    LatLon(50.10201, 8.69567),
    LatLon(50.10063, 8.6915),
    LatLon(50.09878, 8.68752),
]


def test_decodes_the_specification_example() -> None:
    assert decode("BFoz5xJ67i1B1B7PzIhaxL7Y") == EXPECTED


def test_drops_the_third_dimension() -> None:
    # Same points with altitudes 10, 20, 30, 40.
    assert decode("BlBoz5xJ67i1BU1B7PUzIhaUxL7YU") == EXPECTED


@pytest.mark.parametrize(
    "encoded",
    [
        "",
        "C",  # unknown format version
        "BFoz5xJ67i1B1B7PzIhaxL7",  # ends mid-point
        "BFoz5xJ67i1B1B7PzIhaxL7Y5",  # ends mid-value (continuation bit set)
        "BFoz5xJ67i1B1B7PzIha*L7Y",  # not in the alphabet
    ],
)
def test_rejects_broken_input(encoded: str) -> None:
    with pytest.raises(ValueError):
        decode(encoded)
