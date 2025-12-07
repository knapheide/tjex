from __future__ import annotations

import curses
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Self, override

from tjex.config import config
from tjex.curses_helper import DummyRegion, OffsetRegion, Region
from tjex.history import History
from tjex.kill_ring import KillRing
from tjex.panel import Event, KeyBindings, KeyPress, Panel, StatusUpdate
from tjex.point import Point


class TextPanel(Panel):
    def __init__(self, content: str, clear_first: bool = False):
        self.region: Region = DummyRegion()
        self.content: str = content
        self.attr: int = 0
        self.clear_first: bool = clear_first

    @override
    def resize(self, region: Region):
        self.region = region

    @override
    def handle_key(self, key: KeyPress):
        return [key]

    @override
    def draw(self):
        if self.clear_first:
            for i in range(self.region.height):
                self.region.insstr(Point(i, 0), self.region.width * " ")
        for i, s in enumerate(self.content.splitlines()):
            self.region.insstr(Point(i, 0), s, self.attr)


@dataclass(frozen=True)
class TextEditPanelState:
    content: str
    cursor: int = field(compare=False)


class TextEditPanel(Panel):
    bindings: KeyBindings[Self, None | Event] = KeyBindings()
    word_char_pattern: re.Pattern[str] = re.compile(r"[0-9a-zA-Z_-]")

    def __init__(self, content: str):
        self.region: OffsetRegion = OffsetRegion(DummyRegion(), Point.ZERO)
        self.content: str = content
        self.cursor: int = len(content)
        self.history: History[TextEditPanelState] = History(self.state)
        self.kill_ring: KillRing = KillRing()
        # If the last command was yank or rotate, the position where that yank started, None otherwise
        self.yank_start: int | None = None

    @override
    def resize(self, region: Region):
        self.region = OffsetRegion(region, self.region.offset)

    def next_word(self):
        next_cursor = self.cursor
        while next_cursor < len(self.content) and not self.word_char_pattern.fullmatch(
            self.content[next_cursor]
        ):
            next_cursor += 1
        while next_cursor < len(self.content) and self.word_char_pattern.fullmatch(
            self.content[next_cursor]
        ):
            next_cursor += 1
        return next_cursor

    def prev_word(self):
        next_cursor = self.cursor - 1
        while next_cursor >= 0 and not self.word_char_pattern.fullmatch(
            self.content[next_cursor]
        ):
            next_cursor -= 1
        while next_cursor >= 0 and self.word_char_pattern.fullmatch(
            self.content[next_cursor]
        ):
            next_cursor -= 1
        return next_cursor + 1

    def delete(self, until: int, kill: bool = False):
        until = max(0, min(until, len(self.content)))
        if kill:
            self.kill_ring.kill(
                self.content[min(self.cursor, until) : max(self.cursor, until)],
                prepend=self.cursor > until,
            )
        self.update(
            TextEditPanelState(
                self.content[: min(self.cursor, until)]
                + self.content[max(self.cursor, until) :],
                min(until, self.cursor),
            ),
            killing=kill,
        )

    @bindings.add("C-_")
    def undo(self):
        self.set_state(self.history.pop(self.state))

    @bindings.add("M-_")
    def redo(self):
        self.set_state(self.history.redo())

    @bindings.add("M-w")
    def copy(self):
        """Copy current prompt to clipboard"""
        config.do_copy(self.content)
        return StatusUpdate("Copied.")

    @bindings.add("C-k")
    def kill_line(self):
        """Delete everything to the right of the cursor"""
        self.delete(len(self.content), kill=True)

    @bindings.add("KEY_DC", "C-d")
    def delete_next_char(self):
        self.delete(self.cursor + 1)

    @bindings.add("M-KEY_DC", "M-d", "C-<delete>")
    def delete_next_word(self):
        self.delete(self.next_word(), kill=True)

    @bindings.add("KEY_BACKSPACE")
    def delete_prev_char(self):
        self.delete(self.cursor - 1)

    @bindings.add("M-KEY_BACKSPACE", "C-<backspace>")
    def delete_prev_word(self):
        self.delete(self.prev_word(), kill=True)

    @bindings.add("KEY_RIGHT", "C-f")
    def forward_char(self):
        self.kill_ring.kill_done()
        self.yank_start = None
        self.set_cursor(self.cursor + 1)

    @bindings.add("M-KEY_RIGHT", "C-<right>", "M-<right>", "M-f")
    def forward_word(self):
        self.kill_ring.kill_done()
        self.yank_start = None
        self.set_cursor(self.next_word())

    @bindings.add("KEY_LEFT", "C-b")
    def backward_char(self):
        self.kill_ring.kill_done()
        self.yank_start = None
        self.set_cursor(max(self.cursor - 1, 0))

    @bindings.add("M-KEY_LEFT", "C-<left>", "M-<left>", "M-b")
    def backward_word(self):
        self.kill_ring.kill_done()
        self.yank_start = None
        self.set_cursor(self.prev_word())

    @bindings.add("KEY_END", "C-e")
    def end(self):
        self.kill_ring.kill_done()
        self.yank_start = None
        self.set_cursor(len(self.content))

    @bindings.add("KEY_HOME", "C-a")
    def home(self):
        self.kill_ring.kill_done()
        self.yank_start = None
        self.set_cursor(0)

    @bindings.add("C-y")
    def yank(self):
        pre = self.content[: self.cursor] + self.kill_ring.yank()
        self.yank_start = self.cursor
        self.update(
            TextEditPanelState(
                pre + self.content[self.cursor :],
                len(pre),
            ),
            yanking=True,
        )

    @bindings.add("M-y")
    def rotate(self):
        if self.yank_start is not None:
            pre = self.content[: self.yank_start] + self.kill_ring.rotate()
            self.update(
                TextEditPanelState(
                    pre + self.content[self.cursor :],
                    len(pre),
                ),
                yanking=True,
            )

    @override
    def handle_key(self, key: KeyPress) -> Iterable[Event]:
        match self.bindings.handle_key(key, self):
            case None:
                return ()
            case KeyPress(key_str) if (
                len(key_str) == 1 and key_str not in "\n" and key_str.isprintable()
            ):
                self.kill_ring.kill_done()
                self.yank_start = None
                self.content = (
                    self.content[: self.cursor] + key_str + self.content[self.cursor :]
                )
                self.set_cursor(self.cursor + 1)
            case Event() as event:
                return (event,)
        return ()

    def set_cursor(self, cursor: int):
        self.cursor = max(0, min(len(self.content), cursor))
        self.update_content_base()

    def update_content_base(self):
        if self.cursor < self.region.offset.x:
            self.region.offset = Point(0, self.cursor)
        if self.cursor >= self.region.offset.x + self.region.width:
            self.region.offset = Point(0, self.cursor - self.region.width + 1)
        if len(self.content) < self.region.offset.x + self.region.width:
            self.region.offset = Point(
                0, max(0, len(self.content) - self.region.width + 1)
            )

    @override
    def draw(self):
        self.region.insstr(Point(0, 0), self.content)
        if self.active:
            self.region.chgat(Point(0, self.cursor), 1, curses.A_REVERSE)

    def update(
        self,
        state: str | TextEditPanelState,
        killing: bool = False,
        yanking: bool = False,
    ):
        if isinstance(state, str):
            state = TextEditPanelState(state, len(state))
        self.history.push(self.state)
        self.set_state(state, killing=killing, yanking=yanking)
        self.history.push(self.state)

    @property
    def state(self):
        return TextEditPanelState(self.content, self.cursor)

    def set_state(
        self, state: TextEditPanelState, killing: bool = False, yanking: bool = False
    ):
        if not killing:
            self.kill_ring.kill_done()
        if not yanking:
            self.yank_start = None
        self.content = state.content
        self.set_cursor(state.cursor)
