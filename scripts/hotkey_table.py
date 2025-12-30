import curses
from multiprocessing import set_start_method

from tjex import tjex
from tjex.curses_helper import DummyRegion
from tjex.point import Point
from tjex.utils import TmpFiles

# Stub out curses functions that might get called
curses.color_pair = lambda _: 0  # pyright: ignore[reportUnknownLambdaType]


def main():
    set_start_method("forkserver")
    screen = DummyRegion(Point(0, 0))

    with TmpFiles() as tmpfile:
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


if __name__ == "__main__":
    main()
