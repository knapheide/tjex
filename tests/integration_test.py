from contextlib import ExitStack
from multiprocessing import set_start_method
from pathlib import Path
from tempfile import NamedTemporaryFile

from tjex import tjex
from tjex.curses_helper import KEY_ALIASES, DummyRegion
from tjex.point import Point


def test_integration():
    set_start_method("forkserver")
    dummy = DummyRegion(Point(50, 100))

    with ExitStack() as stack:

        def tmpfile(s: str):
            buffered = stack.enter_context(
                NamedTemporaryFile(mode="w", delete_on_close=False, delete=True)
            )
            _ = buffered.write(s)
            buffered.close()
            return Path(buffered.name)

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
