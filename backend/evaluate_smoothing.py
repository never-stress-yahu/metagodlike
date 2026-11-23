"""Walk-forward ablation on one exported player history (standard library only)."""
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path


def evaluate(history):
    records = defaultdict(list)
    errors = defaultdict(list)
    for row in sorted(history, key=lambda r: r["start_time"]):
        t, hero, outcome = row["start_time"], row["hero_id"], row["is_win"]
        if not isinstance(outcome, bool):
            continue
        past = [(2 ** (-(t - start) / (30 * 86400)), win)
                for start, win in records[hero] if 0 < t - start <= 90 * 86400]
        records[hero].append((t, outcome))
        if not past:
            continue
        games = sum(w for w, _ in past)
        wins = sum(w * win for w, win in past)
        for name, p in [("Neutral", .5), ("Personal", wins / games),
                        ("Smoothed", (wins + 40 * .5) / (games + 40))]:
            errors[name].append((p - outcome) ** 2)
    for name, values in errors.items():
        print(f"{name}: {len(values)} predictions, Brier {sum(values)/len(values):.4f}")


if __name__ == "__main__":
    with sqlite3.connect(Path(sys.argv[1]).resolve().as_uri() + "?mode=ro", uri=True) as db:
        snapshot = json.loads(db.execute("SELECT payload FROM active_snapshot").fetchone()[0])
    evaluate(snapshot["cache"]["history"])
