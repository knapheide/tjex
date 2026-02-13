import argparse
import curses
import json
import re
import time
from collections.abc import Generator
from multiprocessing import set_start_method
from pathlib import Path
from typing import Literal, NotRequired, TypedDict, cast

import pytest

import tjex.config as tjex_config
from tjex import tjex
from tjex.curses_helper import KEY_ALIASES, DummyRegion
from tjex.json_table import Json
from tjex.point import Point
from tjex.utils import TmpFiles

# Stub out curses functions that might get called
curses.color_pair = lambda _: 0  # pyright: ignore[reportUnknownLambdaType]


class Command(TypedDict):
    op: str


class InputCommand(TypedDict):
    op: Literal["input"]
    key: str


class TypeCommand(TypedDict):
    op: Literal["type"]
    text: str


class SleepCommand(TypedDict):
    op: Literal["sleep"]
    timeout: float


class ExpectCommand(TypedDict):
    op: Literal["expect"]
    timeout: float
    content: NotRequired[list[str]]


class Case(TypedDict):
    description: str
    screen_shape: list[int]
    inputs: list[str | list[Json]]
    commands: list[Command]
    config: NotRequired[list[str]]


def case_name(path: Path):
    return path.stem.removeprefix("integration_")


def case_paths():
    return (Path(__file__).parent / "cases").glob("integration_*.json")


def run_case(path: Path, update: bool):
    with open(path) as f:
        test_case: Case = json.load(f)
    print()
    print(f"Running {case_name(path)}")
    for description_line in test_case["description"].splitlines():
        print("-- " + description_line)

    screen = DummyRegion(Point(*test_case["screen_shape"]))

    def foo() -> Generator[str | None]:
        for command in test_case["commands"]:
            match command["op"]:
                case "input":
                    c = cast(
                        InputCommand, command
                    )  # pyright: ignore[reportInvalidCast]
                    yield KEY_ALIASES.get(c["key"], c["key"])
                case "type":
                    c = cast(TypeCommand, command)  # pyright: ignore[reportInvalidCast]
                    yield from c["text"]
                case "sleep":
                    c = cast(
                        SleepCommand, command
                    )  # pyright: ignore[reportInvalidCast]
                    t_start = time.monotonic()
                    while time.monotonic() < t_start + c["timeout"]:
                        yield
                case "expect":
                    c = cast(
                        ExpectCommand, command
                    )  # pyright: ignore[reportInvalidCast]
                    t_start = time.monotonic()
                    while time.monotonic() < t_start + c[
                        "timeout"
                    ] and screen.content != c.get("content", None):
                        yield
                    if update:
                        c["content"] = screen.content
                    else:
                        assert screen.content == c.get("content", None)
                case _:
                    pass
        yield KEY_ALIASES["C-g"]

    key_reader = foo()

    with TmpFiles() as tmpfile:
        for k, v in vars(tjex_config.Config()).items():
            setattr(tjex_config.config, k, v)
        assert 0 == tjex.tjex(
            screen,
            lambda: next(key_reader),
            screen.clear,
            lambda: None,
            [
                (
                    Path(i)
                    if isinstance(i, str)
                    else tmpfile(
                        "\n".join(json.dumps(j, ensure_ascii=False) for j in i)
                    )
                )
                for i in test_case["inputs"]
            ],
            "",
            tmpfile("".join(l + "\n" for l in test_case.get("config", []))),
            50,
            False,
        )

    if update:
        with open(path, "w") as f:
            json.dump(test_case, f, indent=2, ensure_ascii=False)
            _ = f.write("\n")


@pytest.fixture(scope="session")
def fork_server():
    set_start_method("forkserver")


@pytest.mark.parametrize("path", case_paths(), ids=case_name)
def test_integration(
    path: Path, fork_server: None  # pyright: ignore[reportUnusedParameter]
):
    run_case(path, False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Update expected results in integration test cases."
    )
    _ = parser.add_argument("pattern", nargs="?", default="")
    args = parser.parse_args()
    set_start_method("forkserver")
    pattern = re.compile(args.pattern)
    for path in case_paths():
        if pattern.search(case_name(path)):
            run_case(path, True)
