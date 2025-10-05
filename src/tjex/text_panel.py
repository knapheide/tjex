from __future__ import annotations

import curses
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Self, override

from tjex.config import config
from tjex.curses_helper import WindowRegion
from tjex.history import History
from tjex.panel import Event, KeyBindings, KeyPress, Panel, StatusUpdate
from tjex.point import Point


class TextPanel(Panel):
    def __init__(self, window: WindowRegion, content: str):
        self.window: WindowRegion = window
        self.content: str = content

    @override
    def handle_key(self, key: KeyPress):
        return [key]

    @override
    def draw(self):
        for i, s in enumerate(self.content.splitlines()):
            self.window.insstr(Point(i, 0), s)


@dataclass(frozen=True)
class TextEditPanelState:
    content: str
    cursor: int = field(compare=False)


class TextEditPanel(Panel):
    bindings: KeyBindings[Self, None | Event] = KeyBindings()
    word_char_pattern: re.Pattern[str] = re.compile(r"[0-9a-zA-Z_-]")

    def __init__(self, window: WindowRegion, content: str):
        self.window: WindowRegion = window
        self.content: str = content
        self.cursor: int = len(content)
        self.history: History[TextEditPanelState] = History(self.state)

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

    def delete(self, until: int):
        until = max(0, min(until, len(self.content)))
        self.update(
            TextEditPanelState(
                self.content[: min(self.cursor, until)]
                + self.content[max(self.cursor, until) :],
                min(until, self.cursor),
            )
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
        self.delete(len(self.content))

    @bindings.add("KEY_DC", "C-d")
    def delete_next_char(self):
        self.delete(self.cursor + 1)

    @bindings.add("M-KEY_DC", "M-d", "C-<delete>")
    def delete_next_word(self):
        self.delete(self.next_word())

    @bindings.add("KEY_BACKSPACE")
    def delete_prev_char(self):
        self.delete(self.cursor - 1)

    @bindings.add("M-KEY_BACKSPACE", "C-<backspace>")
    def delete_prev_word(self):
        self.delete(self.prev_word())

    @bindings.add("KEY_RIGHT", "C-f")
    def forward_char(self):
        self.set_cursor(self.cursor + 1)

    @bindings.add("M-KEY_RIGHT", "C-<right>", "M-<right>", "M-f")
    def forward_word(self):
        self.set_cursor(self.next_word())

    @bindings.add("KEY_LEFT", "C-b")
    def backward_char(self):
        self.set_cursor(max(self.cursor - 1, 0))

    @bindings.add("M-KEY_LEFT", "C-<left>", "M-<left>", "M-b")
    def backward_word(self):
        self.set_cursor(self.prev_word())

    @bindings.add("KEY_END", "C-e")
    def end(self):
        self.set_cursor(len(self.content))

    @bindings.add("KEY_HOME", "C-a")
    def home(self):
        self.set_cursor(0)

    @override
    def handle_key(self, key: KeyPress) -> Iterable[Event]:
        match self.bindings.handle_key(key, self):
            case None:
                return ()
            case KeyPress(key_str) if (
                len(key_str) == 1 and key_str not in "\n" and key_str.isprintable()
            ):
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
        if self.cursor < self.window.content_base.x:
            self.window.content_base = Point(0, self.cursor)
        if self.cursor >= self.window.content_base.x + self.window.width:
            self.window.content_base = Point(0, self.cursor - self.window.width + 1)
        if len(self.content) < self.window.content_base.x + self.window.width:
            self.window.content_base = Point(
                0, max(0, len(self.content) - self.window.width + 1)
            )

    @override
    def draw(self):
        self.window.insstr(Point(0, 0), self.content)
        if self.active:
            self.window.chgat(Point(0, self.cursor), 1, curses.A_REVERSE)

    def update(self, state: str | TextEditPanelState):
        if isinstance(state, str):
            state = TextEditPanelState(state, len(state))
        self.history.push(self.state)
        self.set_state(state)
        self.history.push(self.state)

    @property
    def state(self):
        return TextEditPanelState(self.content, self.cursor)

    def set_state(self, state: TextEditPanelState):
        self.content = state.content
        self.set_cursor(state.cursor)
