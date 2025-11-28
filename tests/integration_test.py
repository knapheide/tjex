from multiprocessing import set_start_method

from tjex import tjex
from tjex.curses_helper import KEY_ALIASES, DummyRegion
from tjex.point import Point
from tjex.utils import TmpFiles


def test_integration():
    set_start_method("forkserver")
    dummy = DummyRegion(Point(50, 100))

    with TmpFiles() as tmpfile:
        _ = tjex.tjex(
            dummy,
            lambda: KEY_ALIASES["C-g"],
            lambda: None,
            lambda: None,
            [tmpfile("[]")],
            "",
            tmpfile(""),
            50,
            False,
        )
