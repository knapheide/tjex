from __future__ import annotations

import curses
import json
import re
from abc import ABC
from collections.abc import Iterable
from dataclasses import dataclass, replace
from math import log10
from typing import Self, override

from tjex.curses_helper import WindowRegion
from tjex.logging import logger
from tjex.panel import Event, KeyBindings, KeyPress, Panel
from tjex.point import Point


@dataclass(frozen=True)
class Undefined:
    pass


type Json = str | int | float | bool | list[Json] | dict[str, Json] | None


class TableEntry(ABC):
    pass


@dataclass
class StringEntry(TableEntry):
    s: str
    color: int | None = None
    fixed_width: bool = False
    attr: int = 0


@dataclass
class NumberEntry(TableEntry):
    v: int | float


FLOAT_PRECISION = 10


def integer_digits(v: int | float):
    if int(abs(v)) == 0:
        return 1
    return int(log10(int(abs(v)))) + 1


def integer_chars(v: int | float):
    return integer_digits(v) + (v < 0)


class EntryWidth:
    def __init__(self, max_width: int | None, entries: Iterable[TableEntry]):
        min_width = 1
        full_width = 1
        integer_width = 1
        fraction_width = None
        for entry in entries:
            match entry:
                case StringEntry():
                    full_width = max(full_width, len(entry.s))
                    if entry.fixed_width:
                        min_width = max(min_width, len(entry.s))
                case NumberEntry(v):
                    if int(v) != 0:
                        integer_width = max(integer_width, integer_chars(v))
                    if isinstance(v, float):
                        min_width = max(min_width, 7)
                        if fraction_width is None:
                            fraction_width = 1
                        if v != 0.0:
                            fraction_width = max(
                                fraction_width,
                                FLOAT_PRECISION + integer_digits(v),
                            )
                case _:
                    pass
        full_width = max(full_width, integer_width + 1 + (fraction_width or -1))
        if max_width is None:
            max_width = full_width
        self.min_width: int = min_width
        self.full_width: int = full_width
        self.width: int = max(min_width, min(max_width, full_width))
        if max_width < integer_width + 1 + (fraction_width or -1):
            fraction_width = None
        if max_width < integer_width:
            integer_width = max_width
        self.integer_width: int = integer_width
        self.fraction_width: int | None = fraction_width

    def draw(
        self,
        window: WindowRegion,
        pos: Point,
        entry: TableEntry,
        attr: int = 0,
        force_left: bool = False,
    ):
        match entry:
            case StringEntry():
                s = entry.s
                if len(s) > self.width:
                    s = s[: self.width - 1] + "…"
                window.insstr(
                    pos,
                    s,
                    entry.attr
                    | (0 if entry.color is None else curses.color_pair(entry.color))
                    | attr,
                )
            case NumberEntry(v):
                if isinstance(v, int) and integer_chars(v) <= self.integer_width:
                    if force_left:
                        window.insstr(
                            pos,
                            str(v),
                            curses.color_pair(curses.COLOR_BLUE) | attr,
                        )
                    else:
                        window.insstr(
                            pos,
                            f"{{:{self.integer_width}d}}".format(v),
                            curses.color_pair(curses.COLOR_BLUE) | attr,
                        )
                        window.chgat(
                            pos,
                            self.integer_width - integer_chars(v),
                            curses.color_pair(curses.COLOR_BLUE)
                            | curses.A_DIM
                            | curses.A_UNDERLINE
                            | attr,
                        )
                elif self.fraction_width is None:
                    window.insstr(
                        pos,
                        f"{{:.{min(FLOAT_PRECISION, self.width-6)}e}}".format(v),
                        curses.color_pair(curses.COLOR_BLUE) | attr,
                    )
                else:
                    fraction_width = max(
                        1,
                        min(self.fraction_width, FLOAT_PRECISION - integer_digits(v)),
                    )
                    window.insstr(
                        pos,
                        f"{{:{self.integer_width + 1 + fraction_width}.{fraction_width}f}}".format(
                            v
                        ),
                        curses.color_pair(curses.COLOR_BLUE) | attr,
                    )
                    window.chgat(
                        pos,
                        self.integer_width - integer_chars(v),
                        curses.color_pair(curses.COLOR_BLUE)
                        | curses.A_DIM
                        | curses.A_UNDERLINE
                        | attr,
                    )
            case _:
                pass


type TableKey = str | int | Undefined
type TableContent = dict[TableKey, dict[TableKey, TableEntry]]


def to_table_entry(v: Json | Undefined) -> TableEntry:
    match v:
        case False:
            return StringEntry("false", curses.COLOR_RED, True)
        case True:
            return StringEntry("true", curses.COLOR_GREEN, True)
        case float() | int():
            return NumberEntry(v)
        case "":
            return StringEntry('""', attr=curses.A_DIM)
        case str():
            encoded = json.dumps(v)
            if v != encoded[1:-1]:
                v = encoded
            return StringEntry(v)
        case []:
            return StringEntry(
                "[]",
                curses.COLOR_MAGENTA,
                True,
                curses.A_DIM,
            )
        case list():
            return StringEntry("[…]", curses.COLOR_MAGENTA, True)
        case dict() if not v:
            return StringEntry(
                "{}",
                curses.COLOR_MAGENTA,
                True,
                curses.A_DIM,
            )
        case dict():
            return StringEntry("{…}", curses.COLOR_MAGENTA, True)
        case None:
            return StringEntry("null", curses.COLOR_YELLOW, True, curses.A_DIM)
        case Undefined():
            return StringEntry("")


def to_dict(v: Json) -> dict[TableKey, TableEntry]:
    match v:
        case list():
            return {i: to_table_entry(v) for i, v in enumerate(v)}
        case dict():
            return {k: to_table_entry(v) for k, v in v.items()}
        case _:
            return {Undefined(): to_table_entry(v)}


def to_table_content(
    v: Json,
) -> TableContent:
    match v:
        case list():
            return {i: to_dict(v) for i, v in enumerate(v)}
        case dict():
            return {k: to_dict(v) for k, v in v.items()}
        case _:
            return {Undefined(): to_dict(v)}


identifier_pattern = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")


def key_to_selector(key: TableKey):
    match key:
        case Undefined():
            return ""
        case str() if identifier_pattern.fullmatch(key):
            return f".{key}"
        case _:
            return f".[{json.dumps(key)}]"


@dataclass
class TableState:
    cursor: Point
    content_base: Point


class TablePanel(Panel):
    bindings: KeyBindings[Self, Select | None] = KeyBindings()

    def __init__(self, window: WindowRegion, max_cell_width: int):
        self.window: WindowRegion = window
        self._max_cell_width: int = max_cell_width
        self.full_cell_width: bool = False
        self.content: TableContent = {}
        self.col_keys: list[TableKey] = []
        self.col_widths: list[EntryWidth] = []
        self.row_keys: list[TableKey] = []
        self.offsets: list[int] = []
        self.row_header_width: EntryWidth = EntryWidth(None, [])
        self.content_offset: Point = Point(1, 0)
        self.cursor: Point = Point(0, 0)
        self.content_window: WindowRegion = WindowRegion(self.window.window)
        self.row_header_window: WindowRegion = WindowRegion(self.window.window)
        self.col_header_window: WindowRegion = WindowRegion(self.window.window)

    @override
    def resize(self):
        self.row_header_window.pos = replace(self.content_offset, x=0) + self.window.pos
        self.row_header_window.size = self.window.size - replace(
            self.content_offset, x=0
        )
        self.col_header_window.pos = replace(self.content_offset, y=0) + self.window.pos
        self.col_header_window.size = self.window.size - replace(
            self.content_offset, y=0
        )
        self.content_window.pos = self.content_offset + self.window.pos
        self.content_window.size = self.window.size - self.content_offset

    @dataclass
    class Select(Event):
        selector: str

    @property
    def max_cell_width(self):
        if self.full_cell_width:
            return None
        return self._max_cell_width

    def update(self, content: TableContent, state: TableState | None):
        self.content = content

        # Using dicts here because that retains the order
        self.col_keys = list({c: c for r in self.content.values() for c in r.keys()})
        self.row_keys = list({r: r for r in self.content.keys()})

        self.col_keys.sort(
            key=lambda k: 0 if k == Undefined() else 1 if isinstance(k, str) else 2
        )
        self.row_keys.sort(
            key=lambda k: 0 if k == Undefined() else 1 if isinstance(k, str) else 2
        )

        self.col_widths = [
            EntryWidth(
                self.max_cell_width,
                [to_table_entry(c), *(r[c] for r in self.content.values() if c in r)],
            )
            for c in self.col_keys
        ]

        self.offsets = [0]
        for width in self.col_widths:
            self.offsets.append(self.offsets[-1] + width.width + 1)

        self.row_header_width = EntryWidth(
            self.max_cell_width,
            [to_table_entry(r) for r in self.row_keys],
        )
        self.content_offset = Point(
            1,
            self.row_header_width.width + 1,
        )
        logger.debug(f"{self.content_offset=}")
        self.resize()
        if state is not None:
            self.cursor = state.cursor
            self.content_window.content_base = state.content_base
        else:
            self.cursor = Point(0, 0)
            self.content_window.content_base = Point(0, 0)
        self.propagate_content_base()

    @property
    def state(self):
        return TableState(self.cursor, self.content_window.content_base)

    @override
    def draw(self):
        col_range = range(
            max(
                0,
                next(
                    (
                        i
                        for i, offset in enumerate(self.offsets)
                        if offset > self.content_window.content_base.x
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
                    >= self.content_window.content_base.x + self.content_window.width
                ),
                len(self.offsets) - 1,
            ),
        )
        row_range = range(
            self.content_window.content_base.y,
            min(
                self.content_window.content_base.y + self.content_window.height,
                len(self.row_keys),
            ),
        )

        for i in col_range:
            self.col_widths[i].draw(
                self.col_header_window,
                Point(0, self.offsets[i]),
                to_table_entry(self.col_keys[i]),
                curses.A_BOLD,
                force_left=True,
            )

        for i in row_range:
            self.row_header_width.draw(
                self.row_header_window,
                Point(i, 0),
                to_table_entry(self.row_keys[i]),
                curses.A_BOLD,
            )

        for i in row_range:
            for j in col_range:
                entry = self.content[self.row_keys[i]].get(self.col_keys[j], None)
                if entry is not None:
                    self.col_widths[j].draw(
                        self.content_window,
                        Point(i, self.offsets[j]),
                        entry,
                    )

        if self.active:
            self.chgat_cursor(curses.A_REVERSE)

    def chgat_cursor(self, a: int):
        if len(self.col_widths) > 0:
            self.content_window.chgat(
                Point(self.cursor.y, self.offsets[self.cursor.x]),
                self.col_widths[self.cursor.x].width,
                a,
            )

    def clamp_cursor(self):
        self.cursor = Point(
            max(0, min(len(self.row_keys) - 1, self.cursor.y)),
            max(0, min(len(self.col_keys) - 1, self.cursor.x)),
        )

        if (
            self.offsets[self.cursor.x] + self.col_widths[self.cursor.x].width
            > self.content_window.width + self.content_window.content_base.x
        ):
            self.content_window.content_base = replace(
                self.content_window.content_base,
                x=self.offsets[self.cursor.x]
                + self.col_widths[self.cursor.x].width
                - self.content_window.width,
            )
        if self.offsets[self.cursor.x] < self.content_window.content_base.x:
            self.content_window.content_base = replace(
                self.content_window.content_base, x=self.offsets[self.cursor.x]
            )

        if (
            self.cursor.y + 1
            > self.content_window.height + self.content_window.content_base.y
        ):
            self.content_window.content_base = replace(
                self.content_window.content_base,
                y=self.cursor.y + 1 - self.content_window.height,
            )
        if self.cursor.y < self.content_window.content_base.y:
            self.content_window.content_base = replace(
                self.content_window.content_base, y=self.cursor.y
            )

        self.propagate_content_base()

    def propagate_content_base(self):
        self.row_header_window.content_base = replace(
            self.content_window.content_base, x=0
        )
        self.col_header_window.content_base = replace(
            self.content_window.content_base, y=0
        )

    @bindings.add("KEY_UP", "\x10")  # C-p
    def up(self):
        self.cursor += Point(-1, 0)

    @bindings.add("KEY_DOWN", "\x0e")  # C-n
    def down(self):
        self.cursor += Point(1, 0)

    @bindings.add("KEY_LEFT", "\x02")  # C-b
    def left(self):
        self.cursor += Point(0, -1)

    @bindings.add("KEY_RIGHT", "\x06")  # C-f
    def right(self):
        self.cursor += Point(0, 1)

    @bindings.add("\n")
    def enter_cell(self):
        try:
            return self.Select(
                key_to_selector(self.row_keys[self.cursor.y])
                + key_to_selector(self.col_keys[self.cursor.x])
            )
        except KeyError:
            pass

    @bindings.add("M-\n")
    def enter_row(self):
        try:
            return self.Select(key_to_selector(self.row_keys[self.cursor.y]))
        except KeyError:
            pass

    @bindings.add("M-<")
    def first_row(self):
        self.cursor = replace(self.cursor, y=0)

    @bindings.add("M->")
    def last_row(self):
        self.cursor = replace(self.cursor, y=len(self.row_keys) - 1)

    @bindings.add("KEY_NPAGE")
    def next_page(self):
        self.cursor += Point(self.content_window.height, 0)

    @bindings.add("KEY_PPAGE")
    def prev_page(self):
        self.cursor -= Point(self.content_window.height, 0)

    @bindings.add("KEY_END", "\x05")  # C-e
    def last_col(self):
        self.cursor = replace(self.cursor, x=len(self.col_keys) - 1)

    @bindings.add("KEY_HOME", "\x01")  # C-a
    def first_col(self):
        self.cursor = replace(self.cursor, x=0)

    @bindings.add("l")
    def full_width(self):
        self.full_cell_width = not self.full_cell_width
        self.update(self.content, self.state)

    @bindings.add("+")
    def inc_width(self):
        self._max_cell_width += 1
        self.update(self.content, self.state)

    @bindings.add("-")
    def dec_width(self):
        self._max_cell_width -= 1
        self.update(self.content, self.state)

    @override
    def handle_key(self, key: KeyPress) -> list[KeyPress | Select]:
        res = self.bindings.handle_key(key, self)
        if isinstance(res, str):
            return [res]
        self.clamp_cursor()
        if res is None:
            return []
        return [res]
