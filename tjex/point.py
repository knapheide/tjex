from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class Point:
    y: int
    x: int

    def __add__(self, that: Point):
        return Point(self.y + that.y, self.x + that.x)

    def __sub__(self, that: Point):
        return Point(self.y - that.y, self.x - that.x)

    ZERO: ClassVar[Point]


Point.ZERO = Point(0, 0)
