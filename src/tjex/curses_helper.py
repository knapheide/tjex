from __future__ import annotations

import curses
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from typing import override

from tjex.logging import logger
from tjex.point import Point


def setup_plain_colors():
    curses.start_color()
    for i in range(1, 8):
        curses.init_pair(i, i, curses.COLOR_BLACK)


KEY_ALIASES = {
    "C-g": "\x07",
    "C-d": "\x04",
    "C-o": "\x0f",
    "C-_": "\x1f",
    "C-e": "\x05",
    "C-a": "\x01",
    "C-k": "\x0b",
    "C-<delete>": "kDC5",
    "C-<backspace>": "\x08",
    "C-f": "\x06",
    "C-<right>": "kRIT5",
    "M-<right>": "kRIT3",
    "C-b": "\x02",
    "C-<left>": "kLFT5",
    "M-<left>": "kLFT3",
    "C-p": "\x10",
    "C-n": "\x0e",
    "C-y": "\x19",
}


class KeyReader:
    def __init__(self, window: curses.window):
        curses.set_escdelay(10)
        window.keypad(True)
        window.nodelay(True)
        window.notimeout(False)
        self.window: curses.window = window

    def get(self) -> str | None:
        try:
            prefix = ""
            key = self.window.get_wch()
            if key == "\x1b":
                try:
                    prefix = "M-"
                    key = self.window.get_wch()
                except curses.error:
                    return "ESC"
            if isinstance(key, int):
                key = curses.keyname(key).decode("utf-8")
            key = prefix + key
            logger.debug(f"{key=}")
            return key
        except curses.error:
            return None


class Region(ABC):
    size: Point = Point.ZERO

    @property
    def height(self):
        return self.size.y

    @property
    def width(self):
        return self.size.x

    @abstractmethod
    def insstr(self, pos: Point, s: str, attr: int = 0) -> None:
        pass

    @abstractmethod
    def chgat(self, pos: Point, width: int, attr: int) -> None:
        pass

    def resize(self):
        """If this region's size depends on external resources.
        (Currently only used for WindowRegion)
        """


class DummyRegion(Region):
    @override
    def insstr(self, pos: Point, s: str, attr: int = 0) -> None:
        pass

    @override
    def chgat(self, pos: Point, width: int, attr: int) -> None:
        pass


class WindowRegion(Region):
    def __init__(self, window: curses.window):
        self.window: curses.window = window
        self.resize()

    @override
    def insstr(self, pos: Point, s: str, attr: int = 0):
        if self.height > pos.y >= 0 and self.width > pos.x > -len(s):
            self.window.insstr(
                pos.y, max(0, pos.x), s[max(0, -pos.x) : self.width - pos.x], attr
            )

    @override
    def chgat(self, pos: Point, width: int, attr: int):
        if self.height > pos.y >= 0 and self.width > pos.x > -width:
            self.window.chgat(
                pos.y, max(0, pos.x), min(self.width, width - max(0, -pos.x)), attr
            )

    @override
    def resize(self):
        self.size: Point = Point(*self.window.getmaxyx())


@dataclass
class SubRegion(Region):
    parent: Region
    pos: Point = Point.ZERO
    size: Point = Point.ZERO

    @property
    def y(self):
        return self.pos.y

    @property
    def x(self):
        return self.pos.x

    @override
    def insstr(self, pos: Point, s: str, attr: int = 0):
        if self.height > pos.y >= 0 and self.width > pos.x > -len(s):
            self.parent.insstr(
                self.pos + replace(pos, x=max(0, pos.x)),
                s[max(0, -pos.x) : self.width - pos.x],
                attr,
            )

    @override
    def chgat(self, pos: Point, width: int, attr: int):
        if self.height > pos.y >= 0 and self.width > pos.x > -width:
            self.parent.chgat(
                self.pos + replace(pos, x=max(0, pos.x)),
                min(self.width, width - max(0, -pos.x)),
                attr,
            )


class OffsetRegion(Region):
    def __init__(self, parent: Region, offset: Point):
        self.parent: Region = parent
        self.size: Point = parent.size
        self.offset: Point = offset

    @override
    def insstr(self, pos: Point, s: str, attr: int = 0):
        self.parent.insstr(pos - self.offset, s, attr)

    @override
    def chgat(self, pos: Point, width: int, attr: int):
        self.parent.chgat(pos - self.offset, width, attr)
