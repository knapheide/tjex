from __future__ import annotations


class KillRing:
    def __init__(self):
        self.ring: list[str] = []
        self.kill_active: bool = False
        self.yank_index: int = 0

    def kill(self, v: str, prepend: bool = False):
        if self.kill_active:
            self.ring[-1] = v + self.ring[-1] if prepend else self.ring[-1] + v
        else:
            self.ring.append(v)
        self.kill_active = True
        self.yank_index = len(self.ring) - 1

    def kill_done(self):
        self.kill_active = False

    def yank(self):
        if self.ring:
            return self.ring[self.yank_index]
        return ""

    def rotate(self):
        self.yank_index = (self.yank_index - 1) % max(1, len(self.ring))
        return self.yank()
