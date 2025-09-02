from __future__ import annotations

from typing import Generic, TypeVar

from tjex.logging import logger

T = TypeVar("T")


class History(Generic[T]):
    history: list[T]
    position: int

    @property
    def current(self):
        return self.history[self.position]

    def __init__(self, default: T):
        self.history = [default]
        self.position = 0

    def push(self, v: T):
        if self.current != v:
            self.history = [*self.history[: self.position + 1], v]
            self.position += 1
        logger.debug(("push", self.history, self.position))

    def pop(self, current: T):
        if current != self.current:
            self.push(current)
        self.position = max(0, self.position - 1)
        return self.current

    def redo(self):
        self.position = min(self.position + 1, len(self.history) - 1)
        return self.current
