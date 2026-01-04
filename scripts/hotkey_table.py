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


def main(readme: Path | None):
    set_start_method("forkserver")
    screen = DummyRegion(Point(0, 0))

    with TmpFiles() as tmpfile:
        try:
            _ = tjex.tjex(
                screen,
                lambda: None,
                screen.clear,
                lambda: None,
                [tmpfile("[]")],
                "",
                tmpfile(""),
                50,
                False,
                make_hotkey_table=True,
            )
        except TjexError as e:
            table = e.msg
            if readme is None:
                print(table)
            else:
                with open(readme) as f:
                    lines = iter(f.readlines())
                    for l in lines:
                        print(l, end="")
                        if l.startswith("## Hotkeys"):
                            break
                    print(table)
                    while not (l := next(lines)).startswith("## "):
                        pass
                    print(l, end="")
                    for l in lines:
                        print(l, end="")

            readme_lines = readme and iter(readme.read_text().splitlines())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("readme", type=Path, nargs="?")
    args = parser.parse_args()
    main(args.readme)
