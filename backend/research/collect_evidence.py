"""Collect public evidence. Review generated files before publishing."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main


async def collect(database, destination):
    destination.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        cache = json.loads(connection.execute("SELECT payload FROM active_snapshot").fetchone()[0])["cache"]
    fetched = datetime.now(timezone.utc).isoformat()
    histories = []
    async with httpx.AsyncClient(timeout=30) as client:
        for index, account in enumerate([321580662, 1095778432, 100058342, 301750126], 1):
            url = f"https://api.opendota.com/api/players/{account}/matches?limit=1000"
            response = await client.get(url)
            response.raise_for_status()
            rows = response.json()
            matches = []
            for row in rows:
                if row.get("radiant_win") is None or row.get("player_slot") is None:
                    continue
                matches.append({
                    "match_id": row["match_id"], "hero_id": row["hero_id"],
                    "start_time": row["start_time"],
                    "is_win": bool(row["radiant_win"]) == (row["player_slot"] < 128),
                })
            histories.append({"player": f"player-{index}", "source": url, "matches": matches})
            print(f"History {index}: {len(matches)}", flush=True)
            await asyncio.sleep(1)
        await main.fetch_hero_catalog(client)

    (destination / "personal-history.json").write_text(json.dumps({
        "collected_at": fetched, "scope": "Latest public matches, pooled roles",
        "players": histories,
    }, indent=2), encoding="utf8", newline="\n")

    cases = []
    for match in cache["recent"][:8]:
        try:
            lineups = await main.load_match_lineups(cache, match["match_id"])
        except Exception as error:
            print(type(error).__name__, match["match_id"], flush=True)
            continue
        if not lineups.get("draft"):
            continue
        pick = next(p for p in lineups["draft"]["picks"] if p["hero"]["is_you"])
        position = lineups["player_position"]
        if position not in (1, 2, 3) or not pick["enemies_revealed"]:
            continue
        prior = [m for m in cache["history"] if m["start_time"] < match["start_time"]]
        experience = {r["hero_id"]: [r["wins"], r["games"]] for r in main.history_hero_totals(prior)}
        eligible = [h["hero_id"] for h in cache["heroes"]
                    if position in main.fallback_positions(h["hero_id"])
                    and position not in main.CONDITIONAL_POSITIONS.get(h["hero_id"], set())
                    and h["hero_id"] not in pick["unavailable_hero_ids"]]
        cases.append({"match_id": match["match_id"], "position": position,
                      "position_source": "provider estimate", "actual_hero": pick["hero"]["hero_id"],
                      "start_time": match["start_time"], "lineups": lineups,
                      "experience": experience, "eligible": eligible,
                      "enemies": pick["enemies_revealed"]})
        print("Draft", match["match_id"], position, flush=True)
        if len(cases) == 3:
            break
    ids = sorted({i for c in cases for i in c["eligible"]} |
                 {e["hero_id"] for c in cases for e in c["enemies"]})
    tables = {}
    async with httpx.AsyncClient(timeout=20) as client:
        for hero_id in ids:
            tables[hero_id] = await main.fetch_enemy_matchups(client, hero_id, {})
            print("Matchups", hero_id, len(tables[hero_id]), flush=True)
            await asyncio.sleep(1)
    heroes = [{k: h.get(k) for k in ("hero_id", "name", "icon_url", "complexity", "complexity_name")}
              for h in cache["heroes"]]
    (destination / "drafts.json").write_text(json.dumps({
        "collected_at": fetched, "scope": "Historical reconstruction using later population aggregates",
        "matchup_source": "https://api.opendota.com/api/heroes/{hero_id}/matchups",
        "meta_source": "https://api.opendota.com/api/heroStats",
        "meta_rank": main.rank_bracket(cache["rank"])[1],
        "heroes": heroes, "meta": main.build_opendota_meta(cache["rank"], cache["heroes"]),
        "cases": cases, "matchups": tables,
    }, indent=2), encoding="utf8", newline="\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    asyncio.run(collect(args.database, args.destination))
