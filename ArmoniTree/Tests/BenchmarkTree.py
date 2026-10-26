import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from Models.Note import Note
from Structures.MusicTree import MusicTree
from Models.MusicNode import MusicNode

SIZES = (1_000, 10_000, 100_000)
FANOUT = 4


def make_records(size: int, shape: str):
    records = []
    for index in range(size):
        if index == 0:
            parent = None
        elif shape == "chain":
            parent = f"n{index - 1}"
        elif shape == "star":
            parent = "n0"
        else:
            parent = f"n{(index - 1) // FANOUT}"
        records.append({
            "id": f"n{index}", "name": f"Version {index}", "parent_id": parent,
            "notes": ["C4:1"], "tempo_bpm": 100, "time_signature": "4/4", "key": None,
            "description": "", "created_at": "2026-01-01T00:00:00",
        })
    return records


def best_of(function, repeats=3):
    best = float("inf")
    for _ in range(repeats):
        start = time.perf_counter()
        function()
        best = min(best, time.perf_counter() - start)
    return best * 1000


def run():
    print(f"{'forma':10}{'n':>9}{'altura':>8}{'find(ult.)':>12}{'DFS':>10}{'BFS':>10}{'stats':>10}{'insert':>10}   (ms)")
    for shape in ("balanced", "star", "chain"):
        for size in SIZES:
            tree = MusicTree.from_records(make_records(size, shape))
            target = f"n{size - 1}"
            height = tree.height()
            find = best_of(lambda: tree.find_by_id(target))
            dfs = best_of(lambda: sum(1 for _ in tree.dfs()))
            bfs = best_of(lambda: sum(1 for _ in tree.bfs()))
            stats = best_of(tree.stats)
            counter = [0]

            def insert_once():
                counter[0] += 1
                node = MusicNode("Nueva", [Note.parse("C4:1")], parent_id="n0", node_id=f"x{counter[0]}")
                tree.insert("n0", node)

            insert = best_of(insert_once)
            print(f"{shape:10}{size:>9}{height:>8}{find:>12.2f}{dfs:>10.2f}{bfs:>10.2f}{stats:>10.2f}{insert:>10.2f}")


if __name__ == "__main__":
    run()
