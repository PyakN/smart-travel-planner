"""HERE flexible polyline decoding (https://github.com/heremaps/flexible-polyline).

The format: a version and a header (precision, optional third dimension), then the
coordinate deltas, zigzag-encoded, as variable-length integers of 5-bit chunks written in
a URL-safe base64 alphabet.
"""

from collections.abc import Iterator

from app.optimizer.geometry import LatLon

FORMAT_VERSION = 1
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
_VALUES = {char: value for value, char in enumerate(ALPHABET)}


def _unsigned(encoded: str) -> Iterator[int]:
    value = shift = 0
    for char in encoded:
        chunk = _VALUES.get(char)
        if chunk is None:
            raise ValueError(f"invalid polyline character {char!r}")
        value |= (chunk & 0x1F) << shift
        if chunk & 0x20:  # more chunks follow
            shift += 5
        else:
            yield value
            value = shift = 0
    if shift:
        raise ValueError("polyline ends in the middle of a value")


def _signed(value: int) -> int:
    return ~(value >> 1) if value & 1 else value >> 1


def decode(encoded: str) -> list[LatLon]:
    """Points of the polyline; a third dimension (elevation, level...) is dropped."""
    values = _unsigned(encoded)
    version, header = next(values, None), next(values, None)
    if version != FORMAT_VERSION or header is None:
        raise ValueError("not a flexible polyline")
    factor = 10 ** (header & 0x0F)
    width = 3 if (header >> 4) & 0x07 else 2
    deltas = list(values)
    if len(deltas) % width:
        raise ValueError("polyline ends in the middle of a point")
    lat = lon = 0
    points = []
    for i in range(0, len(deltas), width):
        lat += _signed(deltas[i])
        lon += _signed(deltas[i + 1])
        points.append(LatLon(lat / factor, lon / factor))
    return points
