"""Extend the original public-history cohort using ranked OpenDota seed matches."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from urllib.parse import urlsplit

import httpx

API = "https://api.opendota.com/api"
RANK_BANDS = ((10, 29), (30, 49), (50, 69), (70, 89))
PLAYERS_PER_BAND = 4
HISTORY_LIMIT = 1000
MIN_HISTORY = 300
RANKED_LOBBY = 7
ALL_PICK = 22


def get_json(client, path, params=None):
    for attempt in range(3):
        time.sleep(1.1)
        response = client.get(API + path, params=params)
        if response.status_code not in (429, 502, 503, 504):
            response.raise_for_status()
            return response.json()
        if attempt < 2:
            time.sleep(5 * (attempt + 1))
    response.raise_for_status()


def player_history(rows):
    matches = {}
    for row in rows:
        if (not isinstance(row.get("radiant_win"), bool)
                or not isinstance(row.get("player_slot"), int)
                or not all(isinstance(row.get(key), int) and row[key] > 0
                           for key in ("match_id", "hero_id", "start_time"))):
            continue
        matches[row["match_id"]] = {
            "match_id": row["match_id"],
            "hero_id": row["hero_id"],
            "start_time": row["start_time"],
            "is_win": row["radiant_win"] == (row["player_slot"] < 128),
        }
    return sorted(matches.values(), key=lambda row: (row["start_time"], row["match_id"]), reverse=True)


def sample_band(client, minimum, maximum, seen):
    new_players = []
    params = {"min_rank": minimum, "max_rank": maximum}
    for _ in range(12):
        seeds = get_json(client, "/publicMatches", params)
        if not seeds:
            break
        for seed in sorted(seeds, key=lambda row: row["match_id"], reverse=True):
            rank = seed.get("avg_rank_tier")
            if (rank is None or not minimum <= rank <= maximum
                    or seed.get("lobby_type") != RANKED_LOBBY or seed.get("game_mode") != ALL_PICK):
                continue
            match_id = seed["match_id"]
            details = get_json(client, f"/matches/{match_id}")
            accounts = sorted({player["account_id"] for player in details.get("players", [])
                               if isinstance(player.get("account_id"), int)
                               and 0 < player["account_id"] < 4294967295})
            for account in accounts:
                if account in seen:
                    continue
                seen.add(account)
                path = f"/players/{account}/matches"
                matches = player_history(get_json(client, path, {"limit": HISTORY_LIMIT}))
                if len(matches) < MIN_HISTORY:
                    continue
                new_players.append({
                    "source": f"{API}{path}?limit={HISTORY_LIMIT}",
                    "seed_match_id": match_id,
                    "seed_match_avg_rank_tier": rank,
                    "matches": matches,
                })
                print(f"Rank band {minimum}-{maximum}: {len(new_players)}/{PLAYERS_PER_BAND}, "
                      f"{len(matches)} matches", flush=True)
                break
            if len(new_players) == PLAYERS_PER_BAND:
                return new_players
        params["less_than_match_id"] = min(seed["match_id"] for seed in seeds)
    raise RuntimeError(f"Found only {len(new_players)} eligible players in rank band {minimum}-{maximum}")


def collect(original, destination):
    snapshot = json.loads(original.read_text(encoding="utf8"))
    if "expanded_at" in snapshot:
        raise ValueError("Use the original cohort as the input")
    players = snapshot["players"]
    seen = {int(urlsplit(player["source"]).path.split("/")[-2]) for player in players}
    started = datetime.now(timezone.utc).isoformat()
    with httpx.Client(timeout=30) as client:
        for minimum, maximum in RANK_BANDS:
            for player in sample_band(client, minimum, maximum, seen):
                players.append({"player": f"player-{len(players) + 1}", **player})
    snapshot["expanded_at"] = started
    destination.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf8", newline="\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    collect(args.original, args.destination)
