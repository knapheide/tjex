from __future__ import annotations

import importlib.resources
import json
import re
import subprocess as sp
from dataclasses import dataclass
from multiprocessing import Process, Queue, get_start_method
from pathlib import Path
from queue import Empty

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
            return f"[{json.dumps(key)}]"


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
    def run(command: list[str], result: Queue[JqResult]):
        try:
            res = sp.run(
                command,
                capture_output=True,
            )
            if res.returncode == 0:
                data: Json = json.loads(res.stdout.decode("utf8"))
                if data is None:
                    result.put(JqResult("null", None))
                else:
                    result.put(JqResult("", json_to_table(data)))
            else:
                result.put(JqResult(res.stderr.decode("utf8"), None))
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
                        *self.file,
                    ],
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
        res = sp.run(
            [
                config.jq_command,
                *self.extra_args,
                self.prelude + (command or "."),
                *self.file,
            ],
            capture_output=True,
        )
        if res.returncode != 0:
            raise JqError(res.stderr.decode("utf8"))
        return json.loads(res.stdout.decode("utf8"))
