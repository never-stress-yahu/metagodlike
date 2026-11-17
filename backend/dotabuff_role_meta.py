"""Dated public Dotabuff role sample, separate from verified patch meta."""

import csv
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

COLLECTED_AT = datetime(2026, 11, 17, tzinfo=timezone.utc)
MAX_AGE = timedelta(days=7)
RANK = "CRUSADER"
SOURCE_URL = "https://www.dotabuff.com/heroes?date=7d&mode=all-pick&rankTier=crusader&show=heroes&view=played"
ROLES = {1: "core-safe", 2: "core-mid", 3: "core-off", 4: "support-off", 5: "support-safe"}


def load_role_sample(rank, hero_profiles, now):
    if rank != RANK or not timedelta(0) <= now - COLLECTED_AT <= MAX_AGE:
        return None

    known_heroes = {
        name.lower().replace("'", "").replace(" ", "-"): hero_id
        for hero_id, (name, *_) in hero_profiles.items()
    }
    heroes = {}
    path = Path(__file__).with_name("dotabuff_crusader_roles_2026-11-17.csv")
    try:
        with path.open(encoding="utf-8", newline="") as file:
            for row in csv.DictReader(file):
                hero_id = known_heroes[row["hero_slug"]]
                position = int(row["position"])
                matches = int(row["matches"])
                winrate = float(row["winrate"])
                share = float(row["reported_role_share"])
                if (position not in ROLES or matches < 200 or not math.isfinite(winrate)
                        or not 0 <= winrate <= 100 or not 10 <= share <= 100):
                    return None
                positions = heroes.setdefault(hero_id, {"positions": {}})["positions"]
                if position in positions:
                    return None
                positions[position] = {"matches": matches, "winrate": winrate, "reported_role_share": share}
    except (OSError, KeyError, TypeError, ValueError, csv.Error):
        return None
    if not all(any(position in hero["positions"] for hero in heroes.values()) for position in ROLES):
        return None
    return {
        "source": "Dotabuff seven-day ranked All Pick role sample",
        "source_url": SOURCE_URL,
        "rank_bracket": RANK,
        "requested_rank_bracket": RANK,
        "collected_at": COLLECTED_AT.isoformat(),
        "position_data_exact": False,
        "dotabuff_role_sample": True,
        "warnings": ["Dotabuff position classifications and seven-day samples are provider-reported. "
                     "The sample is not independently verified for a specific minor patch."],
        "heroes": heroes,
    }
