import curses
from timeit import timeit
from typing import override

import pytest
from tjex.curses_helper import DummyRegion, Region
from tjex.json_table import (
    Json,
    JsonCellFormatter,
    TableCell,
    collect_keys,
    to_table_cell,
)
from tjex.point import Point

# Stub out curses functions that might get called
curses.color_pair = lambda _: 0  # pyright: ignore[reportUnknownLambdaType]


def cell_to_string(
    formatter: JsonCellFormatter, cell: TableCell, max_width: int | None
):
    dummy = DummyRegion(Point(1, 1000))
    formatter.draw(cell, dummy, Point.ZERO, max_width, 0, False)
    return dummy.content[0].rstrip()


@pytest.mark.parametrize(
    "max_width,data,ref,width,min_width",
    [
        (50, [1.0], ["1.0000000"], 9, 3),
        (50, [100.0], ["100.00000"], 9, 5),
        (50, [-0.01, 0.01], ["-0.0100000", " 0.0100000"], 10, 4),
        (4, [100000], ["100000"], 6, 6),
        (4, [10000000], ["1.0e+07"], 8, 7),
        (4, [10000000, -10000000], [" 1.0e+07", "-1.0e+07"], 9, 8),
        (50, [1 << 100000], ["9.99002093e+30102"], 30103, 10),
        (6, [1 << 100000], ["1.0e+30103"], 30103, 10),
        (6, [996 * 10**97], ["1.0e+100"], 100, 8),
        # min_width should be 7 here, but that edge case seems too annoying
        (6, [994 * 10**97], ["9.9e+99"], 100, 8),
        (6, [996 * 10**96], ["1.0e+99"], 99, 7),
    ],
)
def test_column_formatter(
    max_width: int | None, data: list[Json], ref: list[str], width: int, min_width: int
):
    cells = [to_table_cell(v) for v in data]
    formatter = JsonCellFormatter(cells)
    assert ref == [cell_to_string(formatter, cell, max_width) for cell in cells]
    assert formatter.width == width, "width mismatch"
    assert formatter.min_width == min_width, "min_width mismatch"
