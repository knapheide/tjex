import curses
from timeit import timeit
from typing import Any, cast, override

import pytest
from tjex.curses_helper import WindowRegion
from tjex.json_table import (
    Json,
    JsonCellFormatter,
    TableCell,
    collect_keys,
    to_table_cell,
)
from tjex.point import Point


class WindowRegionDummy(WindowRegion):
    def __init__(self, size: Point):
        # Stub out curses functions that might get called
        curses.color_pair = lambda _: 0  # pyright: ignore[reportUnknownLambdaType]
        super().__init__(cast(Any, None), Point.ZERO, size, Point.ZERO)
        self.content: str = ""

    @override
    def insstr(self, pos: Point, s: str, attr: int = 0):
        self.content = pos.x * " " + s

    @override
    def chgat(self, pos: Point, width: int, attr: int):
        pass


def cell_to_string(
    formatter: JsonCellFormatter, cell: TableCell, max_width: int | None
):
    dummy = WindowRegionDummy(Point(20, 20))
    formatter.draw(cell, dummy, Point.ZERO, max_width, 0, False)
    return dummy.content


@pytest.mark.parametrize(
    "max_width,data,ref",
    [
        (50, [1.0], ["1.0000000"]),
        (50, [100.0], ["100.00000"]),
        (50, [-0.01, 0.01], ["-0.0100000", " 0.0100000"]),
        (4, [100000], ["100000"]),
        (4, [10000000], ["1.0e+07"]),
    ],
)
def test_column_formatter(max_width: int | None, data: list[Json], ref: list[str]):
    cells = [to_table_cell(v) for v in data]
    formatter = JsonCellFormatter(cells)
    assert ref == [cell_to_string(formatter, cell, max_width) for cell in cells]


def test_merge_keys_speed():
    # TODO some assertion for this?
    print(
        timeit(
            lambda: collect_keys(
                [[f"data.{i}" for i in range(100000 + 100000 * j)] for j in range(10)]
            ),
            number=1,
        )
    )
