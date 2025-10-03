from typing import cast, Any, override
from tjex.curses_helper import WindowRegion
from tjex.point import Point
from tjex.table_panel import EntryWidth, to_table_entry
import curses

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


def test_entry_width():
    data = [1.0]
    refs  = ["1.0000000"]
    entries = [to_table_entry(v) for v in data]
    width = EntryWidth(None, entries)
    for entry, ref in zip(entries, refs):
        dummy = WindowRegionDummy(Point(20,20))
        width.draw(dummy, Point.ZERO, entry)
        assert dummy.content == ref
