# PYTHON_ARGCOMPLETE_OK
from __future__ import annotations

import argparse
import curses
import json
import os
import shlex
import subprocess as sp
import sys
import time
from dataclasses import dataclass
from importlib.metadata import version
from multiprocessing import set_start_method
from pathlib import Path
from typing import Any, Callable

import argcomplete

from tjex import curses_helper, logging
from tjex.config import config as loaded_config
from tjex.config import load_config_file, make_bindings_table
from tjex.curses_helper import DummyRegion, KeyReader, Region, SubRegion, WindowRegion
from tjex.jq import (
    Jq,
    JqResult,
    append_filter,
    append_selector,
    key_to_selector,
    keys_to_selector,
    standalone_selector,
)
from tjex.json_table import TableCell, TableKey, Undefined
from tjex.logging import logger
from tjex.panel import Event, KeyBindings, KeyPress, Panel, StatusUpdate
from tjex.point import Point
from tjex.table_panel import TablePanel, TableState
from tjex.text_panel import TextEditPanel, TextPanel
from tjex.utils import TjexError, TmpFiles


def append_history(jq_cmd: str) -> StatusUpdate:
    skip = False
    cmd: list[str] = ["tjex"]
    for arg in sys.argv[1:]:
        if skip:
            skip = False
        else:
            if arg in {"-c", "--command"}:
                skip = True
            elif arg.startswith("-c") or arg.startswith("--command"):
                pass
            else:
                cmd.append(arg)
    cmd += ["--command", jq_cmd]
    cmd_str = " ".join(shlex.quote(arg) for arg in cmd)

    logger.debug(f"Trying to add to atuin history: {cmd_str}")
    result = sp.run(
        [
            "bash",
            "-c",
            loaded_config.append_history_command.format(shlex.quote(cmd_str)),
        ],
        capture_output=True,
    )
    if result.returncode:
        return StatusUpdate(result.stderr.decode("utf8"))
    return StatusUpdate("Added to atuin history.")


@dataclass
class Quit(Event):
    pass


class Tjex:
    def __init__(
        self,
        screen: Region,
        file: list[Path],
        command: str,
        slurp: bool,
    ):
        self.screen: Region = screen
        self.table: TablePanel[TableKey, TableCell] = TablePanel[TableKey, TableCell](
            screen
        )
        self.prompt_head: TextEditPanel = TextEditPanel("> ")
        self.prompt: TextEditPanel = TextEditPanel(command)
        self.status: TextPanel = TextPanel("")
        self.status_detail_region: SubRegion = SubRegion(
            DummyRegion(), Point.ZERO, Point.ZERO
        )
        self.status_detail: TextPanel = TextPanel("", clear_first=True)
        self.status_detail.attr = curses.A_DIM
        self.panels: list[Panel] = [
            self.table,
            self.prompt_head,
            self.prompt,
            self.status,
            self.status_detail,
        ]

        self.active_cycle: list[Panel] = [self.table, self.prompt]

        self.jq: Jq = Jq(file, slurp)

        self.current_command: str = command
        self.table_cursor_history: dict[str, TableState] = {}

        self.bindings: KeyBindings[None, Event | None] = KeyBindings()

        @self.bindings.add("C-g", "C-d")
        def quit(_: None):  # pyright: ignore[reportUnusedFunction]
            return Quit()

        @self.bindings.add("M-o", "C-o")
        def toggle_active(_: None):  # pyright: ignore[reportUnusedFunction]
            """Toggle active panel between prompt and table"""
            if self.active_cycle[0] == self.prompt:
                self.update_jq_status(
                    block=True
                )  # pyright: ignore[reportUnusedCallResult]
            if (
                self.active_cycle[0] != self.prompt
                or self.jq.latest_status.table is not None
            ):
                self.active_cycle.append(self.active_cycle.pop(0))
                self.active_cycle[-1].set_active(False)
                self.active_cycle[0].set_active(True)

        _ = self.bindings.add("C-_", "ESC", name="undo")(lambda _: self.prompt.undo())
        _ = self.bindings.add("M-_", name="redo")(lambda _: self.prompt.redo())

        @self.bindings.add("M-\n")
        def add_to_history(_: None):  # pyright: ignore[reportUnusedFunction]
            """Append tjex call with current command to shell's history"""
            return append_history(self.prompt.content)

        @self.bindings.add("g", "\n")
        def reload(_: None):  # pyright: ignore[reportUnusedFunction]
            """Re-run the current filter."""
            self.jq.update(self.prompt.content, force=True)

        @self.table.bindings.add("M-w")
        def copy_content(_: Any):  # pyright: ignore[reportUnusedFunction]
            """Copy output of current command to clipboard"""
            loaded_config.do_copy(json.dumps(self.jq.run_plain(), ensure_ascii=False))
            return StatusUpdate("Copied.")

        @self.table.bindings.add("\n")
        def enter_cell(_: Any):  # pyright: ignore[reportUnusedFunction]
            """Enter highlighted cell by appending selector to jq prompt"""
            self.prompt.update(
                append_selector(
                    self.prompt.content, keys_to_selector(*self.table.cell_keys)
                )
            )

        @self.table.bindings.add("M-\n")
        def enter_row(_: Any):  # pyright: ignore[reportUnusedFunction]
            """Enter highlighted cell's row by appending selector to jq prompt"""
            self.prompt.update(
                append_selector(
                    self.prompt.content, keys_to_selector(self.table.row_key)
                )
            )

        @self.table.bindings.add("w")
        def copy_cell_content(_: Any):  # pyright: ignore[reportUnusedFunction]
            """Copy content of the current cell to clipboard.
            If content is a string, copy the plain value, not the json representation.
            """
            content = self.jq.run_plain(
                append_selector(
                    self.jq.command or ".",
                    keys_to_selector(*self.table.cell_keys) or "",
                )
            )
            if isinstance(content, str):
                loaded_config.do_copy(content)
            else:
                loaded_config.do_copy(json.dumps(content, ensure_ascii=False))
            return StatusUpdate("Copied.")

        @self.table.bindings.add("E")
        def expand_row(_: Any):  # pyright: ignore[reportUnusedFunction]
            """Expand the selected row"""
            key = self.table.row_key
            if key == Undefined():
                raise TjexError("Not an array or object")
            self.prompt_append(
                f"expand({json.dumps(key, ensure_ascii=False)})", self.table.state
            )

        @self.table.bindings.add("e")
        def expand_col(_: Any):  # pyright: ignore[reportUnusedFunction]
            """Expand the selected column"""
            key = self.table.col_key
            if key == Undefined():
                raise TjexError("Not an array or object")
            self.prompt_append(
                f"map_values(expand({json.dumps(key, ensure_ascii=False)}))",
                self.table.state,
            )

        @self.table.bindings.add("K")
        def delete_row(_: Any):  # pyright: ignore[reportUnusedFunction]
            """Delete the selected row"""
            key = self.table.row_key
            if key == Undefined():
                raise TjexError("Not an array or object")
            self.prompt_append(
                f"del({standalone_selector(key_to_selector(key))})", self.table.state
            )

        @self.table.bindings.add("k")
        def delete_col(_: Any):  # pyright: ignore[reportUnusedFunction]
            """Delete the selected column"""
            key = self.table.col_key
            if key == Undefined():
                raise TjexError("Not an array or object")
            self.prompt_append(
                f"map_values(del({standalone_selector(key_to_selector(key))}))",
                self.table.state,
            )

        @self.table.bindings.add("m")
        def select_col(_: Any):  # pyright: ignore[reportUnusedFunction]
            """Enter the selected column"""
            key = self.table.col_key
            if key == Undefined():
                raise TjexError("Not an array or object")
            self.prompt_append(
                f"map_values({standalone_selector(key_to_selector(key))})",
                self.table.state.row_only,
            )

        @self.table.bindings.add("s")
        def sort_by_col(_: Any):  # pyright: ignore[reportUnusedFunction]
            """Sort rows by the selected column.
            Works only for arrays right now.
            """
            if not isinstance(self.table.row_key, int):
                raise TjexError("Not an array")
            key = self.table.col_key
            if key == Undefined():
                self.prompt.update(append_filter(self.prompt.content, f"sort"))
            else:
                self.prompt_append(
                    f"sort_by({standalone_selector(key_to_selector(key))})",
                    self.table.state.col_only,
                )

    def bindings_list(self):
        return {
            "global": self.bindings,
            "prompt": self.prompt.bindings,
            "table": self.table.bindings,
        }

    def make_hotkey_table(self):
        return make_bindings_table(
            {
                "Global": self.bindings,
                "In Prompt": self.prompt.bindings,
                "In Table": self.table.bindings,
            }
        )

    def resize(self, status_detail_height: None | int = None):
        status_height = 1
        self.screen.resize()
        size = self.screen.size
        self.table.resize(SubRegion(self.screen, Point(0, 0), size - Point(3, 0)))
        self.prompt_head.resize(
            SubRegion(self.screen, Point(size.y - status_height - 1, 0), Point(1, 2))
        )
        self.prompt.resize(
            SubRegion(
                self.screen,
                Point(size.y - status_height - 1, 2),
                Point(1, size.x - 2),
            )
        )
        self.status.resize(
            SubRegion(
                self.screen,
                Point(size.y - status_height, 0),
                Point(status_height, size.x),
            )
        )
        if status_detail_height is None:
            status_detail_height = self.status_detail_region.height
        status_detail_region = SubRegion(
            self.screen,
            Point(size.y - status_height - 1 - status_detail_height, 0),
            Point(status_detail_height, size.x),
        )
        self.status_detail.resize(status_detail_region)

    def set_status(self, msg: str):
        logger.debug(msg)
        lines = msg.splitlines()
        self.status.content = "\n".join(lines[:1])
        if len(lines) <= 1:
            self.resize(status_detail_height=0)
            self.status_detail.content = ""
        else:
            self.resize(status_detail_height=len(lines))
            self.status_detail.content = "\n".join(lines)

    def update_jq_status(self, block: bool = False):
        match self.jq.status(block):
            case JqResult(msg, content):
                if msg == "...":
                    # If result is pending, don't clear previous error message
                    self.status.content = msg
                else:
                    self.set_status(msg)
                if content is not None and self.jq.command is not None:
                    self.table_cursor_history[self.current_command] = self.table.state
                    self.current_command = self.jq.command
                    self.table.update(
                        content, self.table_cursor_history.get(self.current_command)
                    )
                return True
            case _:
                return False

    def prompt_append(self, command: str, cursor: TableState | None = None):
        new_prompt = append_filter(self.prompt.content, command)
        if cursor is not None:
            self.table_cursor_history[new_prompt] = cursor
        self.prompt.update(new_prompt)

    def run(
        self,
        key_reader: Callable[[], str | None],
        screen_erase: Callable[[], None],
        screen_refresh: Callable[[], None],
    ) -> int:
        self.resize()
        self.active_cycle = [self.table, self.prompt]
        if loaded_config.start_at_prompt:
            self.active_cycle = [self.prompt, self.table]
        self.active_cycle[0].set_active(True)
        self.jq.update(self.prompt.content)

        redraw = True

        while True:
            if (key := key_reader()) is not None:
                try:
                    for event in self.active_cycle[0].handle_key(KeyPress(key)):
                        match self.bindings.handle_key(event, None):
                            case Quit():
                                return 0
                            case StatusUpdate(msg):
                                self.set_status(msg)
                            case KeyPress("KEY_RESIZE"):
                                self.resize()
                            case _:
                                pass
                except TjexError as e:
                    self.set_status(e.msg)
                self.jq.update(self.prompt.content)
                redraw = True
                continue

            if self.update_jq_status() or redraw:
                screen_erase()
                for panel in self.panels:
                    panel.draw()
                screen_refresh()
                redraw = False
                continue

            time.sleep(0.01)


def main():
    set_start_method("forkserver")
    parser = argparse.ArgumentParser(description="A tabular json explorer.")
    _ = parser.add_argument("--version", action="version", version=version("tjex"))
    _ = parser.add_argument("file", type=Path, nargs="*")
    _ = parser.add_argument("-c", "--command", default="")
    _ = parser.add_argument(
        "--config", type=Path, default=Path.home() / ".config" / "tjex" / "config.toml"
    )
    _ = parser.add_argument("--logfile", type=Path)
    _ = parser.add_argument("-w", "--max-cell-width", type=int)
    _ = parser.add_argument("-s", "--slurp", action="store_true")
    _ = parser.add_argument("-n", "--null-input", action="store_true")
    argcomplete.autocomplete(parser)
    args = parser.parse_args()
    logging.setup(args.logfile)

    with TmpFiles() as tmpfile:
        if args.null_input:
            args.file = [tmpfile("null")]
        if not args.file:
            args.file = [tmpfile(sys.stdin.read())]
            os.close(0)
            sys.stdin = open("/dev/tty")
        for i in range(len(args.file)):
            if not args.file[i].is_file():
                args.file[i] = tmpfile(args.file[i].read_text())

        @curses.wrapper
        def result(scr: curses.window):
            _ = curses.curs_set(0)
            curses_helper.setup_plain_colors()
            tjex_main = Tjex(
                WindowRegion(scr),
                args.file,
                args.command,
                args.slurp,
            )
            load_config_file(args.config, tjex_main.bindings_list())
            if args.max_cell_width:
                loaded_config.max_cell_width = args.max_cell_width
            return tjex_main.run(KeyReader(scr).get, scr.erase, scr.refresh)

    return result


if __name__ == "__main__":
    exit(main())
