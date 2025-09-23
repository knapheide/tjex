from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

from tjex.curses_helper import KEY_ALIASES, WindowRegion


class Event(ABC):
    pass


@dataclass
class StatusUpdate(Event):
    msg: str


T = TypeVar("T")
S = TypeVar("S")
R = TypeVar("R")


@dataclass(frozen=True)
class KeyPress(Event):
    key: str


@dataclass
class Function(Generic[T, S]):
    f: Callable[[T], S]
    name: str
    description: str | None


class KeyBindings(Generic[T, S]):
    def __init__(self):
        self.functions: list[Function[T, S]] = []
        self.bindings: dict[str, Function[T, S]] = {}

    def add(self, *key: str, name: str | None = None):
        def wrap(f: Callable[[T], S]) -> Callable[[T], S]:
            func = Function(f, f.__name__ if name is None else name, f.__doc__)
            self.functions.append(func)
            for k in key:
                self.bindings[KEY_ALIASES.get(k, k)] = func
            return f

        return wrap

    def handle_key(self, key: KeyPress | R, p: T) -> KeyPress | R | S:
        if isinstance(key, KeyPress) and key.key in self.bindings:
            return self.bindings[key.key].f(p)
        return key


class Panel(ABC):
    active: bool = False
    window: WindowRegion

    def resize(self):
        pass

    @abstractmethod
    def handle_key(self, key: KeyPress) -> Iterable[Event]:
        pass

    @abstractmethod
    def draw(self):
        pass

    def set_active(self, active: bool):
        self.active = active
