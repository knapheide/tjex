from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("tjex")


def setup(logfile: Path | None):
    if logfile is not None:
        logging.basicConfig(
            filename=logfile.as_posix(),
            level=logging.DEBUG,
        )
