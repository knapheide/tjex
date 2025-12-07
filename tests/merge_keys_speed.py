import argparse
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


BARS = ["", "▏", "▎", "▍", "▌", "▋", "▊", "▉"]


def main():
    ns = [200 * i for i in range(20)]
    ts = [merge_keys_speed(n) for n in ns]
    width, _ = shutil.get_terminal_size((80, 20))
    scale = (width - 10) / max(ts)

    for n, t in zip(ns, ts):
        bar = int(t * scale) * "█" + BARS[int(((t * scale) % 1) * len(BARS))]
        print(f"{n:9d} {bar}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Plot complexity of collect_keys function"
    )
    _ = parser.parse_args()
    main()
