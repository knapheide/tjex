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
from contextlib import ExitStack
from dataclasses import dataclass, replace
from multiprocessing import set_start_method
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Callable

import argcomplete

from tjex import curses_helper, logging
from tjex.config import config as loaded_config
from tjex.config import load as load_config
from tjex.curses_helper import (
    DummyRegion,
    KeyReader,
    Region,
    SubRegion,
    WindowRegion,
    setup_plain_colors,
)
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
from tjex.panel import Event, KeyBindings, KeyPress, StatusUpdate
from tjex.point import Point
from tjex.table_panel import TablePanel, TableState
from tjex.text_panel import TextEditPanel, TextPanel
from tjex.utils import TjexError


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


def tjex(
    screen: Region,
    key_reader: Callable[[], str | None],
    screen_erase: Callable[[], None],
    screen_refresh: Callable[[], None],
    file: list[Path],
    command: str,
    config: Path,
    max_cell_width: int | None,
    slurp: bool,
) -> int:
    table = TablePanel[TableKey, TableCell](screen)
    prompt_head = TextEditPanel("> ")
    prompt = TextEditPanel(command)
    status = TextPanel("")
    status_detail_region = SubRegion(DummyRegion(), Point.ZERO, Point.ZERO)
    status_detail = TextPanel("", clear_first=True)
    status_detail.attr = curses.A_DIM
    panels = [table, prompt_head, prompt, status, status_detail]

    def resize(status_detail_height: None | int = None):
        nonlocal status_detail_region
        status_height = 1
        screen.resize()
        size = screen.size
        table.resize(SubRegion(screen, Point(0, 0), size - Point(3, 0)))
        prompt_head.resize(
            SubRegion(screen, Point(size.y - status_height - 1, 0), Point(1, 2))
        )
        prompt.resize(
            SubRegion(
                screen,
                Point(size.y - status_height - 1, 2),
                Point(1, size.x - 2),
            )
        )
        status.resize(
            SubRegion(
                screen,
                Point(size.y - status_height, 0),
                Point(status_height, size.x),
            )
        )
        if status_detail_height is None:
            status_detail_height = status_detail_region.height
        status_detail_region = SubRegion(
            screen,
            Point(size.y - status_height - 1 - status_detail_height, 0),
            Point(status_detail_height, size.x),
        )
        status_detail.resize(status_detail_region)

    jq = Jq(file, slurp)

    current_command: str = command
    table_cursor_history: dict[str, TableState] = {}

    def set_status(msg: str):
        logger.debug(msg)
        lines = msg.splitlines()
        status.content = "\n".join(lines[:1])
        if len(lines) <= 1:
            resize(status_detail_height=0)
            status_detail.content = ""
        else:
            resize(status_detail_height=len(lines))
            status_detail.content = "\n".join(lines)

    def update_jq_status(block: bool = False):
        nonlocal current_command
        match jq.status(block):
            case JqResult(msg, content):
                if msg == "...":
                    # If result is pending, don't clear previous error message
                    status.content = msg
                else:
                    set_status(msg)
                if content is not None and jq.command is not None:
                    table_cursor_history[current_command] = table.state
                    current_command = jq.command
                    table.update(content, table_cursor_history.get(current_command))
                return True
            case _:
                return False

    bindings: KeyBindings[None, Event | None] = KeyBindings()

    @bindings.add("C-g", "C-d")
    def quit(_: None):  # pyright: ignore[reportUnusedFunction]
        return Quit()

    @bindings.add("M-o", "C-o")
    def toggle_active(_: None):  # pyright: ignore[reportUnusedFunction]
        """Toggle active panel between prompt and table"""
        if active_cycle[0] == prompt:
            update_jq_status(block=True)  # pyright: ignore[reportUnusedCallResult]
        if active_cycle[0] != prompt or jq.latest_status.table is not None:
            active_cycle.append(active_cycle.pop(0))
            active_cycle[-1].set_active(False)
            active_cycle[0].set_active(True)

    _ = bindings.add("C-_", "ESC", name="undo")(lambda _: prompt.undo())
    _ = bindings.add("M-_", name="redo")(lambda _: prompt.redo())

    @bindings.add("M-\n")
    def add_to_history(_: None):  # pyright: ignore[reportUnusedFunction]
        """Append tjex call with current command to shell's history"""
        return append_history(prompt.content)

    @bindings.add("g", "\n")
    def reload(_: None):  # pyright: ignore[reportUnusedFunction]
        """Re-run the current filter."""
        jq.update(prompt.content, force=True)

    @table.bindings.add("M-w")
    def copy_content(_: Any):  # pyright: ignore[reportUnusedFunction]
        """Copy output of current command to clipboard"""
        loaded_config.do_copy(json.dumps(jq.run_plain()))
        return StatusUpdate("Copied.")

    @table.bindings.add("\n")
    def enter_cell(_: Any):  # pyright: ignore[reportUnusedFunction]
        """Enter highlighted cell by appending selector to jq prompt"""
        prompt.update(
            append_selector(prompt.content, keys_to_selector(*table.cell_keys))
        )

    @table.bindings.add("M-\n")
    def enter_row(_: Any):  # pyright: ignore[reportUnusedFunction]
        """Enter highlighted cell's row by appending selector to jq prompt"""
        prompt.update(append_selector(prompt.content, keys_to_selector(table.row_key)))

    @table.bindings.add("w")
    def copy_cell_content(_: Any):  # pyright: ignore[reportUnusedFunction]
        """Copy content of the current cell to clipboard.
        If content is a string, copy the plain value, not the json representation.
        """
        content = jq.run_plain(
            append_selector(jq.command or ".", keys_to_selector(*table.cell_keys) or "")
        )
        if isinstance(content, str):
            loaded_config.do_copy(content)
        else:
            loaded_config.do_copy(json.dumps(content))
        return StatusUpdate("Copied.")

    def prompt_append(command: str, cursor: TableState | None = None):
        new_prompt = append_filter(prompt.content, command)
        if cursor is not None:
            table_cursor_history[new_prompt] = cursor
        prompt.update(new_prompt)

    @table.bindings.add("E")
    def expand_row(_: Any):  # pyright: ignore[reportUnusedFunction]
        """Expand the selected row"""
        key = table.row_key
        if key == Undefined():
            raise TjexError("Not an array or object")
        prompt_append(f"expand({json.dumps(key)})", table.state)

    @table.bindings.add("e")
    def expand_col(_: Any):  # pyright: ignore[reportUnusedFunction]
        """Expand the selected column"""
        key = table.col_key
        if key == Undefined():
            raise TjexError("Not an array or object")
        prompt_append(f"map_values(expand({json.dumps(key)}))", table.state)

    @table.bindings.add("K")
    def delete_row(_: Any):  # pyright: ignore[reportUnusedFunction]
        """Delete the selected row"""
        key = table.row_key
        if key == Undefined():
            raise TjexError("Not an array or object")
        prompt_append(f"del({standalone_selector(key_to_selector(key))})", table.state)

    @table.bindings.add("k")
    def delete_col(_: Any):  # pyright: ignore[reportUnusedFunction]
        """Delete the selected column"""
        key = table.col_key
        if key == Undefined():
            raise TjexError("Not an array or object")
        prompt_append(
            f"map_values(del({standalone_selector(key_to_selector(key))}))", table.state
        )

    @table.bindings.add("m")
    def select_col(_: Any):  # pyright: ignore[reportUnusedFunction]
        """Enter the selected column"""
        key = table.col_key
        if key == Undefined():
            raise TjexError("Not an array or object")
        prompt_append(
            f"map_values({standalone_selector(key_to_selector(key))})",
            table.state.row_only,
        )

    @table.bindings.add("s")
    def sort_by_col(_: Any):  # pyright: ignore[reportUnusedFunction]
        """Sort rows by the selected column.
        Works only for arrays right now.
        """
        if not isinstance(table.row_key, int):
            raise TjexError("Not an array")
        key = table.col_key
        if key == Undefined():
            prompt.update(append_filter(prompt.content, f"sort"))
        else:
            prompt_append(
                f"sort_by({standalone_selector(key_to_selector(key))})",
                table.state.col_only,
            )

    load_config(
        config, {"global": bindings, "prompt": prompt.bindings, "table": table.bindings}
    )
    if max_cell_width:
        loaded_config.max_cell_width = max_cell_width

    resize()
    active_cycle = [table, prompt]
    if loaded_config.start_at_prompt:
        active_cycle = [prompt, table]
    active_cycle[0].set_active(True)
    jq.update(prompt.content)

    redraw = True

    while True:
        if (key := key_reader()) is not None:
            try:
                for event in active_cycle[0].handle_key(KeyPress(key)):
                    match bindings.handle_key(event, None):
                        case Quit():
                            return 0
                        case StatusUpdate(msg):
                            set_status(msg)
                        case KeyPress("KEY_RESIZE"):
                            resize()
                        case _:
                            pass
            except TjexError as e:
                set_status(e.msg)
            jq.update(prompt.content)
            redraw = True
            continue

        if update_jq_status() or redraw:
            screen_erase()
            for panel in panels:
                panel.draw()
            screen_refresh()
            redraw = False
            continue

        time.sleep(0.01)


def main():
    set_start_method("forkserver")
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("file", type=Path, nargs="*")
    _ = parser.add_argument("-c", "--command", default="")
    _ = parser.add_argument(
        "--config", type=Path, default=Path.home() / ".config" / "tjex" / "config.toml"
    )
    _ = parser.add_argument("--logfile", type=Path)
    _ = parser.add_argument("-w", "--max-cell-width", type=int)
    _ = parser.add_argument("-s", "--slurp", action="store_true")
    argcomplete.autocomplete(parser)
    args = parser.parse_args()
    logging.setup(args.logfile)

    with ExitStack() as stack:

        def tmpfile(s: str):
            buffered = stack.enter_context(
                NamedTemporaryFile(mode="w", delete_on_close=False, delete=True)
            )
            _ = buffered.write(s)
            buffered.close()
            return Path(buffered.name)

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
            return tjex(
                WindowRegion(scr),
                KeyReader(scr).get,
                scr.erase,
                scr.refresh,
                **{n: k for n, k in vars(args).items() if n not in {"logfile"}},
            )

    return result


if __name__ == "__main__":
    exit(main())
