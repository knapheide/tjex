from __future__ import annotations

import json
import subprocess as sp
from dataclasses import dataclass
from multiprocessing import Process, Queue, get_start_method
from pathlib import Path
from queue import Empty

from tjex.table_panel import Json, TableContent, to_table_content
from tjex.utils import TjexError


@dataclass
class JqResult:
    message: str
    content: TableContent | None


class JqError(TjexError):
    pass


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
                    result.put(JqResult("", to_table_content(data)))
            else:
                result.put(JqResult(res.stderr.decode("utf8"), None))
        except BaseException as e:
            result.put(JqResult(str(e), None))

    def update(self, command: str):
        if command != self.command:
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
                    ["jq", *self.extra_args, command or ".", *self.file],
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
            ["jq", *self.extra_args, command or ".", *self.file],
            capture_output=True,
        )
        if res.returncode != 0:
            raise JqError(res.stderr.decode("utf8"))
        return json.loads(res.stdout.decode("utf8"))
