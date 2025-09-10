import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tjex.logging import logger
from tjex.panel import KeyBindings


@dataclass
class Config:
    bindings: dict[str, dict[str, str]] = field(default_factory=dict)
    float_precision: int = 8
    max_cell_width: int = 50


config: Config = Config()


def load(
    config_file: Path,
    bindings: dict[str, KeyBindings[Any, Any]],
) -> None:
    global config
    if config_file.exists():
        with open(config_file, "rb") as f:
            config = Config(**tomllib.load(f))
    else:
        logger.debug(bindings)
        pass  # TODO
