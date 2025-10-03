from __future__ import annotations

import curses
from dataclasses import dataclass

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
    "C-b": "\x02",
    "C-<left>": "kLFT5",
    "C-p": "\x10",
    "C-n": "\x0e",
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


@dataclass
class WindowRegion:
    window: curses.window
    pos: Point = Point.ZERO
    size: Point = Point.ZERO
    content_base: Point = Point.ZERO

    @property
    def y(self):
        return self.pos.y

    @property
    def x(self):
        return self.pos.x

    @property
    def height(self):
        return self.size.y

    @property
    def width(self):
        return self.size.x

    def insstr(self, pos: Point, s: str, attr: int = 0):
        absolute_pos = pos - self.content_base
        if self.height > absolute_pos.y >= 0 and self.width > absolute_pos.x > -len(s):
            self.window.insstr(
                self.y + absolute_pos.y,
                self.x + max(0, absolute_pos.x),
                s[max(0, -absolute_pos.x) : self.width - absolute_pos.x],
                attr,
            )

    def chgat(self, pos: Point, width: int, attr: int):
        absolute_pos = pos - self.content_base
        if self.height > absolute_pos.y >= 0 and self.width > absolute_pos.x > -width:
            self.window.chgat(
                self.y + absolute_pos.y,
                self.x + max(0, absolute_pos.x),
                min(self.width, width - max(0, -absolute_pos.x)),
                attr,
            )
