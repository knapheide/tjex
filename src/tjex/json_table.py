import curses
import json
from abc import ABC
from collections.abc import Iterable
from dataclasses import dataclass
from math import log10
from typing import override

from tjex.config import config
from tjex.curses_helper import WindowRegion
from tjex.point import Point
from tjex.table import CellFormatter, Table

type Json = str | int | float | bool | list[Json] | dict[str, Json] | None


@dataclass(frozen=True)
class Undefined:
    pass


type TableKey = str | int | Undefined


class TableCell(ABC):
    pass


@dataclass
class StringCell(TableCell):
    s: str
    color: int | None = None
    fixed_width: bool = False
    attr: int = 0


@dataclass
class NumberCell(TableCell):
    v: int | float


def to_table_cell(v: Json | Undefined) -> TableCell:
    match v:
        case False:
            return StringCell("false", curses.COLOR_RED, True)
        case True:
            return StringCell("true", curses.COLOR_GREEN, True)
        case float() | int():
            return NumberCell(v)
        case "":
            return StringCell('""', attr=curses.A_DIM)
        case str():
            encoded = json.dumps(v)
            if v != encoded[1:-1]:
                v = encoded
            return StringCell(v)
        case []:
            return StringCell(
                "[]",
                curses.COLOR_MAGENTA,
                True,
                curses.A_DIM,
            )
        case list():
            return StringCell("[…]", curses.COLOR_MAGENTA, True)
        case dict() if not v:
            return StringCell(
                "{}",
                curses.COLOR_MAGENTA,
                True,
                curses.A_DIM,
            )
        case dict():
            return StringCell("{…}", curses.COLOR_MAGENTA, True)
        case None:
            return StringCell("null", curses.COLOR_YELLOW, True, curses.A_DIM)
        case Undefined():
            return StringCell("")


def to_dict(v: Json) -> dict[TableKey, TableCell]:
    match v:
        case list():
            return {
                Undefined(): to_table_cell(v),
                **{i: to_table_cell(v) for i, v in enumerate(v)},
            }
        case dict():
            return {
                Undefined(): to_table_cell(v),
                **{k: to_table_cell(v) for k, v in v.items()},
            }
        case _:
            return {Undefined(): to_table_cell(v)}


type TableContent = dict[TableKey, dict[TableKey, TableCell]]


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


def compare_prefix_len(base: str | None, a: str, b: str):
    if base is None:
        return True
    for i, c in enumerate(base):
        if i >= len(a) or a[i] != c:
            return False
        if i >= len(b) or b[i] != c:
            return True
    return True


def merge_keys(a_set: set[str], a: list[str], b: list[str]):
    b_set = set(b)
    ia, ib = (0, 0)
    # Using a dict because it preserves insertion order
    res: dict[str, None] = {}
    prev_key = None
    while True:
        if ia >= len(a):
            return list(res.keys()) + b[ib:]
        if ib >= len(b):
            return list(res.keys()) + a[ia:]

        if a[ia] in res:
            ia += 1
        elif b[ib] in res:
            ib += 1
        elif a[ia] == b[ib]:
            res[a[ia]] = None
            prev_key = a[ia]
            ia += 1
            ib += 1
        elif b[ib] in a_set:
            res[a[ia]] = None
            prev_key = a[ia]
            ia += 1
        elif a[ia] in b_set:
            res[b[ib]] = None
            prev_key = b[ib]
            ib += 1
        elif compare_prefix_len(prev_key, a[ia], b[ib]):
            res[a[ia]] = None
            prev_key = a[ia]
            ia += 1
        else:
            res[b[ib]] = None
            prev_key = b[ib]
            ib += 1


def collect_keys(entries: Iterable[Iterable[TableKey]]):
    undefined = set[Undefined]()
    keys_set = set[str]()
    keys_order: list[str] = []
    max_len = 0
    for entry in entries:
        undefined.update({key for key in entry if isinstance(key, Undefined)})
        max_len = max([max_len, *(key + 1 for key in entry if isinstance(key, int))])
        str_keys = [key for key in entry if isinstance(key, str)]
        if any(key not in keys_set for key in str_keys):
            keys_order = merge_keys(keys_set, keys_order, str_keys)
            keys_set.update(str_keys)
    return [*undefined, *keys_order, *range(max_len)]


def integer_digits(v: int | float):
    if int(abs(v)) == 0:
        return 1
    return int(log10(int(abs(v)))) + 1


class JsonCellFormatter(CellFormatter[TableCell]):
    def __init__(self, cells: Iterable[TableCell]):
        min_scientific_width = 7

        # For StringCells
        min_width = 1
        full_width = 1

        # For NumberCells
        negative = False
        integer_width = 1
        fraction_width = None

        for cell in cells:
            match cell:
                case StringCell():
                    full_width = max(full_width, len(cell.s))
                    if cell.fixed_width:
                        min_width = max(min_width, len(cell.s))
                case NumberCell(v):
                    if v < 0:
                        negative = True
                    integer_width = max(integer_width, integer_digits(v))
                    if isinstance(v, float):
                        if fraction_width is None:
                            fraction_width = 1
                        if v != 0.0:
                            fraction_width = max(
                                fraction_width,
                                config.float_precision - integer_digits(v),
                            )
                case _:
                    pass

        self.negative: bool = negative
        self.integer_width: int = integer_width
        self.fraction_width: int | None = fraction_width
        self.min_width: int = max(
            min_width,
            negative
            + min(
                integer_width + 2 * (fraction_width is not None), min_scientific_width
            ),
        )
        self.width: int = max(
            full_width, negative + integer_width + 1 + (fraction_width or -1)
        )

    @override
    def draw(
        self,
        cell: TableCell,
        region: WindowRegion,
        pos: Point,
        max_width: int | None,
        attr: int,
        force_left: bool,
    ):
        width = self.final_width(max_width)

        def leading_underscores(pos: Point, width: int):
            if width > 1:
                region.chgat(
                    pos,
                    width - 1,
                    curses.color_pair(curses.COLOR_BLUE)
                    | curses.A_DIM
                    | curses.A_UNDERLINE
                    | attr,
                )

        match cell:
            case StringCell():
                s = cell.s
                if len(s) > width:
                    s = s[: width - 1] + "…"
                region.insstr(
                    pos,
                    s,
                    cell.attr
                    | (0 if cell.color is None else curses.color_pair(cell.color))
                    | attr,
                )
            case NumberCell(v):
                integer_width = min(
                    self.integer_width,
                    width - self.negative - 2 * (self.fraction_width is not None),
                )
                fraction_width = self.fraction_width and min(
                    self.fraction_width, width - self.negative - integer_width - 1
                )

                if (int_pad := integer_width - integer_digits(v)) >= 0:
                    pad = Point(
                        0, (v >= 0 and self.negative) + (not force_left) * int_pad
                    )
                    if isinstance(v, int):
                        region.insstr(
                            pos + pad,
                            f"{{:d}}".format(v),
                            curses.color_pair(curses.COLOR_BLUE) | attr,
                        )
                    else:
                        assert fraction_width is not None
                        fraction_width = max(
                            1,
                            min(
                                fraction_width,
                                config.float_precision - integer_digits(v),
                            ),
                        )
                        region.insstr(
                            pos + pad,
                            f"{{:.{fraction_width}f}}".format(v),
                            curses.color_pair(curses.COLOR_BLUE) | attr,
                        )
                    leading_underscores(
                        pos,
                        self.negative + integer_width - (v < 0) - integer_digits(v),
                    )
                else:
                    region.insstr(
                        pos + Point(0, (v >= 0 and self.negative) + 0),
                        f"{{:.{min(config.float_precision, width-self.negative-6)}e}}".format(
                            v
                        ),
                        curses.color_pair(curses.COLOR_BLUE) | attr,
                    )

            case _:
                pass


def json_to_table(v: Json) -> Table[int | str | Undefined, TableCell]:
    content = to_table_content(v)

    row_keys = collect_keys([r] for r in content.keys())
    row_headers = [to_table_cell(r) for r in row_keys]
    col_keys = collect_keys(r.keys() for r in content.values())
    col_headers = [to_table_cell(c) for c in col_keys]

    return Table(
        content,
        row_keys,
        row_headers,
        col_keys,
        col_headers,
        [
            JsonCellFormatter(row_headers),
            *(
                JsonCellFormatter(
                    [h, *(r[c] for r in content.values() if c in r)],
                )
                for c, h in zip(col_keys, col_headers)
            ),
        ],
    )
