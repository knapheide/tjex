# PYTHON_ARGCOMPLETE_OK
from __future__ import annotations

import argparse
import curses
import json
import os
import re
import shlex
import subprocess as sp
import sys
import time
from contextlib import ExitStack
from dataclasses import dataclass
from multiprocessing import set_start_method
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import argcomplete

from tjex import logging
from tjex.config import config as loaded_config
from tjex.config import load as load_config
from tjex.curses_helper import KeyReader, WindowRegion, setup_plain_colors
from tjex.jq import Jq, JqResult
from tjex.logging import logger
from tjex.panel import Event, KeyBindings, KeyPress, StatusUpdate
from tjex.point import Point
from tjex.table_panel import TablePanel, TableState, Undefined, key_to_selector
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


selector_pattern = re.compile(
    r"""\s*(\.\[("[^\]"\\]*"|\d+)\]|.[a-zA-Z_][a-zA-Z0-9_]*)"""
    + r"""(\.?\[("[^\]"\\]*"|\d+)\]|.[a-zA-Z_][a-zA-Z0-9_]*)*\s*"""
)


def append_filter(command: str, filter: str):
    if command == "":
        return filter
    return command + " | " + filter


def append_selector(command: str, selector: str):
    standalone_selector = ("" if selector.startswith(".") else ".") + selector
    if command == "":
        return standalone_selector
    if selector_pattern.fullmatch(command.split("|")[-1]):
        return command + selector
    return command + " | " + standalone_selector


@dataclass
class Quit(Event):
    pass


def tjex(
    stdscr: curses.window,
    file: list[Path],
    command: str,
    config: Path,
    max_cell_width: int | None,
    slurp: bool,
) -> int:
    curses.curs_set(0)  # pyright: ignore[reportUnusedCallResult]
    setup_plain_colors()

    table = TablePanel(WindowRegion(stdscr))
    prompt_head = TextEditPanel(
        WindowRegion(stdscr),
        "> ",
    )
    prompt = TextEditPanel(
        WindowRegion(
            stdscr,
        ),
        command,
    )
    status = TextPanel(
        WindowRegion(
            stdscr,
        ),
        "",
    )
    panels = [table, prompt_head, prompt, status]

    def resize():
        status_height = 2
        screen_size = Point(*stdscr.getmaxyx())
        table.window.pos = Point(0, 0)
        table.window.size = screen_size - Point(3, 0)
        prompt_head.window.pos = Point(screen_size.y - status_height - 1, 0)
        prompt_head.window.size = Point(1, 2)
        prompt.window.pos = Point(screen_size.y - status_height - 1, 2)
        prompt.window.size = Point(1, screen_size.x - 2)
        status.window.pos = Point(screen_size.y - status_height, 0)
        status.window.size = Point(status_height, screen_size.x)
        for panel in panels:
            panel.resize()

    jq = Jq(file, slurp)
    key_reader = KeyReader(stdscr)

    current_command: str = command
    table_cursor_history: dict[str, TableState] = {}

    def update_status(block: bool = False):
        nonlocal current_command
        match jq.status(block):
            case JqResult(msg, content):
                status.content = msg
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
            update_status(block=True)  # pyright: ignore[reportUnusedCallResult]
        if active_cycle[0] != prompt or jq.latest_status.content is not None:
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
        try:
            loaded_config.do_copy(json.dumps(jq.run_plain()))
            status.content = "Copied."
        except TjexError as e:
            status.content = e.msg

    @table.bindings.add("w")
    def copy_cell_content(_: Any):  # pyright: ignore[reportUnusedFunction]
        """Copy content of the current cell to clipboard.
        If content is a string, copy the plain value, not the json representation.
        """
        try:
            content = jq.run_plain(
                append_selector(jq.command or ".", table.cell_selector or "")
            )
            if isinstance(content, str):
                loaded_config.do_copy(content)
            else:
                loaded_config.do_copy(json.dumps(content))
            status.content = "Copied."
        except TjexError as e:
            status.content = e.msg

    @table.bindings.add("E")
    def expand_row(_: Any):  # pyright: ignore[reportUnusedFunction]
        """Expand the selected row"""
        key = table.row_key
        if key == Undefined():
            status.content = "Not an array or object"
            return
        prompt.update(append_filter(prompt.content, f"expand({json.dumps(key)})"))

    @table.bindings.add("e")
    def expand_col(_: Any):  # pyright: ignore[reportUnusedFunction]
        """Expand the selected column"""
        key = table.col_key
        if key == Undefined():
            status.content = "Not an array or object"
            return
        prompt.update(
            append_filter(prompt.content, f"map_values(expand({json.dumps(key)}))")
        )

    @table.bindings.add("K")
    def delete_row(_: Any):  # pyright: ignore[reportUnusedFunction]
        """Delete the selected row"""
        key = table.row_key
        if key == Undefined():
            status.content = "Not an array or object"
            return
        prompt.update(append_filter(prompt.content, f"del({key_to_selector(key)})"))

    @table.bindings.add("k")
    def delete_col(_: Any):  # pyright: ignore[reportUnusedFunction]
        """Delete the selected column"""
        key = table.col_key
        if key == Undefined():
            status.content = "Not an array or object"
            return
        prompt.update(
            append_filter(prompt.content, f"map_values(del({key_to_selector(key)}))")
        )

    @table.bindings.add("m")
    def select_col(_: Any):  # pyright: ignore[reportUnusedFunction]
        """Enter the selected column"""
        key = table.col_key
        if key == Undefined():
            status.content = "Not an array or object"
            return
        prompt.update(
            append_filter(prompt.content, f"map_values({key_to_selector(key)})")
        )

    @table.bindings.add("s")
    def sort_by_col(_: Any):  # pyright: ignore[reportUnusedFunction]
        """Sort rows by the selected column.
        Works only for arrays right now.
        """
        if not isinstance(table.row_key, int):
            status.content = "Not an array"
            return
        key = table.col_key
        if key == Undefined():
            prompt.update(append_filter(prompt.content, f"sort"))
        else:
            prompt.update(
                append_filter(prompt.content, f"sort_by({key_to_selector(key)})")
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
        if (key := key_reader.get()) is not None:
            for event in active_cycle[0].handle_key(KeyPress(key)):
                match bindings.handle_key(event, None):
                    case Quit():
                        return 0
                    case TablePanel.Select(selector):
                        prompt.update(append_selector(prompt.content, selector))
                    case StatusUpdate(msg):
                        status.content = msg
                    case KeyPress("KEY_RESIZE"):
                        resize()
                    case _:
                        pass
            jq.update(prompt.content)
            redraw = True
            continue

        if update_status() or redraw:
            stdscr.erase()
            for panel in panels:
                panel.draw()
            stdscr.refresh()
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
        result = curses.wrapper(
            tjex,
            **{n: k for n, k in vars(args).items() if n not in {"logfile"}},
        )
    return result


if __name__ == "__main__":
    exit(main())
