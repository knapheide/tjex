from __future__ import annotations

import importlib.resources
import json
import re
import shutil
import subprocess as sp
from dataclasses import dataclass
from multiprocessing import Process, Queue, get_start_method
from pathlib import Path
from queue import Empty
from threading import Thread
from typing import cast

from tjex.config import config
from tjex.json_table import Json, TableCell, TableKey, Undefined, json_to_table
from tjex.table import Table
from tjex.utils import TjexError


@dataclass
class JqResult:
    message: str
    table: Table[TableKey, TableCell] | None


class JqError(TjexError):
    pass


identifier_pattern = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")


def key_to_selector(key: TableKey):
    match key:
        case Undefined():
            return ""
        case str() if identifier_pattern.fullmatch(key):
            return f".{key}"
        case _:
            return f"[{json.dumps(key, ensure_ascii=False)}]"


def keys_to_selector(*keys: TableKey):
    return "".join(key_to_selector(key) for key in keys)


selector_pattern = re.compile(
    r"""\s*(\.\[("[^\]"\\]*"|\d+)\]|.[a-zA-Z_][a-zA-Z0-9_]*)"""
    + r"""(\.?\[("[^\]"\\]*"|\d+)\]|.[a-zA-Z_][a-zA-Z0-9_]*)*\s*"""
)


def append_filter(command: str, filter: str):
    if command == "":
        return filter
    return command + " | " + filter


def standalone_selector(selector: str):
    return ("" if selector.startswith(".") else ".") + selector


def append_selector(command: str, selector: str):
    if command == "":
        return standalone_selector(selector)
    if selector_pattern.fullmatch(command.split("|")[-1]):
        return command + selector
    return command + " | " + standalone_selector(selector)


def run(command: list[str], inputs: list[Path]):
    p = sp.Popen(
        command,
        stdin=sp.PIPE,
        stdout=sp.PIPE,
        stderr=sp.PIPE,
        text=True,
    )

    feed_exception = cast(Exception | None, None)

    def feed():
        nonlocal feed_exception
        assert p.stdin is not None
        try:
            for file in inputs:
                with open(file) as f:
                    try:
                        shutil.copyfileobj(f, p.stdin)
                    except OSError:
                        # The OSError was probably just because the jq process died.
                        return
        except Exception as e:
            feed_exception = e
        finally:
            p.stdin.close()

    feed_thread = Thread(target=feed, daemon=True)
    feed_thread.start()

    json_exception = None
    assert p.stdout is not None
    data: Json = None
    try:
        data = json.load(p.stdout)
    except Exception as e:
        json_exception = e
    assert p.stderr is not None
    stderr = p.stderr.read()
    _ = p.wait()
    feed_thread.join()
    if isinstance(feed_exception, OSError):
        raise feed_exception
    if p.returncode != 0:
        raise JqError(stderr)
    if json_exception is not None:
        raise json_exception
    if feed_exception is not None:
        raise feed_exception
    return data


class Jq:
    command: str | None = None
    result: Queue[JqResult] | None = None
    process: Process | None = None
    latest_status: JqResult = JqResult("...", None)

    def __init__(self, file: list[Path], slurp: bool):
        # The default start_method "fork" breaks curses
        assert get_start_method() == "forkserver"
        self.file: list[Path] = file
        self.extra_args: list[str] = ["--slurp"] if slurp or len(file) > 1 else []
        self.prelude: str = importlib.resources.read_text(
            "tjex.resources", "builtins.jq"
        )

    @staticmethod
    def run(command: list[str], inputs: list[Path], result: Queue[JqResult]):
        try:
            data = run(command, inputs)
            if data is None:
                result.put(JqResult("null", None))
            else:
                result.put(JqResult("", json_to_table(data)))
        except BaseException as e:
            result.put(JqResult(str(e), None))

    def update(self, command: str, force: bool = False):
        if force or command != self.command:
            if self.process is not None:
                self.process.terminate()
                self.process.join()
                self.process.close()
            if self.result is not None:
                self.result.close()
            self.result = Queue()

            self.process = Process(
                target=self.run,
                args=(
                    [
                        config.jq_command,
                        *self.extra_args,
                        self.prelude + (command or "."),
                    ],
                    self.file,
                    self.result,
                ),
            )
            self.process.start()
            self.command = command

    def status(self, block: bool = False, timeout: float = 2) -> JqResult | None:
        if self.result is None:
            return None
        try:
            self.latest_status = self.result.get(block, timeout)
            if self.process is not None:
                self.process.join()
                self.process.close()
                self.process = None
            self.result.close()
            self.result = None
        except Empty:
            self.latest_status = JqResult("...", None)
        return self.latest_status

    def run_plain(self, command: str | None = None) -> Json:
        if command is None:
            command = self.command
        return run(
            [
                config.jq_command,
                *self.extra_args,
                self.prelude + (command or "."),
            ],
            self.file,
        )
