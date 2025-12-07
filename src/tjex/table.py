from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, TypeVar

from tjex.point import Point

if TYPE_CHECKING:
    from tjex.curses_helper import Region

T_Cell = TypeVar("T_Cell")
T_Key = TypeVar("T_Key")


class CellFormatter(ABC, Generic[T_Cell]):
    min_width: int
    width: int

    @abstractmethod
    def draw(
        self,
        cell: T_Cell,
        region: Region,
        pos: Point,
        max_width: int | None,
        attr: int,
        force_left: bool,
    ) -> None: ...

    def final_width(self, max_width: int | None):
        width = self.width
        if max_width is not None:
            width = min(width, max_width)
        return max(width, self.min_width)


@dataclass
class Table(Generic[T_Key, T_Cell]):
    content: dict[T_Key, dict[T_Key, T_Cell]]
    row_keys: list[T_Key]
    row_headers: list[T_Cell]
    col_keys: list[T_Key]
    col_headers: list[T_Cell]
    col_formatters: list[CellFormatter[T_Cell]]
