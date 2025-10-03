import curses
from typing import Any, cast, override

import pytest
from tjex.curses_helper import WindowRegion
from tjex.point import Point
from tjex.table_panel import EntryWidth, Json, TableEntry, to_table_entry


class WindowRegionDummy(WindowRegion):
    def __init__(self, size: Point):
        # Stub out curses functions that might get called
        curses.color_pair = lambda _: 0  # pyright: ignore[reportUnknownLambdaType]
        super().__init__(cast(Any, None), Point.ZERO, size, Point.ZERO)
        self.content: str = ""

    @override
    def insstr(self, pos: Point, s: str, attr: int = 0):
        self.content = s

    @override
    def chgat(self, pos: Point, width: int, attr: int):
        pass


def entry_to_string(width: EntryWidth, entry: TableEntry):
    dummy = WindowRegionDummy(Point(20, 20))
    width.draw(dummy, Point.ZERO, entry)
    return dummy.content


@pytest.mark.parametrize(
    "max_width,data,ref", [(50, [1.0], ["1.0000000"]), (4, [100000], ["1.0e+05"])]
)
def test_entry_width(max_width: int | None, data: list[Json], ref: list[str]):
    entries = [to_table_entry(v) for v in data]
    width = EntryWidth(max_width, entries)
    assert ref == [entry_to_string(width, entry) for entry in entries]
