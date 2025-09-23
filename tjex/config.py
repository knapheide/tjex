import json
import subprocess as sp
import tomllib
from base64 import b64encode
from dataclasses import asdict, dataclass, field
from pathlib import Path
from textwrap import dedent
from typing import Any, TypeVar

from tjex.panel import KeyBindings
from tjex.utils import TjexError


class ConfigError(TjexError):
    pass


T = TypeVar("T")


def config_field(default: T, doc: str) -> T:
    return field(default=default, metadata={"doc": dedent(doc).strip()})


@dataclass
class Config:
    bindings: dict[str, dict[str, str]] = field(default_factory=dict)
    float_precision: int = config_field(
        8, "Number of significand digits for floating point numbers"
    )
    max_cell_width: int = config_field(50, "Default maximum cell width")
    copy_command: str | None = config_field(
        None,
        """
        Bash command to copy a string from stdin to the clipboard
        e.g.
        * "osc" (https://github.com/theimpostor/osc)
        * "wl-copy 2> /dev/null"
          (It's important to pipe stderr to null, because `wl-copy` will stick around and make tjex hang otherwise)
        By default, tjex just emits the plain OCS52 escape sequence.
        For many setups, this wont work though.
        """,
    )
    append_history_command: str = config_field(
        "atuin history end --exit 0 -- $(atuin history start -- {})",
        "Format string that generates a bash command to append the given string to a shell history",
    )

    def do_copy(self, s: str):
        if self.copy_command is None:
            print("\033]52;c;{}\a".format(b64encode(s.encode()).decode()))
        else:
            result = sp.run(
                ["bash", "-c", self.copy_command],
                input=s + "\n",
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise ConfigError(result.stderr)


config: Config = Config()


def comment_out(s: str):
    return "".join(f"# {l}\n" if l else "\n" for l in s.splitlines())


def make_example_config(bindings: dict[str, KeyBindings[Any, Any]]):
    res = "# Example configuration for tjex"

    for k, v in asdict(config).items():
        if k != "bindings":
            res += "\n\n"
            if doc := config.__dataclass_fields__[k].metadata.get("doc"):
                res += comment_out(doc)
            if v is None:
                res += comment_out(f'{json.dumps(k)} = ""')
            else:
                res += f"{json.dumps(k)} = {json.dumps(v)}"

    for panel, b in bindings.items():
        res += f"\n\n"
        res += f"[bindings.{panel}]"
        for f in b.functions:
            res += f"\n"
            res += comment_out(f.name)
            if f.description is not None:
                res += comment_out(f.description)
            for k, v in b.bindings.items():
                if v == f:
                    res += f"{json.dumps(k)} = {json.dumps(f.name)}\n"

    return comment_out(res)


def apply_bindings(bindings: dict[str, KeyBindings[Any, Any]]):
    for panel, b in config.bindings.items():
        for k, f in b.items():
            bindings[panel].bindings[k] = next(
                _f for _f in bindings[panel].functions if _f.name == f
            )


def load(
    config_file: Path,
    bindings: dict[str, KeyBindings[Any, Any]],
) -> None:
    if config_file.exists():
        with open(config_file, "rb") as f:
            for k, v in tomllib.load(f).items():
                setattr(config, k, v)
        apply_bindings(bindings)
    else:
        config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(config_file, "w") as f:
            _ = f.write(make_example_config(bindings))
