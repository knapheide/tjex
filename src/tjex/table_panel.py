from __future__ import annotations

import curses
from dataclasses import dataclass, replace
from typing import Generic, Self, override

from tjex.config import config
from tjex.curses_helper import (
    DummyRegion,
    OffsetRegion,
    Region,
    SubRegion,
)
from tjex.panel import Event, KeyBindings, KeyPress, Panel
from tjex.point import Point
from tjex.table import T_Cell, T_Key, Table
from tjex.utils import TjexError


class TableEmptyError(TjexError):
    def __init__(self):
        super().__init__("Table is empty")


@dataclass
class TableState:
    cursor: Point
    content_base: Point

    @property
    def row_only(self):
        return TableState(replace(self.cursor, x=0), replace(self.content_base, x=0))

    @property
    def col_only(self):
        return TableState(replace(self.cursor, y=0), replace(self.content_base, y=0))


class TablePanel(Panel, Generic[T_Key, T_Cell]):
    bindings: KeyBindings[Self, Event | None] = KeyBindings()

    def __init__(self, region: Region):
        self._max_cell_width: int | None = None
        self.full_cell_width: bool = False
        self.table: Table[T_Key, T_Cell] = Table({}, [], [], [], [], [])
        self.offsets: list[int] = []
        self.content_offset: Point = Point(1, 0)
        self.cursor: Point = Point(0, 0)
        self.region: Region = region
        self.content_region: OffsetRegion = OffsetRegion(DummyRegion(), Point.ZERO)
        self.row_header_region: OffsetRegion = OffsetRegion(DummyRegion(), Point.ZERO)
        self.col_header_region: OffsetRegion = OffsetRegion(DummyRegion(), Point.ZERO)

    @override
    def resize(self, region: Region):
        self.region = region
        self.row_header_region = OffsetRegion(
            SubRegion(
                region,
                replace(self.content_offset, x=0),
                region.size - replace(self.content_offset, x=0),
            ),
            self.row_header_region.offset,
        )
        self.col_header_region = OffsetRegion(
            SubRegion(
                region,
                replace(self.content_offset, y=0),
                region.size - replace(self.content_offset, y=0),
            ),
            self.col_header_region.offset,
        )
        self.content_region = OffsetRegion(
            SubRegion(region, self.content_offset, region.size - self.content_offset),
            self.content_region.offset,
        )

    @property
    def max_cell_width(self):
        if self.full_cell_width:
            return None
        return self._max_cell_width or config.max_cell_width

    def update(self, table: Table[T_Key, T_Cell], state: TableState | None):
        self.table = table

        self.offsets = [0]
        for formatter in table.col_formatters[1:]:
            self.offsets.append(
                self.offsets[-1] + formatter.final_width(self.max_cell_width) + 1
            )

        if not table.col_formatters:
            return

        self.content_offset = Point(
            1,
            table.col_formatters[0].final_width(self.max_cell_width) + 1,
        )
        self.resize(self.region)
        if state is not None:
            self.cursor = state.cursor
            self.content_region.offset = state.content_base
            self.clamp_cursor()
        else:
            self.cursor = Point(0, 0)
            self.content_region.offset = Point(0, 0)
        self.propagate_content_base()

    @property
    def state(self):
        return TableState(self.cursor, self.content_region.offset)

    @override
    def draw(self):
        table = self.table

        col_range = range(
            max(
                0,
                next(
                    (
                        i
                        for i, offset in enumerate(self.offsets)
                        if offset > self.content_region.offset.x
                    ),
                    len(self.offsets),
                )
                - 1,
            ),
            next(
                (
                    i
                    for i, offset in enumerate(self.offsets)
                    if offset
                    >= self.content_region.offset.x + self.content_region.width
                ),
                len(self.offsets) - 1,
            ),
        )
        row_range = range(
            self.content_region.offset.y,
            min(
                self.content_region.offset.y + self.content_region.height,
                len(table.row_keys),
            ),
        )

        for i in col_range:
            table.col_formatters[i + 1].draw(
                table.col_headers[i],
                self.col_header_region,
                Point(0, self.offsets[i]),
                self.max_cell_width,
                curses.A_BOLD,
                True,
            )

        for i in row_range:
            table.col_formatters[0].draw(
                table.row_headers[i],
                self.row_header_region,
                Point(i, 0),
                self.max_cell_width,
                curses.A_BOLD,
                False,
            )

        for i in row_range:
            for j in col_range:
                cell = table.content[table.row_keys[i]].get(table.col_keys[j], None)
                if cell is not None:
                    table.col_formatters[j + 1].draw(
                        cell,
                        self.content_region,
                        Point(i, self.offsets[j]),
                        self.max_cell_width,
                        0,
                        False,
                    )

        if self.active:
            self.chgat_cursor(curses.A_REVERSE)

    def chgat_cursor(self, a: int):
        if self.table.col_keys:
            self.content_region.chgat(
                Point(self.cursor.y, self.offsets[self.cursor.x]),
                self.table.col_formatters[self.cursor.x + 1].final_width(
                    self.max_cell_width
                ),
                a,
            )

    def clamp_cursor(self):
        table = self.table
        self.cursor = Point(
            max(0, min(len(table.row_keys) - 1, self.cursor.y)),
            max(0, min(len(table.col_keys) - 1, self.cursor.x)),
        )
        if not table.col_keys:
            return

        if (
            self.offsets[self.cursor.x + 1]
            >= self.content_region.width + self.content_region.offset.x
        ):
            self.content_region.offset = replace(
                self.content_region.offset,
                x=self.offsets[self.cursor.x + 1] - 1 - self.content_region.width,
            )
        if self.offsets[self.cursor.x] < self.content_region.offset.x:
            self.content_region.offset = replace(
                self.content_region.offset, x=self.offsets[self.cursor.x]
            )

        if (
            self.cursor.y + 1
            > self.content_region.height + self.content_region.offset.y
        ):
            self.content_region.offset = replace(
                self.content_region.offset,
                y=self.cursor.y + 1 - self.content_region.height,
            )
        if self.cursor.y < self.content_region.offset.y:
            self.content_region.offset = replace(
                self.content_region.offset, y=self.cursor.y
            )

        self.propagate_content_base()

    def propagate_content_base(self):
        self.row_header_region.offset = replace(self.content_region.offset, x=0)
        self.col_header_region.offset = replace(self.content_region.offset, y=0)

    @bindings.add("KEY_UP", "p", "C-p")
    def up(self):
        self.cursor += Point(-1, 0)

    @bindings.add("KEY_DOWN", "n", "C-n")
    def down(self):
        self.cursor += Point(1, 0)

    @bindings.add("KEY_LEFT", "b", "C-b")
    def left(self):
        self.cursor += Point(0, -1)

    @bindings.add("KEY_RIGHT", "f", "C-f")
    def right(self):
        self.cursor += Point(0, 1)

    @property
    def row_key(self):
        if not self.table.row_keys:
            raise TableEmptyError()
        return self.table.row_keys[self.cursor.y]

    @property
    def col_key(self):
        if not self.table.col_keys:
            raise TableEmptyError()
        return self.table.col_keys[self.cursor.x]

    @property
    def cell_keys(self):
        return (self.row_key, self.col_key)

    @bindings.add("M-<")
    def first_row(self):
        """Jump to first row"""
        self.cursor = replace(self.cursor, y=0)

    @bindings.add("M->")
    def last_row(self):
        """Jump to last row"""
        self.cursor = replace(self.cursor, y=len(self.table.row_keys) - 1)

    @bindings.add("KEY_NPAGE")
    def next_page(self):
        self.cursor += Point(self.content_region.height, 0)

    @bindings.add("KEY_PPAGE")
    def prev_page(self):
        self.cursor -= Point(self.content_region.height, 0)

    @bindings.add("KEY_END", "C-e")
    def last_col(self):
        """Jump to last column"""
        self.cursor = replace(self.cursor, x=len(self.table.col_keys) - 1)

    @bindings.add("KEY_HOME", "C-a")
    def first_col(self):
        """Jump to first column"""
        self.cursor = replace(self.cursor, x=0)

    @bindings.add("l")
    def full_width(self):
        """Toggle: rendering all cells with their full width vs. max_cell_width"""
        self.full_cell_width = not self.full_cell_width
        self.update(self.table, self.state)

    @bindings.add("+")
    def inc_width(self):
        """Increase max_cell_width by one"""
        self._max_cell_width = (self._max_cell_width or config.max_cell_width) + 1
        self.update(self.table, self.state)

    @bindings.add("-")
    def dec_width(self):
        """Decrease max_cell_width by one"""
        self._max_cell_width = max(
            1, (self._max_cell_width or config.max_cell_width) - 1
        )
        self.update(self.table, self.state)

    @override
    def handle_key(self, key: KeyPress) -> list[Event]:
        res = self.bindings.handle_key(key, self)
        if isinstance(res, str):
            return [res]
        self.clamp_cursor()
        if res is None:
            return []
        return [res]
