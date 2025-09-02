from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

from tjex.curses_helper import WindowRegion


class Event(ABC):
    pass


T = TypeVar("T")
S = TypeVar("S")
R = TypeVar("R")


@dataclass(frozen=True)
class KeyPress(Event):
    key: str


class KeyBindings(Generic[T, S]):
    def __init__(self):
        self.bindings: dict[str, Callable[[T], S]] = {}

    def add(self, *key: str):
        def wrap(f: Callable[[T], S]) -> Callable[[T], S]:
            for k in key:
                self.bindings[k] = f
            return f

        return wrap

    def handle_key(self, key: KeyPress | R, p: T) -> KeyPress | R | S:
        if isinstance(key, KeyPress) and key.key in self.bindings:
            return self.bindings[key.key](p)
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
