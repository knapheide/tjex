# PYTHON_ARGCOMPLETE_OK
from __future__ import annotations

import argparse
import curses
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
from tjex.curses_helper import KeyReader, WindowRegion, setup_plain_colors
from tjex.jq import Jq, JqResult
from tjex.logging import logger
from tjex.panel import Event, KeyBindings, KeyPress, StatusUpdate
from tjex.point import Point
from tjex.table_panel import TablePanel, TableState
from tjex.text_panel import TextEditPanel, TextPanel, osc52copy


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
            f"atuin history end --exit 0 -- $(atuin history start -- {shlex.quote(cmd_str)})",
        ],
        capture_output=True,
    )
    logger.debug(f"{result.stdout=} {result.stderr=}")
    if result.returncode:
        return StatusUpdate(result.stderr.decode("utf8"))
    return StatusUpdate("Added to atuin history.")


selector_pattern = re.compile(
    r"""\s*(\.\[("[^\]"\\]*"|\d+)\]|.[a-zA-Z_][a-zA-Z0-9_]*)*\s*"""
)


def append_selector(command: str, selector: str):
    if command == "":
        return selector
    if selector_pattern.fullmatch(command.split("|")[-1]):
        return command + selector
    return command + " | " + selector


@dataclass
class Quit(Event):
    pass


def tjex(
    stdscr: curses.window,
    file: list[Path],
    command: str,
    max_cell_width: int,
    slurp: bool,
    **_,
) -> int:
    curses.curs_set(0)  # pyright: ignore[reportUnusedCallResult]
    setup_plain_colors()

    table = TablePanel(WindowRegion(stdscr), max_cell_width)
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
        screen_size = Point(*stdscr.getmaxyx())
        table.window.pos = Point(0, 0)
        table.window.size = screen_size - Point(3, 0)
        prompt_head.window.pos = Point(screen_size.y - 3, 0)
        prompt_head.window.size = Point(1, 2)
        prompt.window.pos = Point(screen_size.y - 3, 2)
        prompt.window.size = Point(1, screen_size.x - 2)
        status.window.pos = Point(screen_size.y - 2, 0)
        status.window.size = Point(2, screen_size.x)
        for panel in panels:
            panel.resize()

    resize()

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

    active_cycle = [prompt, table]
    prompt.set_active(True)
    jq.update(prompt.content)

    bindings: KeyBindings[None, Event | None] = KeyBindings()

    @bindings.add("\x07", "\x04")  # C-g, C-d
    def quit(_: None):  # pyright: ignore[reportUnusedFunction]
        return Quit()

    @bindings.add("M-o", "\x0f")  # C-o
    def toggle_active(_: None):  # pyright: ignore[reportUnusedFunction]
        if active_cycle[0] == prompt:
            update_status(block=True)  # pyright: ignore[reportUnusedCallResult]
        if active_cycle[0] != prompt or jq.latest_status.content is not None:
            active_cycle.append(active_cycle.pop(0))
            active_cycle[-1].set_active(False)
            active_cycle[0].set_active(True)

    _ = bindings.add("\x1f", "ESC")(lambda _: prompt.undo())  # C-_
    _ = bindings.add("M-_")(lambda _: prompt.redo())

    @bindings.add("M-\n")
    def add_to_history(_: None):  # pyright: ignore[reportUnusedFunction]
        return append_history(prompt.content)

    @table.bindings.add("M-w")
    def copy_content(_: Any):  # pyright: ignore[reportUnusedFunction]
        osc52copy(jq.run_plain())

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
    _ = parser.add_argument("--logfile", type=Path)
    _ = parser.add_argument("-w", "--max-cell-width", type=int, default=50)
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
            tjex,  # pyright: ignore[reportUnknownArgumentType]
            **vars(args),
        )
    return result


if __name__ == "__main__":
    exit(main())
