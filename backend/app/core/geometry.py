"""Small 2D geometry helpers used by the generator and renderer payloads."""

from __future__ import annotations

import math
from collections.abc import Sequence

Point = tuple[float, float]


def distance(a: Point, b: Point) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def manhattan(a: Point, b: Point) -> float:
    return abs(b[0] - a[0]) + abs(b[1] - a[1])


def signed_area(points: Sequence[Point]) -> float:
    total = 0.0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def centroid(points: Sequence[Point]) -> Point:
    n = len(points)
    return (sum(p[0] for p in points) / n, sum(p[1] for p in points) / n)


def point_line_distance(p: Point, a: Point, b: Point) -> float:
    """Distance from ``p`` to the infinite line through ``a`` and ``b``."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    if length == 0:
        return distance(p, a)
    return abs(dy * p[0] - dx * p[1] + b[0] * a[1] - b[1] * a[0]) / length


def lerp(a: Point, b: Point, t: float) -> Point:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
