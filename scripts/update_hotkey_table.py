import argparse
import curses
from multiprocessing import set_start_method
from pathlib import Path

from tjex import tjex
from tjex.curses_helper import DummyRegion
from tjex.point import Point
from tjex.utils import TjexError, TmpFiles

# Stub out curses functions that might get called
curses.color_pair = lambda _: 0  # pyright: ignore[reportUnknownLambdaType]


def make_table():
    screen = DummyRegion(Point(0, 0))

    with TmpFiles() as tmpfile:
        tjex_main = tjex.Tjex(
            screen,
            [tmpfile("[]")],
            "",
            tmpfile(""),
            50,
            False,
        )
        return tjex_main.make_hotkey_table()


def main(readme: Path | None):
    set_start_method("forkserver")

    table = make_table()

    if readme is None:
        print(table)
        return

    readme_lines = iter(readme.read_text().splitlines())

    with open(readme, "w") as f:
        for l in readme_lines:
            print(l, file=f)
            if l.startswith("## Hotkeys"):
                break
        print(table, file=f)
        while not (l := next(readme_lines)).startswith("## "):
            pass
        print(l, file=f)
        for l in readme_lines:
            print(l, file=f)

    readme_lines = readme and iter(readme.read_text().splitlines())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("readme", type=Path, nargs="?")
    args = parser.parse_args()
    main(args.readme)
