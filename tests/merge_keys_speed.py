import shutil
from timeit import timeit

from tjex.json_table import collect_keys


def merge_keys_speed(n: int):
    return timeit(
        lambda: collect_keys(
            [[f"data.{i}" for i in range(n + n * j)] for j in range(10)]
        ),
        number=10,
    )


if __name__ == "__main__":
    ns = [2**i for i in range(15)]
    ts = [merge_keys_speed(n) for n in ns]
    width, _ = shutil.get_terminal_size((80, 20))
    scale = (width - 10) / max(ts)

    for n, t in zip(ns, ts):
        print(f"{n:8d}: {int(t * scale) * '#'}")
