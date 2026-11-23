from __future__ import annotations

import asyncio
from collections import Counter
from statistics import median
import logging
import json
from pathlib import Path as FilePath
import math
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Path, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from draft_recommendations import rank_draft_picks, population_rate
from dotabuff_role_meta import MAX_AGE as DOTABUFF_SAMPLE_MAX_AGE, ROLES as DOTABUFF_ROLES, load_role_sample
from database import init_db, load_active_player, save_active_player
from recommendation_context import (PERSONAL_UNKNOWN_ROLE_WEIGHT, learning_value,
                                    hero_learning_cost, temporal_evidence, load_snapshot)


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global ACTIVE_PLAYER_CACHE
    await asyncio.to_thread(init_db)
    try:
        ACTIVE_PLAYER_CACHE = await asyncio.to_thread(load_active_player)
    except (ValueError, KeyError, TypeError, AttributeError):
        logger.exception("Ignoring invalid player snapshot; sync is required")
        ACTIVE_PLAYER_CACHE = None
    yield


app = FastAPI(title="metagodlike API", lifespan=lifespan)
FRONTEND_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

OPENDOTA_BASE_URL = "https://api.opendota.com/api"
STRATZ_URL = "https://api.stratz.com/graphql"
VALVE_HERO_LIST_URL = "https://www.dota2.com/datafeed/herolist?language=english"
STEAM_ID64_BASE = 76561197960265728
SYNC_LOCK = asyncio.Lock()
ACTIVE_PLAYER_CACHE: dict[str, Any] | None = None
HERO_CATALOG_CACHE: dict[int, dict[str, Any]] = {}
HERO_STATS_CACHE: dict[int, dict[str, Any]] = {}
HERO_STATS_FETCHED_AT: str | None = None
HERO_STATS_FETCHED_MONOTONIC = 0.0
CATALOG_LOCK = asyncio.Lock()
CATALOG_TTL_SECONDS = 3600
META_TTL_SECONDS = 15 * 60
MAX_STALE_SECONDS = 24 * 3600
META_CACHE: dict[int, tuple[float, dict[str, Any]]] = {}
SYNC_COOLDOWN_SECONDS = 30
LAST_SYNC_ATTEMPT = float("-inf")
RECOMMENDATION_REFRESH_LOCK = asyncio.Lock()
LAST_META_REFRESH_ATTEMPT = float("-inf")
META_REFRESH_RETRY_SECONDS = 60
# Explicit product policies, not statistically validated thresholds.
MIN_META_MATCHES = 200
MIN_EXACT_POSITION_SHARE = 0.10
SCORING_VERSION = "3.2-current-pub-personal"
# Versioned product defaults, not trained/calibrated parameters.
PERSONAL_PRIOR_GAMES = 40.0
PERSONAL_WINDOW_DAYS = 90
PERSONAL_HALF_LIFE_DAYS = 30.0
LEARNING_MAX_GAMES = 20
RANK_BRACKETS = {
    1: "HERALD",
    2: "GUARDIAN",
    3: "CRUSADER",
    4: "ARCHON",
    5: "LEGEND",
    6: "ANCIENT",
    7: "DIVINE",
    8: "IMMORTAL",
}
MAX_META_RANK = 7
POSITION_NAMES = {
    1: "Carry",
    2: "Mid",
    3: "Offlane",
    4: "Soft Support",
    5: "Hard Support",
}
HERO_POSITION_MAPPING_VERSION = "2026-10-01-audited-pub-v4"
# Loaded once: a reviewable 127-hero policy, including conditional alternatives.
_policy_path = FilePath(__file__).with_name("hero_policy.json")
if _policy_path.exists():
    HERO_POLICY_AUDIT = json.loads(_policy_path.read_text(encoding="utf-8"))
    HERO_POSITION_PROFILES = {int(h["hero_id"]): (h["hero_name"], tuple(h["positions"]))
                              for h in HERO_POLICY_AUDIT["heroes"]}
else:
    raise RuntimeError("hero_policy.json is required; refusing to use an unaudited role list")
CONDITIONAL_POSITIONS = {int(h["hero_id"]): set(h.get("conditional_positions", []))
                         for h in HERO_POLICY_AUDIT["heroes"]}
CURRENT_PATCH_INFO = json.loads(FilePath(__file__).with_name("current_patch.json").read_text(encoding="utf-8"))
LAST_PATCH_REFRESH = 0.0


async def refresh_current_patch():
    global CURRENT_PATCH_INFO, LAST_PATCH_REFRESH
    if LAST_PATCH_REFRESH > 0 and time.monotonic() - LAST_PATCH_REFRESH < 3600:
        return CURRENT_PATCH_INFO
    LAST_PATCH_REFRESH = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            body = await request_json(client, "GET", "https://www.dota2.com/datafeed/patchnoteslist")
        rows = valid_rows(body.get("patches"), "Valve patch list")
        latest = max(rows, key=lambda row: as_int(row.get("patch_timestamp")))
        if not latest.get("patch_number") or not as_int(latest.get("patch_timestamp")):
            raise ProviderError("Invalid Valve patch metadata")
        CURRENT_PATCH_INFO = {**latest, "verified_at": datetime.now(timezone.utc).isoformat()}
    except (ProviderError, ValueError, KeyError, AttributeError):
        logger.warning("Current patch refresh unavailable; using last known patch with disclosed age")
    return CURRENT_PATCH_INFO

PRIMARY_ATTRIBUTES = {
    0: "str",
    1: "agi",
    2: "int",
    3: "all",
    4: "all",
}
COMPLEXITY_NAMES = {
    1: "Simple",
    2: "Moderate",
    3: "Complex",
}


class ProviderError(RuntimeError):
    pass


def valid_rows(value: Any, context: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ProviderError(f"{context}: expected a list")
    rows = [row for row in value if isinstance(row, dict)]
    if len(rows) != len(value):
        logger.warning("%s: discarded malformed rows", context)
    if value and not rows:
        raise ProviderError(f"{context}: no valid rows")
    return rows


def optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = int(value)
        if isinstance(value, float) and value != result:
            return None
        return result
    except (TypeError, ValueError, OverflowError):
        return None


def outcome(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    return None


def bounded_matches(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    ordered = sorted(rows, key=lambda m: (as_int(m.get("start_time")), as_int(m.get("match_id"))), reverse=True)
    result, seen = [], set()
    for row in ordered:
        match_id = as_int(row.get("match_id"))
        if match_id <= 0 or match_id in seen or outcome(row.get("is_win")) is None:
            continue
        seen.add(match_id)
        result.append(row)
        if len(result) == limit:
            break
    return result


def history_hero_totals(history: list[dict[str, Any]]) -> list[dict[str, int]]:
    totals: dict[int, dict[str, int]] = {}
    for match in history:
        hero_id = as_int(match.get("hero_id"))
        if hero_id > 0:
            row = totals.setdefault(hero_id, {"hero_id": hero_id, "games": 0, "wins": 0})
            row["games"] += 1
            row["wins"] += int(match["is_win"])
    return list(totals.values())


def timestamp(value: Any) -> int | None:
    parsed = optional_int(value)
    return parsed if parsed is not None and 0 < parsed <= 253402300799 else None


def normalize_opendota_match(match: dict[str, Any], detailed: bool = False) -> dict[str, Any] | None:
    won = player_won(match)
    match_id = as_int(match.get("match_id"))
    if won is None or match_id <= 0:
        return None
    row = {"match_id": match_id, "hero_id": as_int(match.get("hero_id")) or None,
           "is_win": won, "start_time": timestamp(match.get("start_time"))}
    # Retain these small fields in lightweight history when the provider supplies
    # them. Lane alone is not an exact position; never invent position 4/5.
    provider_position = optional_int(match.get("position_est"))
    row["position"] = provider_position if provider_position in POSITION_NAMES else None
    row["position_source"] = "provider estimate" if row["position"] else None
    row["lane_role"] = optional_int(match.get("lane_role"))
    if detailed:
        row.update({key: optional_int(match.get(source)) for key, source in {
            "kills": "kills", "deaths": "deaths", "assists": "assists",
            "gpm": "gold_per_min", "xpm": "xp_per_min", "duration": "duration",
            "position": "position_est", "lane_role": "lane_role", "lane": "lane", "last_hits": "last_hits",
        }.items()})
        row["position_source"] = "provider estimate" if row["position"] in POSITION_NAMES else None
        if row["position"] not in POSITION_NAMES:
            row["position"] = None
    return row


def normalize_stratz_match(match: dict[str, Any], detailed: bool = False) -> dict[str, Any] | None:
    players = match.get("players")
    if not isinstance(players, list) or not players or not isinstance(players[0], dict):
        return None
    player = players[0]
    won = outcome(player.get("isVictory"))
    match_id = as_int(match.get("id"))
    if won is None or match_id <= 0:
        return None
    row = {"match_id": match_id, "hero_id": as_int(player.get("heroId")) or None,
           "is_win": won, "start_time": timestamp(match.get("startDateTime"))}
    if detailed:
        row.update({key: optional_int(player.get(source)) for key, source in {
            "kills": "kills", "deaths": "deaths", "assists": "assists",
            "gpm": "goldPerMinute", "xpm": "experiencePerMinute",
        }.items()})
        row["duration"] = optional_int(match.get("durationSeconds"))
        row["position"] = None
        row["position_source"] = None
    return row

def normalize_account_id(value: int) -> int:
    account_id = value - STEAM_ID64_BASE if value >= STEAM_ID64_BASE else value
    if account_id <= 0 or account_id > 4_294_967_295:
        raise HTTPException(status_code=422, detail="Invalid Steam account ID")
    return account_id


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def percent(wins: int, games: int) -> float:
    return round(wins / games * 100, 2) if games > 0 else 0.0


def wilson_score(wins: int, games: int) -> float:
    if games <= 0:
        return 0.0
    z = 1.96
    ratio = wins / games
    denominator = 1 + z * z / games
    centre = ratio + z * z / (2 * games)
    margin = z * math.sqrt((ratio * (1 - ratio) + z * z / (4 * games)) / games)
    return round((centre - margin) / denominator * 100, 2)


def player_won(match: dict[str, Any]) -> bool | None:
    radiant_win = outcome(match.get("radiant_win"))
    player_slot = optional_int(match.get("player_slot"))
    if radiant_win is None or player_slot not in (*range(5), *range(128, 133)):
        return None
    return radiant_win == (player_slot < 128)

def image_url(path: Any) -> str | None:
    if not isinstance(path, str) or not path:
        return None
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return f"https://cdn.cloudflare.steamstatic.com{path}"


def curated_positions(hero_id: int) -> list[int]:
    profile = HERO_POSITION_PROFILES.get(hero_id)
    return list(profile[1]) if profile else []


def fallback_positions(hero_id: int) -> list[int]:
    """Conservative defaults when no role-specific statistics are available.

    The first curated position is a policy default, not an observed pick share.
    Support 4/5 alternatives stay available for designated support heroes.
    Cross-core and core/support alternatives need measured position statistics.
    Neither professional picks nor large out-of-policy counts expand eligibility.
    """
    positions = curated_positions(hero_id)
    if not positions:
        return []
    return [p for p in positions if p >= 4] if positions[0] >= 4 else positions[:1]


def position_policy_payload(hero_id: int) -> dict[str, Any]:
    positions = curated_positions(hero_id)
    return {"positions": positions,
            "position_names": [POSITION_NAMES[p] for p in positions],
            "fallback_positions": fallback_positions(hero_id),
            "conditional_positions": sorted(CONDITIONAL_POSITIONS.get(hero_id, set())),
            "audit_date": "2026-10-01",
            "policy_basis": "reviewed pub policy; high-MMR role evidence does not establish target-rank viability",
            "position_source": "strict_pub_policy" if positions else "unreviewed",
            "position_mapping_version": HERO_POSITION_MAPPING_VERSION}


def catalog_from_items(items: Any) -> dict[int, dict[str, Any]]:
    if not isinstance(items, list):
        return {}
    catalog = {}
    for item in valid_rows(items, "hero catalog"):
        hero_id = as_int(item.get("id"))
        if hero_id <= 0:
            continue
        positions = curated_positions(hero_id)
        catalog[hero_id] = {
            "hero_id": hero_id,
            "name": item.get("localized_name") or f"Hero {hero_id}",
            "primary_attribute": item.get("primary_attr"),
            "attack_type": item.get("attack_type"),
            "roles": [role for role in item.get("roles", []) if isinstance(role, str)]
            if isinstance(item.get("roles"), list) else [],
            "complexity": as_int(item.get("complexity")) or None,
            "complexity_name": COMPLEXITY_NAMES.get(as_int(item.get("complexity"))),
            "positions": positions,
            "position_names": [POSITION_NAMES[position] for position in positions],
            "position_source": "curated" if positions else "provider roles",
            "image_url": image_url(item.get("img")),
            "icon_url": image_url(item.get("icon")),
        }
    return catalog


def build_heroes(player_items: Any, catalog: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    player_stats = {}
    if isinstance(player_items, list):
        for item in valid_rows(player_items, "player heroes"):
            hero_id = as_int(item.get("hero_id") or item.get("heroId"))
            if hero_id <= 0:
                continue
            games = max(0, as_int(item.get("games")))
            wins_value = item.get("win") if "win" in item else item.get("wins")
            wins = min(games, max(0, as_int(wins_value)))
            player_stats[hero_id] = {"games": games, "wins": wins}

    hero_ids = sorted(set(HERO_POSITION_PROFILES) | set(catalog) | set(player_stats))
    heroes = []
    for hero_id in hero_ids:
        metadata = catalog.get(
            hero_id,
            {
                "hero_id": hero_id,
                "name": HERO_POSITION_PROFILES.get(hero_id, (f"Hero {hero_id}", ()))[0],
                "primary_attribute": None,
                "attack_type": None,
                "roles": [],
                "complexity": None,
                "complexity_name": None,
                "positions": curated_positions(hero_id),
                "position_names": [
                    POSITION_NAMES[position]
                    for position in curated_positions(hero_id)
                ],
                "position_source": "curated"
                if curated_positions(hero_id)
                else "provider roles",
                "image_url": None,
                "icon_url": None,
            },
        )
        games = player_stats.get(hero_id, {}).get("games", 0)
        wins = player_stats.get(hero_id, {}).get("wins", 0)
        heroes.append(
            {
                **metadata,
                **position_policy_payload(hero_id),
                "games": games,
                "wins": wins,
                "losses": games - wins,
                "winrate": percent(wins, games),
                "performance_score": wilson_score(wins, games),
            }
        )
    return heroes


def choose_profile_heroes(
    heroes: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    played = [hero for hero in heroes if hero["games"] > 0]
    if not played:
        return None, None
    favorite = max(played, key=lambda hero: (hero["games"], hero["wins"], -hero["hero_id"]))
    qualified = [hero for hero in played if hero["games"] >= 3] or played
    best = max(
        qualified,
        key=lambda hero: (
            hero["performance_score"],
            hero["winrate"],
            hero["games"],
            -hero["hero_id"],
        ),
    )
    return favorite, best


def rank_bracket(rank_tier: int) -> tuple[int | None, str | None]:
    rank_number = as_int(rank_tier) // 10
    if rank_number not in RANK_BRACKETS:
        return None, None
    return rank_number, RANK_BRACKETS[rank_number]


def meta_rank_bracket(rank_tier: int) -> tuple[int | None, str | None]:
    rank_number, _ = rank_bracket(rank_tier)
    if rank_number is None:
        return None, None
    meta_rank_number = min(rank_number, MAX_META_RANK)
    return meta_rank_number, RANK_BRACKETS[meta_rank_number]


def estimated_positions(hero: dict[str, Any]) -> list[int]:
    # Manual positions are the product's eligibility rules, including with STRATZ meta.
    # Unknown/new heroes need a mapping update, rather than an invented default Mid role.
    return curated_positions(as_int(hero.get("hero_id")))

def match_position(match: dict[str, Any], hero: dict[str, Any] | None) -> int | None:
    provider_position = as_int(match.get("position"))
    if provider_position in POSITION_NAMES:
        return provider_position
    positions = estimated_positions(hero or {})
    lane_positions = {1: {1, 5}, 2: {2}, 3: {3, 4}}.get(as_int(match.get("lane_role")))
    if lane_positions is None:
        return None  # Jungle/unknown does not identify a position.
    candidates = lane_positions.intersection(positions)
    return next(iter(candidates)) if len(candidates) == 1 else None

def build_recent_focus(
    recent: list[dict[str, Any]],
    heroes: list[dict[str, Any]],
    meta: dict[str, Any],
    position_override: int | None = None,
) -> dict[str, Any] | None:
    heroes_by_id = {hero["hero_id"]: hero for hero in heroes}
    totals: dict[int, dict[str, Any]] = {}
    for match in recent[:20]:
        if outcome(match.get("is_win")) is None:
            continue
        hero_id = as_int(match.get("hero_id"))
        if hero_id <= 0:
            continue
        row = totals.setdefault(hero_id, {"matches": 0, "wins": 0, "positions": {}})
        row["matches"] += 1
        row["wins"] += int(bool(match.get("is_win")))
        position = match_position(match, heroes_by_id.get(hero_id))
        if position:
            row["positions"][position] = row["positions"].get(position, 0) + 1

    if not totals:
        return None

    # When switching role, use a compatible recent hero as the similarity reference.
    compatible = {hero_id: row for hero_id, row in totals.items()
                  if position_override in curated_positions(hero_id)} if position_override else {}
    hero_id, row = max(
        (compatible or totals).items(),
        key=lambda item: (item[1]["matches"], item[1]["wins"], -item[0]),
    )
    position_source = "recent matches (estimated)"
    if position_override is not None:
        position = position_override
        position_source = "user selection"
    elif row["positions"]:
        position = max(row["positions"], key=row["positions"].get)
    else:
        hero_meta = meta.get("heroes", {}).get(hero_id, {}).get("positions", {})
        allowed = curated_positions(hero_id)
        hero_meta = {p: stats for p, stats in hero_meta.items() if p in allowed}
        if hero_meta and meta.get("position_data_exact"):
            position = max(hero_meta, key=lambda key: hero_meta[key]["matches"])
            position_source = "current meta (estimated)"
        else:
            positions = estimated_positions(heroes_by_id.get(hero_id, {}))
            position = positions[0] if positions else None
            position_source = "curated default (estimated)" if positions else "unknown"

    hero = heroes_by_id.get(hero_id, {"hero_id": hero_id, "name": f"Hero {hero_id}"})
    return {
        "hero_id": hero_id,
        "hero_name": hero.get("name"),
        "matches": row["matches"],
        "wins": row["wins"],
        "losses": row["matches"] - row["wins"],
        "winrate": percent(row["wins"], row["matches"]),
        "position": position,
        "position_name": POSITION_NAMES.get(position),
        "position_is_estimated": position_source != "user selection",
        "position_source": position_source,
        "position_matches": row["positions"].get(position, 0),
    }


def meta_points(winrate: float, matches: int) -> tuple[float, float, float]:
    # Shrink sparse samples toward 50%; this is a heuristic reliability weight.
    matches = max(0, matches)
    confidence = matches / (matches + 500)
    adjusted_winrate = 50 + (winrate - 50) * confidence
    points = max(-9.0, min(9.0, (adjusted_winrate - 50) * 1.5))
    return round(points, 2), round(adjusted_winrate, 2), round(confidence, 2)

def recent_role_evidence(cache: dict[str, Any], position: int, now: datetime) -> dict[int, dict[str, Any]]:
    """Bounded, deduplicated pre-request evidence; no inferred lanes or lifetime W/L."""
    merged: dict[int, dict[str, Any]] = {}
    for match in cache.get("history", [])[:1000] + cache.get("recent", [])[:20]:
        match_id = as_int(match.get("match_id"))
        if match_id <= 0:
            continue
        previous = merged.get(match_id, {})
        merged[match_id] = {**previous, **{k: v for k, v in match.items() if v is not None}}
    totals: dict[int, dict[str, Any]] = {}
    for match in merged.values():
        hero_id = as_int(match.get("hero_id"))
        played_at = timestamp(match.get("start_time"))
        won = outcome(match.get("is_win"))
        if hero_id <= 0 or played_at is None or won is None:
            continue
        age_days = (now.timestamp() - played_at) / 86400
        if not 0 <= age_days <= PERSONAL_WINDOW_DAYS:
            continue
        row = totals.setdefault(hero_id, {"recent_games": 0, "role_games": 0,
                                         "weighted_games": 0.0, "weighted_wins": 0.0,
                                         "unknown_role_games": 0, "unknown_role_wins": 0,
                                         "unknown_weighted_games": 0.0, "unknown_weighted_wins": 0.0,
                                         "role_wins": 0})
        row["recent_games"] += 1
        # Provider positions can themselves be estimates. We expose this scope;
        # inferred positions from the manual hero mapping are never counted.
        reported_position = optional_int(match.get("position"))
        weight = 2 ** (-age_days / PERSONAL_HALF_LIFE_DAYS)
        if reported_position not in POSITION_NAMES:
            row["unknown_role_games"] += 1
            row["unknown_role_wins"] += int(won)
            row["unknown_weighted_games"] += weight
            row["unknown_weighted_wins"] += weight * int(won)
            continue
        if reported_position != position:
            continue
        row["role_games"] += 1
        row["role_wins"] += int(won)
        row["weighted_games"] += weight
        row["weighted_wins"] += weight * int(won)
    return totals


def adjusted_personal_performance(wins: float, games: float, prior: float) -> float:
    """Shrink comparable recent role results toward a meta-derived prior (0..1)."""
    return (wins + PERSONAL_PRIOR_GAMES * prior) / (games + PERSONAL_PRIOR_GAMES)


def hero_familiarity(games: int, recent_games: int) -> float:
    # Lifetime/sample volume measures familiarity, not role-specific success.
    volume = min(1.0, math.log1p(max(0, games)) / math.log1p(100))
    recent = min(1.0, recent_games / 10)
    return 0.7 * volume + 0.3 * recent


def playstyle_similarity(hero: dict[str, Any], anchors: list[dict[str, Any]]) -> float:
    """Coarse content-based fallback, explicitly limited to available role tags."""
    tags = set(hero.get("roles") or []) - {"Carry", "Support"}
    if not tags:
        return 0.0
    pairs = []
    for anchor in anchors:
        if anchor["hero_id"] == hero["hero_id"]:
            continue
        other = set(anchor.get("roles") or []) - {"Carry", "Support"}
        if other:
            weight = math.log1p(max(0, anchor.get("games", 0)))
            pairs.append((len(tags & other) / len(tags | other), weight))
    denominator = sum(weight for _, weight in pairs)
    return sum(value * weight for value, weight in pairs) / denominator if denominator else 0.0


def build_recommendations(cache: dict[str, Any], limit: int, position: int | None = None,
                          unavailable_hero_ids: set[int] | None = None, *,
                          allow_historical_meta: bool = False,
                          allow_historical_learning: bool = False) -> dict[str, Any]:
    heroes, meta = cache["heroes"], cache["meta"]
    now = datetime.now(timezone.utc)
    focus = build_recent_focus(cache.get("recent", []), heroes, meta, position)
    target_position = position if position is not None else (focus or {}).get("position")
    focus_hero = next((h for h in heroes if h["hero_id"] == (focus or {}).get("hero_id")), {})
    # Use a small compatible hero pool instead of a single recent hero.
    anchors = sorted((h for h in heroes if h.get("games", 0) >= LEARNING_MAX_GAMES
                      and target_position in curated_positions(h["hero_id"])),
                     key=lambda h: (-h["games"], h["hero_id"]))[:5]
    evidence = recent_role_evidence(cache, target_position, now)
    role_volume = sum(row["weighted_games"] for row in evidence.values())
    unavailable_ids = set(unavailable_hero_ids or ())
    exact = bool(meta.get("position_data_exact"))
    observed_roles = bool(meta.get("dotabuff_role_sample"))
    temporal = temporal_evidence(meta, now, CURRENT_PATCH_INFO)
    strict_current = not allow_historical_meta and os.getenv("REQUIRE_CURRENT_PATCH_META", "true").lower() != "false"
    known_rank = meta.get("rank_bracket") in RANK_BRACKETS.values()
    verified_current = temporal["verified"] and exact and known_rank
    current_unavailable = temporal["wrong_patch"] or (strict_current and not verified_current)
    age = meta_age_seconds(meta)
    max_age = DOTABUFF_SAMPLE_MAX_AGE.total_seconds() if observed_roles else MAX_STALE_SECONDS
    ttl = MAX_STALE_SECONDS if observed_roles else META_TTL_SECONDS if exact else CATALOG_TTL_SECONDS
    stale = bool(meta.get("stale")) or age >= ttl
    unavailable = age > max_age or not meta.get("heroes")
    evidence_mode = "unavailable"
    if not unavailable and not current_unavailable:
        evidence_mode = "verified_current" if verified_current else "historical"
    historical_learning = allow_historical_learning and evidence_mode == "historical"
    learning_mode = evidence_mode if evidence_mode == "verified_current" or historical_learning else "unavailable"
    warnings = list(meta.get("warnings", []))
    if not exact and not observed_roles:
        warnings.append("Meta covers all positions; it is a weaker proxy, not measured role performance")
    if stale:
        warnings.append("Meta snapshot is stale")
    if not temporal["verified"]:
        warnings.append("Underlying meta window is not verified for the current patch")
    if current_unavailable:
        warnings.append("Current-patch evidence is required; recommendations are withheld")
    exclusions = {"manual_position": 0, "requires_position_meta": 0, "draft_unavailable": 0,
                  "insufficient_meta": 0, "rare_position": 0,
                  "invalid_meta": 0, "missing_meta": 0, "below_next_games_floor": 0,
                  "conditional_role_unverified": 0, "practice_first": 0,
                  "learning_unjustified": 0, "current_patch_unverified": int(current_unavailable)}
    next_games, learning = [], []
    if target_position in POSITION_NAMES and not unavailable and not current_unavailable:
        for hero in heroes:
            hero_id = hero["hero_id"]
            if hero_id in unavailable_ids:
                exclusions["draft_unavailable"] += 1
                continue
            if not observed_roles:
                if target_position not in curated_positions(hero_id):
                    exclusions["manual_position"] += 1
                    continue
                if target_position in CONDITIONAL_POSITIONS.get(hero_id, set()) and not (exact and temporal["verified"] and not meta.get("rank_fallback_applied")):
                    exclusions["conditional_role_unverified"] += 1
                    continue
                if not exact and target_position not in fallback_positions(hero_id):
                    exclusions["requires_position_meta"] += 1
                    continue
            positions = meta.get("heroes", {}).get(hero_id, {}).get("positions", {})
            stats = positions.get(target_position)
            if not stats:
                exclusions["missing_meta"] += 1
                continue
            matches = max(0, as_int(stats.get("matches")))
            try:
                wr = float(stats["winrate"])
            except (KeyError, TypeError, ValueError, OverflowError):
                wr = float("nan")
            if not math.isfinite(wr) or not 0 <= wr <= 100:
                exclusions["invalid_meta"] += 1
                continue
            if matches < MIN_META_MATCHES:
                exclusions["insufficient_meta"] += 1
                continue
            total = sum(max(0, as_int(p.get("matches"))) for p in positions.values())
            share = matches / total if total else 0.0
            if exact and share < MIN_EXACT_POSITION_SHARE:
                exclusions["rare_position"] += 1
                continue
            _, adjusted_meta, reliability = meta_points(wr, matches)
            # Aggregate/fallback meta and stale snapshots carry less influence.
            scope_quality = 1.0 if exact else 0.75 if observed_roles else 0.5
            quality = scope_quality * (0.75 if stale else 1.0) * (1.0 if temporal["verified"] else 0.5)
            prior = (50 + (adjusted_meta - 50) * quality) / 100
            ev = evidence.get(hero_id, {"recent_games": 0, "role_games": 0,
                                       "weighted_games": 0.0, "weighted_wins": 0.0,
                                       "unknown_role_games": 0, "unknown_role_wins": 0,
                                       "unknown_weighted_games": 0.0, "unknown_weighted_wins": 0.0,
                                       "role_wins": 0})
            posterior = adjusted_personal_performance(ev["weighted_wins"], ev["weighted_games"], prior)
            unknown_posterior = adjusted_personal_performance(ev["unknown_weighted_wins"], ev["unknown_weighted_games"], prior)
            readiness_adjustment = min(0.0, (unknown_posterior - prior) * 100) * PERSONAL_UNKNOWN_ROLE_WEIGHT
            readiness_games = ev["role_games"] + ev["unknown_role_games"]
            readiness_wins = ev["role_wins"] + ev["unknown_role_wins"]
            games = max(0, as_int(hero.get("games")), ev["recent_games"])
            familiarity = hero_familiarity(games, ev["recent_games"])
            similarity = playstyle_similarity(hero, anchors)
            learning_assessment = learning_value(hero_id, anchors, similarity)
            complexity = as_int(hero.get("complexity"))
            learning_cost = hero_learning_cost(complexity, games)
            meta_component = (prior - 0.5) * 100
            personal_component = (posterior - prior) * 100
            comfort_component = 1.5 * familiarity
            # A small role-specific pool signal, independent of wins and lifetime
            # aggregates. Sparse or unknown-position history contributes zero/little.
            pool_preference = ev["weighted_games"] / (role_volume + 20.0)
            pool_component = 0.75 * pool_preference
            next_score = meta_component + personal_component + readiness_adjustment + comfort_component + pool_component - learning_cost
            practice_first = (games < LEARNING_MAX_GAMES and readiness_games >= 3 and readiness_wins == 0) or (complexity == 3 and games < 5)
            learning_score = meta_component + 1.5 * similarity + learning_assessment["pool_gap_bonus"] - learning_cost
            if observed_roles:
                reasons = ["Dotabuff reports a significant sample for this position at the selected rank"]
            else:
                reasons = ["Allowed by the curated position policy",
                           "Position-specific meta" if exact else "All-position meta proxy; reduced influence"]
            if evidence_mode == "historical":
                reasons.append("Historical evidence; current-patch rank and position coverage is unverified")
            if ev["role_games"]:
                reasons.append(f"Personal adjustment uses {ev['role_games']} recent matches with a provider-reported position")
            else:
                reasons.append("No recent position-specific results; personal performance adjustment is neutral")
            if ev["unknown_role_games"]:
                reasons.append(f"Readiness caution uses {ev['unknown_role_games']} recent hero games with unknown position; not role win-rate evidence")
            if practice_first:
                reasons.append("Practice first: limited experience with a complex hero or at least three relevant recent games without a win")
            reasons.append(f"{games} recorded hero games inform familiarity, not role win rate")
            if learning_cost:
                reasons.append(f"{COMPLEXITY_NAMES[complexity]} difficulty applies a {learning_cost:.2f}-point learning penalty at your experience level")
            if pool_component:
                reasons.append("Small preference bonus from recent selections in this position")
            if stale:
                reasons.append("Stale meta has reduced influence")
            next_breakdown = {"current_meta": round(meta_component, 4),
                              "personal_performance": round(personal_component, 4),
                              "unknown_role_readiness": round(readiness_adjustment, 4),
                              "familiarity": round(comfort_component, 4),
                              "recent_role_pool": round(pool_component, 4),
                              "learning_cost": round(-learning_cost, 4)}
            common = {
                **hero, **position_policy_payload(hero_id), "target_position": target_position,
                "target_position_name": POSITION_NAMES[target_position],
                "meta_winrate": round(wr, 2), "adjusted_meta_winrate": adjusted_meta,
                "meta_matches": matches,
                "meta_scope": "rank_position_sample" if observed_roles else "rank_and_position" if exact else "rank_all_positions_proxy",
                "reported_role_share": stats.get("reported_role_share"),
                "meta_pick_rate": stats.get("pick_rate"),
                "meta_pick_rate_scope": "within_position_hero_picks" if exact else "all_rank_hero_picks",
                "position_share": round(share * 100, 2) if exact else None,
                "performance_estimate": round(posterior * 100, 2),
                "performance_estimate_kind": "shrunk_recent_role_rate_not_calibrated_win_probability",
                "next_game_readiness": "practice_first" if practice_first else "eligible",
                "learning_assessment": learning_assessment,
                "personal_evidence": {**ev, "weighted_games": round(ev["weighted_games"], 3),
                                      "weighted_wins": round(ev["weighted_wins"], 3),
                                      "scope": "provider_reported_position_may_be_estimated",
                                      "window_days": PERSONAL_WINDOW_DAYS},
                "score_context": {"meta_sample_reliability": reliability,
                                  "meta_quality_multiplier": quality,
                                  "familiarity": round(familiarity, 3),
                                  "playstyle_similarity": round(similarity, 3),
                                  "similarity_source": "coarse_provider_role_tags",
                                  "complexity": complexity if complexity in (1, 2, 3) else None,
                                  "experience_scope": "recorded_all_positions",
                                  "recent_role_pool_preference": round(pool_preference, 4),
                                  "personal_weight": round(ev["weighted_games"] / (ev["weighted_games"] + PERSONAL_PRIOR_GAMES), 3)},
                "reasons": reasons,
            }
            if next_score >= 0 and not practice_first:
                next_games.append({**common, "recommendation_score": round(next_score, 4),
                                   "score_breakdown": next_breakdown, "track": "next_games"})
            else:
                exclusions["practice_first" if practice_first else "below_next_games_floor"] += 1
            # Discovery does not push established heroes or currently below-neutral
            # meta. Never fill the learning list just to reach the requested size.
            learning_allowed = (
                games < LEARNING_MAX_GAMES and adjusted_meta >= 50 and learning_score >= 0
                and learning_assessment["justified"]
                and (verified_current or (historical_learning and (observed_roles or target_position in fallback_positions(hero_id))))
            )
            if games < LEARNING_MAX_GAMES and not learning_allowed:
                exclusions["learning_unjustified"] += 1
            if learning_allowed:
                learning_reason = (
                    "Current-patch role evidence supports a learning candidate" if verified_current
                    else "Historical statistics support a practice candidate for this position"
                )
                learning.append({**common, "recommendation_score": round(learning_score, 4),
                                 "score_breakdown": {"current_meta": round(meta_component, 4),
                                                     "playstyle_similarity": round(1.5 * similarity, 4),
                                                     "pool_capability_gap": learning_assessment["pool_gap_bonus"],
                                                     "learning_cost": round(-learning_cost, 4)},
                                 "track": "worth_learning",
                                 "reasons": reasons + [learning_reason,
                                                       "Adds options to " + ("; ".join(learning_assessment["gap_explanations"]) or "reinforce capabilities already in your pool"),
                                                       "Skills you can transfer: " + ("; ".join(learning_assessment["transfer_explanations"]) or "no established pool overlap; practice the new skills first"),
                                                       "Learning ranking does not claim immediate readiness or guaranteed win improvement"]})
    sort_key = lambda h: (-h["recommendation_score"], -h["meta_matches"], h["hero_id"])
    next_games.sort(key=sort_key)
    learning.sort(key=sort_key)
    recommendations = next_games[:limit]
    message = None
    if target_position not in POSITION_NAMES:
        message = "Select position=1..5; a reliable target position could not be inferred"
    elif unavailable:
        message = "Meta is missing or too old; refresh before requesting recommendations"
    elif current_unavailable:
        message = "Verified current-patch rank/role meta is unavailable; no historical aggregate is presented as today's recommendation"
    elif not recommendations:
        message = "No heroes passed the position and meta-evidence checks"
    learning_message = None
    if not learning:
        learning_message = (
            "No low-experience heroes passed the learning criteria"
            if learning_mode != "unavailable"
            else "Learning suggestions require verified role data or an enabled historical preview"
        )
    return {
        "analysis": {"recent_matches_analyzed": min(20, len(cache.get("recent", []))),
                     "focus_hero": focus, "similarity_applied": bool(anchors),
                     "similarity_anchor_ids": [h["hero_id"] for h in anchors],
                     "focus_hero_roles": focus_hero.get("roles") or [],
                     "focus_hero_attribute": focus_hero.get("primary_attribute"),
                     "focus_hero_attack_type": focus_hero.get("attack_type")},
        "meta": {"source": meta.get("source"), "requested_rank_bracket": meta.get("requested_rank_bracket"),
                 "rank_bracket": meta.get("rank_bracket"),
                 "rank_fallback_applied": meta.get("rank_fallback_applied", False),
                 "collected_at": meta.get("collected_at"), "position_data_exact": exact,
                 "position_mapping_version": HERO_POSITION_MAPPING_VERSION,
                 "stale": stale, "patch_coverage_verified": temporal["verified"],
                 "current_patch": temporal["patch"], "window_start": temporal["window_start"],
                 "window_end": temporal["window_end"], "current_patch_required": strict_current,
                 "evidence_mode": evidence_mode, "dotabuff_role_sample": observed_roles,
                 "source_url": meta.get("source_url"),
                 "warnings": list(dict.fromkeys(warnings))},
        "scoring_version": SCORING_VERSION, "score_kind": "ranking_utility_not_win_probability",
        "requested_position": position, "target_position": target_position,
        "target_position_name": POSITION_NAMES.get(target_position),
        "policy": {"minimum_meta_matches": MIN_META_MATCHES,
                   "audience": "2000-4000 MMR pubs; strict curated eligibility",
                   "professional_role_overrides_allowed": False,
                   "all_role_meta_cross_position_recommendations_allowed": False,
                   "recent_role_pool_maximum_bonus": 0.75,
                   "minimum_exact_position_share_percent": MIN_EXACT_POSITION_SHARE * 100,
                   "personal_prior_games": PERSONAL_PRIOR_GAMES,
                   "personal_window_days": PERSONAL_WINDOW_DAYS,
                   "personal_half_life_days": PERSONAL_HALF_LIFE_DAYS,
                   "learning_max_recorded_games_exclusive": LEARNING_MAX_GAMES,
                   "learning_minimum_adjusted_meta_winrate": 50,
                   "next_games_minimum_utility": 0,
                   "parameters_are_trained": False,
                   "unknown_role_readiness_weight": PERSONAL_UNKNOWN_ROLE_WEIGHT,
                   "unknown_role_positive_performance_bonus_allowed": False,
                   "learning_requires_current_patch_role_evidence": not allow_historical_learning},
        "excluded_by_reason": exclusions,
        "draft": {"unavailable_hero_ids": sorted(unavailable_ids),
                  "availability_filter_applied": bool(unavailable_ids),
                  "synergy_and_counter_scoring_applied": False},
        "recommendations": recommendations,  # Existing frontend compatibility.
        "recommended_for_next_games": recommendations,
        "worth_learning": learning[:limit],
        "worth_learning_evidence_mode": learning_mode,
        "worth_learning_message": learning_message,
        "message": message,
    }

def build_match_group_chart(
    history: list[dict[str, Any]],
    group_size: int = 20,
    max_groups: int = 50,
) -> list[dict[str, Any]]:
    if group_size <= 0 or max_groups <= 0:
        raise ValueError("Group limits must be positive")
    sample = bounded_matches(history, group_size * max_groups)
    newest_first = []

    for index in range(0, len(sample), group_size):
        chunk = sample[index : index + group_size]
        wins = sum(bool(match.get("is_win")) for match in chunk)
        timestamps = [
            as_int(match.get("start_time"))
            for match in chunk
            if timestamp(match.get("start_time")) is not None
        ]
        start_date = None
        end_date = None
        date_range = "Date unavailable"

        if timestamps:
            start_date = datetime.fromtimestamp(min(timestamps), tz=timezone.utc).date().isoformat()
            end_date = datetime.fromtimestamp(max(timestamps), tz=timezone.utc).date().isoformat()
            date_range = start_date if start_date == end_date else f"{start_date} вЂ“ {end_date}"

        newest_first.append(
            {
                "matches": len(chunk),
                "wins": wins,
                "losses": len(chunk) - wins,
                "winrate": percent(wins, len(chunk)),
                "start_date": start_date,
                "end_date": end_date,
                "date_range": date_range,
                "is_complete_group": len(chunk) == group_size,
            }
        )

    chronological = list(reversed(newest_first))
    for group_number, group in enumerate(chronological, start=1):
        group["group"] = group_number
    return chronological


def winrate_history_payload(cache: dict[str, Any]) -> dict[str, Any]:
    groups = build_match_group_chart(cache["history"])
    return {
        "account_id": cache["account_id"],
        "sample_size": sum(group["matches"] for group in groups),
        "group_size": 20,
        "group_count": len(groups),
        "groups": groups,
        "labels": [group["date_range"] for group in groups],
        "winrates": [group["winrate"] for group in groups],
    }


def serialize_match(match: dict[str, Any]) -> dict[str, Any]:
    duration = optional_int(match.get("duration"))
    duration = max(0, duration) if duration is not None else None
    kda = [optional_int(match.get(key)) for key in ("kills", "deaths", "assists")]
    return {
        "match_id": match.get("match_id"), "hero_id": match.get("hero_id"),
        "result": "Win" if match["is_win"] else "Loss", "is_win": match["is_win"],
        "kills": kda[0], "deaths": kda[1], "assists": kda[2],
        "kda_string": " / ".join(str(value) if value is not None else "?" for value in kda),
        "gpm": optional_int(match.get("gpm")), "xpm": optional_int(match.get("xpm")),
        "duration_seconds": duration,
        "duration": f"{duration // 60}:{duration % 60:02d}" if duration is not None else None,
        "start_time": timestamp(match.get("start_time")),
        "position": as_int(match.get("position")) or None,
        "position_name": POSITION_NAMES.get(as_int(match.get("position"))),
        "position_source": match.get("position_source"),
    }

def steam_avatar(profile):
    if not isinstance(profile, dict):
        return None
    for key in ("avatarfull", "avatarmedium", "avatar"):
        url = profile.get(key)
        if isinstance(url, str) and url.startswith("https://"):
            return url
    return None


def overview_payload(cache: dict[str, Any]) -> dict[str, Any]:
    recent = cache["recent"]
    total_matches = cache["total_wins"] + cache["total_losses"]
    complete_kda = [m for m in recent if all(optional_int(m.get(k)) is not None for k in ("kills", "deaths", "assists"))]
    deaths = sum(m["deaths"] for m in complete_kda)
    kills = sum(m["kills"] for m in complete_kda)
    assists = sum(m["assists"] for m in complete_kda)
    def mean_known(key):
        values = [value for m in recent if (value := optional_int(m.get(key))) is not None]
        return round(sum(values) / len(values)) if values else None
    return {
        "account_id": cache["account_id"],
        "name": cache["player_name"],
        "avatar_url": cache.get("avatar_url"),
        "rank": cache["rank"],
        "total_matches": total_matches,
        "wins": cache["total_wins"],
        "losses": cache["total_losses"],
        "winrate": percent(cache["total_wins"], total_matches),
        "recent_kda": round((kills + assists) / max(1, deaths), 2) if complete_kda else None,
        "recent_kda_matches": len(complete_kda),
        "recent_gpm": mean_known("gpm"),
        "recent_xpm": mean_known("xpm"),
        "favorite_hero": cache["favorite_hero"],
        "best_hero": cache["best_hero"],
        "source": cache["source"],
        "synced_at": cache["synced_at"],
        "hero_stats_scope": cache.get("hero_stats_scope"),
        "totals_scope": cache.get("totals_scope"),
        "warnings": cache.get("warnings", []),
    }


def active_cache() -> dict[str, Any]:
    if ACTIVE_PLAYER_CACHE is None:
        raise HTTPException(status_code=409, detail="No active player. Run POST /sync/{account_id} first")
    cache = ACTIVE_PLAYER_CACHE
    meta = cache["meta"]
    age = meta_age_seconds(meta)
    ttl = META_TTL_SECONDS if meta.get("position_data_exact") else CATALOG_TTL_SECONDS
    if age >= ttl:
        warnings = list(meta.get("warnings", []))
        warnings.append("Meta is stale; sync the player to refresh it")
        meta = {**meta, "stale": True, "warnings": warnings}
        if age > MAX_STALE_SECONDS:
            meta["heroes"] = {}
            warnings.append("Meta is too old for current recommendations")
        return {**cache, "meta": meta}
    return cache

def meta_age_seconds(meta: dict[str, Any]) -> float:
    try:
        collected_at = datetime.fromisoformat(meta.get("collected_at"))
        return max(0.0, (datetime.now(timezone.utc) - collected_at).total_seconds())
    except (ValueError, TypeError):
        return float("inf")


def usable_meta(meta: dict[str, Any]) -> dict[str, Any]:
    age = meta_age_seconds(meta)
    ttl = META_TTL_SECONDS if meta.get("position_data_exact") else CATALOG_TTL_SECONDS
    if age < ttl:
        return meta
    warnings = list(meta.get("warnings", []))
    warnings.append("Fresh meta is unavailable; this data is stale")
    result = {**meta, "stale": True, "warnings": warnings}
    if age > MAX_STALE_SECONDS:
        result["heroes"] = {}
        warnings.append("Meta is too old for current recommendations")
    return result


async def recommendation_cache(cache: dict[str, Any]) -> dict[str, Any]:
    """Refresh only meta on demand; player history is not fetched again."""
    global ACTIVE_PLAYER_CACHE, LAST_META_REFRESH_ATTEMPT
    meta = cache["meta"]
    ttl = META_TTL_SECONDS if meta.get("position_data_exact") else CATALOG_TTL_SECONDS
    if meta_age_seconds(meta) < ttl:
        return cache
    if RECOMMENDATION_REFRESH_LOCK.locked() or time.monotonic() - LAST_META_REFRESH_ATTEMPT < META_REFRESH_RETRY_SECONDS:
        return {**cache, "meta": usable_meta(meta)}
    async with RECOMMENDATION_REFRESH_LOCK:
        LAST_META_REFRESH_ATTEMPT = time.monotonic()
        async with httpx.AsyncClient(timeout=20.0) as client:
            await fetch_hero_catalog(client)
        refreshed = usable_meta(await fetch_current_meta(cache["rank"], cache["heroes"]))
        # A player sync may have replaced the account while provider calls were awaited.
        # Return a consistent response for this request, but do not overwrite the new player.
        if (ACTIVE_PLAYER_CACHE is not None and
                ACTIVE_PLAYER_CACHE["account_id"] == cache["account_id"] and
                ACTIVE_PLAYER_CACHE["synced_at"] == cache["synced_at"]):
            ACTIVE_PLAYER_CACHE = {**ACTIVE_PLAYER_CACHE, "meta": refreshed}
        return {**cache, "meta": refreshed}


async def request_json(client: httpx.AsyncClient, method: str, url: str, **kwargs) -> Any:
    for attempt in range(2):
        try:
            response = await client.request(method, url, **kwargs)
        except httpx.HTTPError as error:
            if attempt == 0:
                await asyncio.sleep(0.3)
                continue
            raise ProviderError("Provider request failed after retry") from error
        if response.status_code in (429, 500, 502, 503, 504) and attempt == 0:
            delay = min(2, max(0, as_int(response.headers.get("Retry-After"), 1)))
            await asyncio.sleep(delay)
            continue
        if response.status_code != 200:
            raise ProviderError(f"Provider returned HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as error:
            raise ProviderError("Provider returned invalid JSON") from error
    raise ProviderError("Provider request failed")


async def get_json(client: httpx.AsyncClient, path: str, params: dict[str, Any] | None = None) -> Any:
    return await request_json(client, "GET", f"{OPENDOTA_BASE_URL}{path}", params=params)


async def graphql(client: httpx.AsyncClient, query: str) -> dict[str, Any]:
    token = os.getenv("STRATZ_TOKEN")
    if not token:
        raise ProviderError("STRATZ_TOKEN is not configured")
    body = await request_json(client, "POST", STRATZ_URL, json={"query": query}, headers={
        "Authorization": f"Bearer {token}", "User-Agent": "DotaDraftHelper/1.1",
    })
    if not isinstance(body, dict) or body.get("errors") or not isinstance(body.get("data"), dict):
        raise ProviderError("STRATZ rejected the query or returned an invalid response")
    return body["data"]

async def fetch_hero_catalog(client: httpx.AsyncClient) -> dict[int, dict[str, Any]]:
    global HERO_CATALOG_CACHE, HERO_STATS_CACHE, HERO_STATS_FETCHED_AT, HERO_STATS_FETCHED_MONOTONIC
    async with CATALOG_LOCK:
        age = time.monotonic() - HERO_STATS_FETCHED_MONOTONIC
        if HERO_CATALOG_CACHE and HERO_STATS_CACHE and HERO_STATS_FETCHED_AT and age < CATALOG_TTL_SECONDS:
            return HERO_CATALOG_CACHE
        try:
            api_key = os.getenv("OPENDOTA_API_KEY")
            items = valid_rows(await get_json(client, "/heroStats", {"api_key": api_key} if api_key else {}), "heroStats")
            stats = {as_int(item.get("id")): item for item in items if as_int(item.get("id")) > 0}
            if not stats:
                raise ProviderError("Empty heroStats response")
            catalog = catalog_from_items(list(stats.values()))
        except ProviderError:
            logger.warning("Hero statistics refresh failed; using bounded stale cache or curated catalog")
            if HERO_STATS_FETCHED_AT and age <= MAX_STALE_SECONDS and HERO_CATALOG_CACHE:
                return HERO_CATALOG_CACHE
            HERO_STATS_CACHE = {}
            HERO_STATS_FETCHED_AT = None
            HERO_CATALOG_CACHE = catalog_from_items([
                {"id": hero_id, "localized_name": profile[0]} for hero_id, profile in HERO_POSITION_PROFILES.items()
            ])
            return HERO_CATALOG_CACHE
        try:
            body = await request_json(client, "GET", VALVE_HERO_LIST_URL)
            valve_heroes = valid_rows(body["result"]["data"]["heroes"], "Valve heroes")
            for item in valve_heroes:
                hero_id = as_int(item.get("id"))
                hero = catalog.get(hero_id)
                if not hero:
                    continue
                complexity = as_int(item.get("complexity"))
                if complexity in COMPLEXITY_NAMES:
                    hero["complexity"] = complexity
                    hero["complexity_name"] = COMPLEXITY_NAMES[complexity]
                if not hero.get("primary_attribute"):
                    hero["primary_attribute"] = PRIMARY_ATTRIBUTES.get(optional_int(item.get("primary_attr")))
        except (ProviderError, KeyError, TypeError):
            logger.warning("Valve enrichment unavailable; retaining known hero metadata")
        HERO_STATS_CACHE, HERO_CATALOG_CACHE = stats, catalog
        HERO_STATS_FETCHED_AT = datetime.now(timezone.utc).isoformat()
        HERO_STATS_FETCHED_MONOTONIC = time.monotonic()
        return catalog

async def fetch_stratz_meta(rank_tier: int) -> dict[str, Any]:
    token = os.getenv("STRATZ_TOKEN")
    if not token:
        raise ProviderError("STRATZ_TOKEN is not configured")

    _, requested_bracket = rank_bracket(rank_tier)
    _, bracket = meta_rank_bracket(rank_tier)
    bracket_argument = f"bracketIds: [{bracket}]" if bracket else ""
    position_queries = "\n".join(
        f"""
        p{position}: winWeek(
          take: 1
          {bracket_argument}
          positionIds: [POSITION_{position}]
        ) {{
          heroId
          matchCount
          winCount
        }}
        """
        for position in POSITION_NAMES
    )
    query = f"""
    query {{
      heroStats {{
        {position_queries}
      }}
    }}
    """
    async with httpx.AsyncClient(timeout=20.0) as client:
        body = await graphql(client, query)
    stats = body.get("heroStats")
    if not isinstance(stats, dict):
        raise ProviderError("Invalid STRATZ heroStats response")
    heroes: dict[int, dict[str, Any]] = {}
    for position in POSITION_NAMES:
        rows = valid_rows(stats.get(f"p{position}") or [], "STRATZ position meta")
        totals: dict[int, dict[str, int]] = {}
        for row in rows:
            hero_id = as_int(row.get("heroId"))
            matches = max(0, as_int(row.get("matchCount")))
            wins = min(matches, max(0, as_int(row.get("winCount"))))
            if hero_id <= 0 or matches <= 0:
                continue
            hero_total = totals.setdefault(hero_id, {"matches": 0, "wins": 0})
            hero_total["matches"] += matches
            hero_total["wins"] += wins
        position_total = sum(row["matches"] for row in totals.values())
        for hero_id, row in totals.items():
            hero_meta = heroes.setdefault(hero_id, {"positions": {}})
            hero_meta["positions"][position] = {
                "matches": row["matches"],
                "wins": row["wins"],
                "winrate": percent(row["wins"], row["matches"]),
                "pick_rate": round(row["matches"] / position_total * 100, 2)
                if position_total
                else 0.0,
            }

    if not heroes:
        raise ProviderError("STRATZ returned no weekly position meta")
    return {
        "source": "STRATZ weekly rank-and-position meta",
        "requested_rank_bracket": requested_bracket or "ALL_RANKS",
        "rank_bracket": bracket or "ALL_RANKS",
        "rank_fallback_applied": requested_bracket != bracket,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "position_data_exact": True,
        "position_mapping_version": HERO_POSITION_MAPPING_VERSION,
        "stale": False,
        "warnings": [],
        "heroes": heroes,
    }


def build_opendota_meta(
    rank_tier: int,
    heroes: list[dict[str, Any]],
) -> dict[str, Any]:
    _, requested_bracket = rank_bracket(rank_tier)
    rank_number, bracket = meta_rank_bracket(rank_tier)
    rank_rows: dict[int, dict[str, int]] = {}
    for hero in heroes:
        hero_id = as_int(hero.get("hero_id"))
        row = HERO_STATS_CACHE.get(hero_id, {})
        if rank_number:
            matches = max(0, as_int(row.get(f"{rank_number}_pick")))
            wins = min(matches, max(0, as_int(row.get(f"{rank_number}_win"))))
        else:
            matches = sum(
                max(0, as_int(row.get(f"{rank}_pick")))
                for rank in RANK_BRACKETS
            )
            wins = sum(
                max(0, as_int(row.get(f"{rank}_win")))
                for rank in RANK_BRACKETS
            )
            wins = min(matches, wins)
        if matches > 0:
            rank_rows[hero_id] = {"matches": matches, "wins": wins}

    total_rank_picks = sum(row["matches"] for row in rank_rows.values())
    meta_heroes: dict[int, dict[str, Any]] = {}
    for hero in heroes:
        hero_id = as_int(hero.get("hero_id"))
        rank_row = rank_rows.get(hero_id)
        if not rank_row:
            continue
        positions = fallback_positions(hero_id)
        matches = rank_row["matches"]
        wins = rank_row["wins"]
        pick_rate = (
            round(matches / total_rank_picks * 100, 2)
            if total_rank_picks
            else 0.0
        )
        meta_heroes[hero_id] = {
            "positions": {
                position: {
                    "matches": matches,
                    "wins": wins,
                    "winrate": percent(wins, matches),
                    "pick_rate": pick_rate,
                }
                for position in positions
            }
        }
    return {
        "source": "OpenDota rank aggregates with curated hero positions",
        "requested_rank_bracket": requested_bracket or "ALL_RANKS",
        "rank_bracket": bracket or "ALL_RANKS",
        "rank_fallback_applied": requested_bracket != bracket,
        "collected_at": HERO_STATS_FETCHED_AT,
        "stale": bool(HERO_STATS_FETCHED_AT) and time.monotonic() - HERO_STATS_FETCHED_MONOTONIC >= CATALOG_TTL_SECONDS,
        "warnings": [] if meta_heroes else ["No usable rank meta is available; recommendations are empty"],
        "position_data_exact": False,
        "position_mapping_version": HERO_POSITION_MAPPING_VERSION,
        "heroes": meta_heroes,
    }


async def fetch_current_meta(rank_tier: int, heroes: list[dict[str, Any]]) -> dict[str, Any]:
    current_patch = await refresh_current_patch()
    if os.getenv("CURRENT_META_FILE"):
        _, bracket = meta_rank_bracket(rank_tier)
        _, requested = rank_bracket(rank_tier)
        try:
            snapshot = await asyncio.to_thread(load_snapshot, os.environ["CURRENT_META_FILE"], bracket or "ALL_RANKS", current_patch, datetime.now(timezone.utc))
            snapshot["requested_rank_bracket"] = requested or "ALL_RANKS"
            snapshot["rank_fallback_applied"] = requested != bracket
            return snapshot
        except ValueError as exc:
            logger.warning("%s", exc)
            return {"source": "Invalid current-meta snapshot", "requested_rank_bracket": requested or "ALL_RANKS",
                    "rank_bracket": bracket or "ALL_RANKS", "rank_fallback_applied": requested != bracket,
                    "position_data_exact": False, "collected_at": datetime.now(timezone.utc).isoformat(),
                    "heroes": {}, "current_patch": current_patch, "warnings": [str(exc)]}
    if os.getenv("STRATZ_TOKEN"):
        cached = META_CACHE.get(rank_tier)
        if cached and time.monotonic() - cached[0] < META_TTL_SECONDS:
            return cached[1]
        try:
            meta = await fetch_stratz_meta(rank_tier)
            if len(META_CACHE) >= 9 and rank_tier not in META_CACHE:
                del META_CACHE[min(META_CACHE, key=lambda key: META_CACHE[key][0])]
            META_CACHE[rank_tier] = (time.monotonic(), meta)
            return meta
        except ProviderError:
            logger.warning("STRATZ position meta unavailable; using cached meta or OpenDota")
            if cached and time.monotonic() - cached[0] <= MAX_STALE_SECONDS:
                return {**cached[1], "stale": True, "warnings": ["STRATZ refresh failed; serving stale position meta"]}
    return build_opendota_meta(rank_tier, heroes)

async def fetch_opendota(account_id: int) -> dict[str, Any]:
    api_key = os.getenv("OPENDOTA_API_KEY")
    params = {"api_key": api_key} if api_key else {}
    async with httpx.AsyncClient(timeout=20.0) as client:
        results = await asyncio.gather(
            get_json(client, f"/players/{account_id}", params),
            get_json(client, f"/players/{account_id}/matches", {**params, "limit": 1000}),
            get_json(client, f"/players/{account_id}/wl", params),
            get_json(client, f"/players/{account_id}/recentMatches", params),
            get_json(client, f"/players/{account_id}/heroes", params),
            fetch_hero_catalog(client), return_exceptions=True,
        )
    # Programming errors remain visible, rather than being hidden by fallback.
    for result in results:
        if isinstance(result, BaseException) and not isinstance(result, ProviderError):
            raise result
    player, raw_history, wl, raw_recent, raw_heroes, catalog = results
    warnings = []
    def rows_or_empty(value, label):
        try:
            rows = valid_rows(value, label)
            if len(rows) != len(value):
                warnings.append(f"{label}: malformed rows skipped")
            return rows
        except ProviderError:
            warnings.append(f"{label} unavailable")
            return []
    history_rows = rows_or_empty(raw_history, "Match history")
    recent_rows = rows_or_empty(raw_recent, "Recent matches")
    history = bounded_matches([row for m in history_rows if (row := normalize_opendota_match(m))], 1000)
    recent = bounded_matches([row for m in recent_rows if (row := normalize_opendota_match(m, True))], 20)
    if len(history) < min(1000, len(history_rows)) or len(recent) < min(20, len(recent_rows)):
        warnings.append("Unknown outcomes, invalid IDs or duplicate matches were excluded")
    if not history and recent:
        history = [{k: m[k] for k in ("match_id", "hero_id", "is_win", "start_time")} for m in recent]
        warnings.append("History is limited to the available recent matches")
    if not history:
        raise ProviderError("OpenDota returned no usable public matches")
    if not recent:
        recent = bounded_matches([row for m in history_rows if (row := normalize_opendota_match(m, True))], 20)
        warnings.append("Recent details reconstructed from history; some metrics may be unknown")
    hero_rows = rows_or_empty(raw_heroes, "Hero statistics")
    hero_rows = [r for r in hero_rows if as_int(r.get("hero_id")) > 0 and optional_int(r.get("games")) is not None and optional_int(r.get("win")) is not None]
    if hero_rows:
        hero_scope = {"kind": "provider_aggregate", "provider": "OpenDota", "matches": sum(max(0, as_int(r.get("games"))) for r in hero_rows)}
    else:
        hero_rows = history_hero_totals(history)
        hero_scope = {"kind": "sampled_history", "provider": "OpenDota", "matches": len(history)}
        warnings.append("Hero statistics use the available match-history sample")
    if isinstance(wl, dict) and optional_int(wl.get("win")) is not None and optional_int(wl.get("lose")) is not None:
        wins, losses = max(0, as_int(wl["win"])), max(0, as_int(wl["lose"]))
        totals_scope = "provider_aggregate"
    else:
        wins = sum(m["is_win"] for m in history)
        losses = len(history) - wins
        totals_scope = "sampled_history"
        warnings.append("Total wins/losses use the available match-history sample")
    if not isinstance(player, dict):
        warnings.append("Player profile unavailable; rank is unknown")
        player = {}
    profile = player.get("profile") if isinstance(player.get("profile"), dict) else {}
    return {
        "source": "OpenDota", "player_name": profile.get("personaname") or f"Unknown_{account_id}",
        "avatar_url": steam_avatar(profile),
        "rank": as_int(player.get("rank_tier")), "total_wins": wins, "total_losses": losses,
        "history": history, "recent": recent, "player_heroes": hero_rows,
        "catalog": catalog if isinstance(catalog, dict) else HERO_CATALOG_CACHE,
        "hero_stats_scope": hero_scope, "totals_scope": totals_scope, "warnings": warnings,
    }

async def fetch_stratz(account_id: int) -> dict[str, Any]:
    if not os.getenv("STRATZ_TOKEN"):
        raise ProviderError("STRATZ_TOKEN is not configured")
    query = f"""
    query {{ player(steamAccountId: {account_id}) {{
      matchCount winCount steamAccount {{ name seasonRank }}
      history: matches(request: {{ take: 100, skip: 0 }}) {{
        id startDateTime players(steamAccountId: {account_id}) {{ isVictory heroId }}
      }}
      recent: matches(request: {{ take: 20 }}) {{
        id startDateTime durationSeconds players(steamAccountId: {account_id}) {{
          heroId isVictory kills deaths assists goldPerMinute experiencePerMinute
        }}
      }}
    }} }}
    """
    warnings = []
    async with httpx.AsyncClient(timeout=20.0) as client:
        body = await graphql(client, query)
        player = body.get("player")
        if not isinstance(player, dict):
            raise ProviderError("STRATZ returned no public player data")
        page = valid_rows(player.get("history"), "STRATZ history")
        raw_history = page[:100]
        seen = {as_int(m.get("id")) for m in raw_history}
        # Bounded pagination avoids assuming a single 1,000-match request is supported.
        for offset in range(100, 1000, 100):
            if len(page) < 100:
                break
            next_query = f"""query {{ player(steamAccountId: {account_id}) {{
              history: matches(request: {{ take: 100, skip: {offset} }}) {{
                id startDateTime players(steamAccountId: {account_id}) {{ isVictory heroId }}
              }}
            }} }}"""
            try:
                next_body = await graphql(client, next_query)
                next_player = next_body.get("player")
                if not isinstance(next_player, dict):
                    raise ProviderError("Missing STRATZ player during pagination")
                page = valid_rows(next_player.get("history"), "STRATZ history page")[:100]
            except ProviderError:
                warnings.append("STRATZ history pagination stopped after a provider failure")
                break
            unique = [m for m in page if as_int(m.get("id")) not in seen]
            if not unique and page:
                warnings.append("STRATZ repeated a history page; pagination stopped")
                break
            raw_history.extend(unique)
            seen.update(as_int(m.get("id")) for m in unique)
        catalog = await fetch_hero_catalog(client)
    history = bounded_matches([row for m in raw_history if (row := normalize_stratz_match(m))], 1000)
    if not history:
        raise ProviderError("STRATZ returned no usable completed public matches")
    try:
        raw_recent = valid_rows(player.get("recent"), "STRATZ recent matches")
    except ProviderError:
        raw_recent = []
        warnings.append("STRATZ recent match details unavailable")
    recent = bounded_matches([row for m in raw_recent if (row := normalize_stratz_match(m, True))], 20)
    if len(history) < len(raw_history) or len(recent) < min(20, len(raw_recent)):
        warnings.append("Unknown outcomes, invalid IDs or duplicate matches were excluded")
    if not recent:
        recent = [dict(m) for m in history[:20]]
        warnings.append("Recent matches use history; detailed metrics are unknown")
    account = player.get("steamAccount") if isinstance(player.get("steamAccount"), dict) else {}
    matches, wins = optional_int(player.get("matchCount")), optional_int(player.get("winCount"))
    if matches is None or wins is None or not 0 <= wins <= matches:
        matches, wins = len(history), sum(m["is_win"] for m in history)
        totals_scope = "sampled_history"
        warnings.append("Total wins/losses use the available history sample")
    else:
        totals_scope = "provider_aggregate"
    return {
        "source": "STRATZ", "player_name": account.get("name") or f"Unknown_{account_id}",
        "rank": as_int(account.get("seasonRank")), "total_wins": wins, "total_losses": matches - wins,
        "history": history, "recent": recent, "player_heroes": history_hero_totals(history),
        "catalog": catalog, "hero_stats_scope": {"kind": "sampled_history", "provider": "STRATZ", "matches": len(history)},
        "totals_scope": totals_scope, "warnings": warnings,
    }

@app.post("/sync/{account_id}")
async def sync_player(account_id: int = Path(gt=0)):
    global ACTIVE_PLAYER_CACHE, LAST_SYNC_ATTEMPT
    normalized_id = normalize_account_id(account_id)
    if SYNC_LOCK.locked():
        raise HTTPException(status_code=409, detail="A player sync is already running")
    async with SYNC_LOCK:
        elapsed = time.monotonic() - LAST_SYNC_ATTEMPT
        if elapsed < SYNC_COOLDOWN_SECONDS:
            if (ACTIVE_PLAYER_CACHE and ACTIVE_PLAYER_CACHE["account_id"] == normalized_id
                and (datetime.now(timezone.utc) - datetime.fromisoformat(ACTIVE_PLAYER_CACHE["synced_at"])).total_seconds() < SYNC_COOLDOWN_SECONDS):
                return sync_response(ACTIVE_PLAYER_CACHE, reused=True)
            raise HTTPException(status_code=429, detail="Please wait before syncing again",
                                headers={"Retry-After": str(math.ceil(SYNC_COOLDOWN_SECONDS - elapsed))})
        LAST_SYNC_ATTEMPT = time.monotonic()
        provider_errors = []
        try:
            data = await fetch_opendota(normalized_id)
        except ProviderError as error:
            provider_errors.append(f"OpenDota: {error}")
            logger.warning("OpenDota player sync failed; trying STRATZ")
            try:
                data = await fetch_stratz(normalized_id)
            except ProviderError as fallback_error:
                provider_errors.append(f"STRATZ: {fallback_error}")
                raise HTTPException(status_code=502, detail={"message": "Player sync failed", "providers": provider_errors}) from fallback_error
        heroes = build_heroes(data["player_heroes"], data["catalog"])
        favorite, best = choose_profile_heroes(heroes)
        meta = await fetch_current_meta(data["rank"], heroes)
        cache = {
            "account_id": normalized_id, "source": data["source"],
            "synced_at": datetime.now(timezone.utc).isoformat(),
            "player_name": data["player_name"], "rank": data["rank"],
            "avatar_url": data.get("avatar_url"),
            "total_wins": data["total_wins"], "total_losses": data["total_losses"],
            "history": bounded_matches(data["history"], 1000), "recent": bounded_matches(data["recent"], 20),
            "heroes": heroes, "favorite_hero": favorite, "best_hero": best, "meta": meta,
            "hero_stats_scope": data["hero_stats_scope"], "totals_scope": data["totals_scope"],
            "warnings": data.get("warnings", []) + meta.get("warnings", []) + provider_errors,
        }
        try:
            await asyncio.to_thread(save_active_player, cache)
        except Exception as error:
            logger.exception("Could not persist active player; previous player retained")
            raise HTTPException(status_code=500, detail="Could not save the active player") from error
        ACTIVE_PLAYER_CACHE = cache
        return sync_response(cache)


def sync_response(cache: dict[str, Any], reused: bool = False) -> dict[str, Any]:
    return {
        "message": "Recent sync reused" if reused else "Player synced", "cached": reused,
        "source": cache["source"], "account_id": cache["account_id"], "player_name": cache["player_name"],
        "synced_at": cache["synced_at"], "history_matches_cached": len(cache["history"]),
        "detailed_matches_cached": len(cache["recent"]), "heroes_cached": len(cache["heroes"]),
        "favorite_hero": cache["favorite_hero"], "best_hero": cache["best_hero"],
        "meta_source": cache["meta"]["source"],
        "meta_requested_rank_bracket": cache["meta"]["requested_rank_bracket"],
        "meta_rank_bracket": cache["meta"]["rank_bracket"],
        "meta_rank_fallback_applied": cache["meta"]["rank_fallback_applied"],
        "hero_stats_scope": cache.get("hero_stats_scope"), "totals_scope": cache.get("totals_scope"),
        "warnings": cache.get("warnings", []),
    }

CORE_FARM_CACHE = None
CORE_FARM_LOCK = asyncio.Lock()


def provider_match_position(match, player):
    for value in (match.get("position"), player.get("position_est")):
        position = optional_int(value)
        if position in POSITION_NAMES:
            return position
    return None


async def farming_match(client, cache, match, params):
    if match.get("position") in (4, 5) or (match.get("position") in (1, 2, 3) and match.get("last_hits") is not None and match.get("duration")):
        return match
    try:
        details = await get_json(client, f"/matches/{match['match_id']}", params)
    except ProviderError:
        return match
    players = details.get("players") if isinstance(details, dict) else None
    if not isinstance(players, list):
        return match
    player = next((row for row in players if isinstance(row, dict)
                   and optional_int(row.get("account_id")) == cache["account_id"]), None)
    if player is None:
        return match
    return {
        **match,
        "position": provider_match_position(match, player),
        "last_hits": match["last_hits"] if match.get("last_hits") is not None else optional_int(player.get("last_hits")),
        "duration": match.get("duration") or optional_int(details.get("duration")),
    }


def core_farm_summary(rows):
    buckets = {position: [] for position in (1, 2, 3)}
    missing = 0
    for row in rows:
        position = row.get("position")
        if position in (4, 5):
            continue
        hits = optional_int(row.get("last_hits"))
        duration = optional_int(row.get("duration"))
        if position not in buckets or hits is None or hits < 0 or duration is None or duration <= 0:
            missing += 1
            continue
        buckets[position].append((hits, duration))
    roles = []
    for position, games in buckets.items():
        hits = sum(hits for hits, _ in games)
        seconds = sum(duration for _, duration in games)
        roles.append({
            "position": position, "role": POSITION_NAMES[position], "matches": len(games),
            "last_hits_per_match": round(hits / len(games), 1) if games else None,
            "last_hits_per_minute": round(hits * 60 / seconds, 2) if games else None,
        })
    return {"roles": roles, "missing_data": missing, "recent_matches": len(rows)}


@app.get("/player/core-farm")
async def get_core_farm():
    global CORE_FARM_CACHE
    cache = active_cache()
    key = (cache["account_id"], cache["synced_at"])
    async with CORE_FARM_LOCK:
        if CORE_FARM_CACHE and CORE_FARM_CACHE[0] == key and time.monotonic() - CORE_FARM_CACHE[1] < 600:
            return CORE_FARM_CACHE[2]
        api_key = os.getenv("OPENDOTA_API_KEY")
        params = {"api_key": api_key} if api_key else None
        matches = cache["recent"][:20]
        limits = httpx.Limits(max_connections=4)
        async with httpx.AsyncClient(timeout=6.0, limits=limits) as client:
            rows = await asyncio.gather(*(farming_match(client, cache, match, params) for match in matches))
        result = {"account_id": cache["account_id"], **core_farm_summary(rows)}
        CORE_FARM_CACHE = (key, time.monotonic(), result)
        return result


@app.get("/player/overview")
def get_player_overview():
    return overview_payload(active_cache())


PLAYER_AVATAR_CACHE = None


@app.get("/player/avatar")
async def get_player_avatar():
    global PLAYER_AVATAR_CACHE
    cache = active_cache()
    account_id = cache["account_id"]
    if cache.get("avatar_url"):
        return {"account_id": account_id, "avatar_url": cache["avatar_url"]}
    if PLAYER_AVATAR_CACHE and PLAYER_AVATAR_CACHE[0] == account_id and time.monotonic() - PLAYER_AVATAR_CACHE[1] < 600:
        return {"account_id": account_id, "avatar_url": PLAYER_AVATAR_CACHE[2]}
    token = os.getenv("OPENDOTA_API_KEY")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            data = await get_json(client, f"/players/{account_id}", {"api_key": token} if token else None)
    except ProviderError:
        data = {}
    avatar = steam_avatar(data.get("profile") if isinstance(data, dict) else None)
    PLAYER_AVATAR_CACHE = (account_id, time.monotonic(), avatar)
    return {"account_id": account_id, "avatar_url": avatar}


@app.get("/player/heroes")
def get_player_heroes(
    played_only: bool = False,
):
    cache = active_cache()
    # Old saved snapshots may contain an earlier mapping; expose current policy.
    heroes = [{**h, **position_policy_payload(h["hero_id"])} for h in cache["heroes"]]
    if played_only:
        heroes = [hero for hero in heroes if hero["games"] > 0]
    heroes = sorted(heroes, key=lambda hero: (hero["games"], hero["winrate"]), reverse=True)
    return {
        "account_id": cache["account_id"],
        "count": len(heroes),
        "stats_scope": cache.get("hero_stats_scope"),
        "heroes": heroes,
    }


ITEM_CATALOG_CACHE = None
STARTING_BUY_CACHE = {}
STARTING_BUY_MATCH_LIMIT = 6
STARTING_BUY_WINDOW_SECONDS = 14 * 86400


async def fetch_item_catalog(client, params):
    global ITEM_CATALOG_CACHE
    if ITEM_CATALOG_CACHE and time.monotonic() - ITEM_CATALOG_CACHE[0] < 86400:
        return ITEM_CATALOG_CACHE[1]
    payload = await get_json(client, "/constants/items", params)
    if not isinstance(payload, dict):
        raise ProviderError("Item catalog is unavailable")
    catalog = {}
    for key, row in payload.items():
        if not isinstance(row, dict):
            continue
        item_id = optional_int(row.get("id"))
        cost = optional_int(row.get("cost"))
        if item_id and isinstance(row.get("dname"), str) and cost is not None and cost >= 0:
            catalog[key] = {"item_id": item_id, "name": row["dname"], "cost": cost,
                            "image_url": image_url(row.get("img")),
                            "components": row["components"] if isinstance(row.get("components"), list) else [],
                            "created": row.get("created") is True and not key.startswith("recipe_")}
    if not catalog:
        raise ProviderError("Item catalog is unavailable")
    ITEM_CATALOG_CACHE = (time.monotonic(), catalog)
    return catalog


def item_match_player(details, hero_id):
    if not isinstance(details, dict) or not isinstance(details.get("players"), list):
        return None
    return next((row for row in details["players"]
                   if isinstance(row, dict) and optional_int(row.get("hero_id")) == hero_id), None)


def observed_starting_buy(details, hero_id, catalog):
    player = item_match_player(details, hero_id)
    if not player or not isinstance(player.get("purchase_log"), list):
        return None
    items = Counter(
        item["key"] for item in player["purchase_log"]
        if isinstance(item, dict) and isinstance(item.get("key"), str) and item["key"] in catalog
        and (purchase_time := optional_int(item.get("time"))) is not None and purchase_time <= 0
    )
    cost = sum(catalog[key]["cost"] * quantity for key, quantity in items.items())
    if not items or not 0 < cost <= 600:
        return None
    return {"position": optional_int(player.get("position_est")),
            "items": tuple(sorted(items.items())), "cost": cost}


async def fetch_item_matches(client, hero_id, params, minimum_duration=0, extended=False):
    cache_key = (hero_id, minimum_duration, extended)
    cached = STARTING_BUY_CACHE.get(cache_key)
    if cached and time.monotonic() - cached[0] < CATALOG_TTL_SECONDS:
        return cached[1]
    rows = valid_rows(await get_json(client, f"/heroes/{hero_id}/matches", params), "hero matches")
    recent_cutoff = time.time() - STARTING_BUY_WINDOW_SECONDS
    cutoff = time.time() - 60 * 86400 if extended else recent_cutoff
    ids = dict.fromkeys(
        match_id for row in rows
        if (match_id := optional_int(row.get("match_id"))) and match_id > 0
        and (timestamp(row.get("start_time")) or 0) >= cutoff
        and (not extended or timestamp(row.get("start_time")) < recent_cutoff)
        and as_int(row.get("duration")) >= minimum_duration
    )
    # Limit concurrent detail reads and reuse the resulting sample for all roles.
    matches = await asyncio.gather(
        *(get_json(client, f"/matches/{match_id}", params) for match_id in list(ids)[:STARTING_BUY_MATCH_LIMIT]),
        return_exceptions=True,
    )
    samples = []
    for details in matches:
        if isinstance(details, ProviderError):
            continue
        if isinstance(details, BaseException):
            raise details
        if player := item_match_player(details, hero_id):
            inventory_fields = ("hero_id", "position_est", "purchase_log", "networth_t", "lh_t", "times", *(f"item_{i}" for i in range(6)))
            samples.append({
                "match_id": details.get("match_id"), "duration": details.get("duration"),
                "start_time": details.get("start_time"),
                "players": [{field: player.get(field) for field in inventory_fields}],
            })
    if samples:
        STARTING_BUY_CACHE[cache_key] = (time.monotonic(), samples)
    return samples


@app.get("/heroes/{hero_id}/starting-items")
async def get_starting_items(hero_id: int = Path(gt=0), position: int = Query(ge=1, le=5)):
    if hero_id not in HERO_POSITION_PROFILES:
        raise HTTPException(status_code=404, detail="Unknown hero")
    api_key = os.getenv("OPENDOTA_API_KEY")
    params = {"api_key": api_key} if api_key else None
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            catalog = await fetch_item_catalog(client, params)
            try:
                matches = await fetch_item_matches(client, hero_id, params)
                samples = [sample for match in matches if (sample := observed_starting_buy(match, hero_id, catalog))]
            except ProviderError:
                samples = []
            role_samples = [sample for sample in samples if sample["position"] == position]
            chosen = role_samples or samples
            if chosen:
                frequencies = Counter((sample["items"], sample["cost"]) for sample in chosen)
                bundles = [
                    {"items": [{**catalog[key], "quantity": quantity} for key, quantity in items],
                     "gold": cost, "observed_count": count}
                    for (items, cost), count in frequencies.most_common(2)
                ]
                return {"source": "OpenDota", "mode": "selected_position" if role_samples else "all_positions",
                        "sample_size": len(chosen), "bundles": bundles, "popular_items": []}

            payload = await get_json(client, f"/heroes/{hero_id}/itemPopularity", params)
            counts = payload.get("start_game_items") if isinstance(payload, dict) else None
            if not isinstance(counts, dict):
                raise ProviderError("Starting item data is unavailable")
            return {"source": "OpenDota", "mode": "item_popularity", "sample_size": None,
                    "bundles": [], "popular_items": most_purchased_items(counts, catalog, 8)}
        except ProviderError as error:
            raise HTTPException(status_code=502, detail="Starting item data is unavailable from OpenDota") from error


def most_purchased_items(counts, catalog, limit):
    if not isinstance(counts, dict):
        return []
    by_id = {item["item_id"]: item for item in catalog.values()}
    items = [
        {**by_id[item_id], "purchases": count}
        for key, value in counts.items()
        if (item_id := optional_int(key)) in by_id and (count := optional_int(value)) and count > 0
    ]
    return sorted(items, key=lambda item: (-item["purchases"], item["item_id"]))[:limit]


MID_INVENTORY_TIME = 35 * 60
LATE_INVENTORY_MINIMUM = 50 * 60


def finished_equipment(key, item):
    return item["cost"] >= 450 and (item["created"] or key in {"boots", "blink", "magic_stick"})


def mid_equipment(player, catalog):
    purchases = player.get("purchase_log")
    if not isinstance(purchases, list):
        return []
    held = Counter()

    def consume(key, visited):
        if key in visited or not isinstance(key, str):
            return
        if held[key] > 0:
            held[key] -= 1
            return
        for component in catalog.get(key, {}).get("components", []):
            consume(component, visited | {key})

    events = sorted(
        ((seconds, index, item["key"]) for index, item in enumerate(purchases)
         if isinstance(item, dict) and isinstance(item.get("key"), str) and item["key"] in catalog
         and (seconds := optional_int(item.get("time"))) is not None and seconds < MID_INVENTORY_TIME)
    )
    for _, _, key in events:
        for component in catalog[key]["components"]:
            consume(component, {key})
        held[key] += 1

    equipment = [
        (key, item) for key, item in catalog.items()
        if held[key] > 0 and finished_equipment(key, item)
    ]
    equipment.sort(key=lambda pair: -pair[1]["cost"])
    return [item for key, item in equipment for _ in range(held[key])][:6]


def choose_game_inventory(matches, hero_id, position, catalog, late=False):
    by_id = {item["item_id"]: (key, item) for key, item in catalog.items()}
    candidates = []
    for match in matches:
        duration = as_int(match.get("duration"))
        if duration < (LATE_INVENTORY_MINIMUM if late else MID_INVENTORY_TIME):
            continue
        player = item_match_player(match, hero_id)
        if late:
            slots = [by_id.get(optional_int(player.get(f"item_{index}"))) for index in range(6)]
            if not all(slot and finished_equipment(*slot) for slot in slots):
                continue
            items = [slot[1] for slot in slots]
        else:
            items = mid_equipment(player, catalog)
            if not items:
                continue
        candidates.append({
            "match_id": match.get("match_id"), "minute": duration // 60 if late else 35,
            "position_match": optional_int(player.get("position_est")) == position, "items": items,
            "gold": sum(item["cost"] for item in items), "start_time": timestamp(match.get("start_time")),
        })
    return next((row for row in candidates if row["position_match"]), candidates[0] if candidates else None)


def timeline_benchmarks(matches, hero_id, position, metric="gold"):
    result = []
    for minute in (10, 35, 50):
        values, role_values, seen = [], [], set()
        for match in matches:
            match_id = match.get("match_id")
            if match_id in seen or as_int(match.get("duration")) < minute * 60:
                continue
            seen.add(match_id)
            player = item_match_player(match, hero_id)
            times = player.get("times")
            timeline = player.get("networth_t" if metric == "gold" else "lh_t")
            if not isinstance(times, list) or not isinstance(timeline, list) or len(times) != len(timeline):
                continue
            point = next((optional_int(value) for t, value in zip(times, timeline) if t == minute * 60), None)
            if point is None or point < 0 or (metric == "gold" and point == 0):
                continue
            values.append(point)
            if optional_int(player.get("position_est")) == position:
                role_values.append(point)
        chosen = role_values if len(role_values) >= 3 else values
        result.append({
            "minute": minute, metric: round(median(chosen)) if len(chosen) >= 3 else None,
            "sample_size": len(chosen), "position_match": chosen is role_values,
        })
    return result


@app.get("/heroes/{hero_id}/game-items")
async def get_game_items(hero_id: int = Path(gt=0), position: int = Query(ge=1, le=5)):
    if hero_id not in HERO_POSITION_PROFILES:
        raise HTTPException(status_code=404, detail="Unknown hero")
    key = os.getenv("OPENDOTA_API_KEY")
    params = {"api_key": key} if key else None
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            catalog = await fetch_item_catalog(client, params)
            mid, late = await asyncio.gather(
                fetch_item_matches(client, hero_id, params),
                fetch_item_matches(client, hero_id, params, LATE_INVENTORY_MINIMUM),
            )
            mid_inventory = choose_game_inventory(mid, hero_id, position, catalog)
            late_inventory = choose_game_inventory(late, hero_id, position, catalog, late=True)
            if not mid_inventory or timeline_benchmarks(mid + late, hero_id, position)[1]["gold"] is None:
                expanded = await fetch_item_matches(client, hero_id, params, MID_INVENTORY_TIME, extended=True)
                mid = mid + expanded
                mid_inventory = choose_game_inventory(mid, hero_id, position, catalog)
            if not late_inventory or timeline_benchmarks(mid + late, hero_id, position)[2]["gold"] is None:
                expanded = await fetch_item_matches(client, hero_id, params, LATE_INVENTORY_MINIMUM, extended=True)
                late = late + expanded
                late_inventory = choose_game_inventory(late, hero_id, position, catalog, late=True)
        except ProviderError as error:
            raise HTTPException(status_code=502, detail="Inventory data is unavailable from OpenDota") from error
    return {
        "mid": mid_inventory, "late": late_inventory,
        "benchmarks": timeline_benchmarks(mid + late, hero_id, position),
        "last_hits_benchmarks": timeline_benchmarks(mid + late, hero_id, position, "last_hits"),
    }


@app.get("/heroes/positions")
def get_hero_positions():
    """Complete reviewed whitelist, available before syncing a player."""
    return {"mapping_version": HERO_POSITION_MAPPING_VERSION,
            "audience": "2000-4000 MMR pubs",
            "scope": "curated product policy, not an empirical current-patch role census",
            "heroes": [{"hero_id": hero_id, "name": profile[0],
                        **position_policy_payload(hero_id)}
                       for hero_id, profile in sorted(HERO_POSITION_PROFILES.items())]}


@app.get("/player/trends")
async def get_player_trends(
    request: Request,
    limit: int = Query(default=10, ge=1, le=10),
    position: int | None = Query(default=None, ge=1, le=5),
    meta_rank: int | None = Query(default=None, ge=3, le=6),
    unavailable_hero_ids: list[int] | None = Query(default=None, max_length=40),
    allow_historical_meta: bool = False,
    allow_historical_learning: bool = False,
):
    unknown = set(request.query_params) - {
        "limit", "position", "meta_rank", "unavailable_hero_ids", "allow_historical_meta", "allow_historical_learning",
    }
    if unknown:
        raise HTTPException(status_code=422, detail={
            "message": "Use position=1..5 to select a role, for example /player/trends?position=4",
            "unsupported_parameters": sorted(unknown),
        })
    if len(request.query_params.getlist("position")) > 1:
        raise HTTPException(status_code=422, detail="Send exactly one position parameter")
    if len(request.query_params.getlist("meta_rank")) > 1:
        raise HTTPException(status_code=422, detail="Send exactly one meta_rank parameter")
    for flag in ("allow_historical_meta", "allow_historical_learning"):
        if len(request.query_params.getlist(flag)) > 1:
            raise HTTPException(status_code=422, detail=f"Send exactly one {flag} parameter")
    allow_historical_meta = allow_historical_meta or allow_historical_learning
    cache = active_cache()
    unavailable_ids = set(unavailable_hero_ids or [])
    known_ids = {h["hero_id"] for h in cache["heroes"]}
    if not unavailable_ids <= known_ids or any(h <= 0 for h in unavailable_ids):
        raise HTTPException(status_code=422, detail="Unavailable heroes must use known positive hero IDs")
    if meta_rank is None:
        cache = await recommendation_cache(cache)
    else:
        # Request-local bracket: do not replace the active player's meta snapshot.
        # Catalog/statistics refresh is bounded by the shared catalog TTL.
        async with httpx.AsyncClient(timeout=20.0) as client:
            await fetch_hero_catalog(client)
        override_meta = await fetch_current_meta(meta_rank * 10, cache["heroes"])
        cache = {**cache, "meta": override_meta}
    await refresh_current_patch()
    result = build_recommendations(cache, limit, position, unavailable_ids,
                                   allow_historical_meta=allow_historical_meta,
                                   allow_historical_learning=allow_historical_learning)
    selected_rank = cache["rank"] if meta_rank is None else meta_rank * 10
    observed = None
    if allow_historical_meta and result["meta"]["evidence_mode"] != "verified_current":
        observed = load_role_sample(rank_bracket(selected_rank)[1], HERO_POSITION_PROFILES, datetime.now(timezone.utc))
        if observed:
            result = build_recommendations({**cache, "meta": observed}, limit, position, unavailable_ids,
                                           allow_historical_meta=True, allow_historical_learning=allow_historical_learning)
    if allow_historical_meta and result["meta"]["evidence_mode"] == "unavailable":
        # A configured snapshot can be invalid or for another rank. Use the
        # independent provider aggregate without replacing the saved meta.
        if meta_rank is None:
            async with httpx.AsyncClient(timeout=20.0) as client:
                await fetch_hero_catalog(client)
        fallback_rank = cache["rank"] if meta_rank is None else meta_rank * 10
        fallback_meta = build_opendota_meta(fallback_rank, cache["heroes"])
        fallback = build_recommendations({**cache, "meta": fallback_meta}, limit, position,
                                         unavailable_ids, allow_historical_meta=True,
                                         allow_historical_learning=allow_historical_learning)
        if fallback["meta"]["evidence_mode"] == "historical":
            result = fallback
    role_candidates = []
    target_position = result["target_position"]
    if observed and target_position in DOTABUFF_ROLES:
        personal = recent_role_evidence(cache, target_position, datetime.now(timezone.utc))
        for hero_id, row in observed["heroes"].items():
            stats = row["positions"].get(target_position)
            if stats:
                evidence = personal.get(hero_id, {})
                games = evidence.get("role_games", 0)
                role_candidates.append({
                    "hero_id": hero_id, "name": HERO_POSITION_PROFILES[hero_id][0], **stats,
                    "player_role_games": games,
                    "player_role_winrate": percent(evidence["role_wins"], games) if games else None,
                })
        role_candidates.sort(key=lambda entry: -entry["matches"])
        result["meta"]["source_url"] += "&position=" + DOTABUFF_ROLES[target_position]
    return {
        "account_id": cache["account_id"],
        "best_hero": cache["best_hero"],
        "scoring_version": SCORING_VERSION,
        "requested_position": position,
        "requested_meta_rank": meta_rank,
        "role_candidates": role_candidates,
        **result,
    }


@app.get("/player/winrate-history")
def get_player_winrate_history():
    return winrate_history_payload(active_cache())


@app.get("/player/yearly")
def get_legacy_player_yearly():
    return get_player_winrate_history()


def serialize_player_matches(cache: dict[str, Any], matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    heroes = {hero["hero_id"]: hero for hero in cache["heroes"]}
    rows = []
    for match in matches:
        hero_id = match.get("hero_id")
        hero = heroes.get(hero_id, {})
        rows.append({
            **serialize_match(match),
            "hero_name": hero.get("name") or (f"Hero {hero_id}" if hero_id else "Unknown hero"),
            "hero_image_url": hero.get("icon_url") or hero.get("image_url"),
        })
    return rows


@app.get("/player/matches")
def get_player_matches(
    limit: int = Query(default=5, ge=1, le=20),
    offset: int = Query(default=0, ge=0),
):
    cache = active_cache()
    recent = cache["recent"]
    page = recent[offset : offset + limit]
    return {
        "account_id": cache["account_id"],
        "total": len(recent),
        "limit": limit,
        "offset": offset,
        "has_more": offset + limit < len(recent),
        "matches": serialize_player_matches(cache, page),
    }


def match_performance_metrics(match: dict[str, Any]) -> dict[str, int | float | None]:
    metrics = {}
    for key in ("kills", "deaths", "assists", "gpm", "xpm"):
        value = optional_int(match.get(key))
        metrics[key] = value if value is not None and value >= 0 else None
    kills, deaths, assists = (metrics[key] for key in ("kills", "deaths", "assists"))
    metrics["kda"] = (
        (kills + assists) / max(1, deaths)
        if kills is not None and deaths is not None and assists is not None
        else None
    )
    return metrics


@app.get("/player/matches/{match_id}")
def get_player_match(match_id: int = Path(gt=0)):
    cache = active_cache()
    recent = cache["recent"]
    match = next((row for row in recent if row["match_id"] == match_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail="This match is outside the player's synced recent matches")

    other_matches = [match_performance_metrics(row) for row in recent if row["match_id"] != match_id]
    comparison = {}
    for key, value in match_performance_metrics(match).items():
        samples = [row[key] for row in other_matches if row[key] is not None]
        average = round(sum(samples) / len(samples), 2) if samples else None
        value = round(value, 2) if value is not None else None
        comparison[key] = {
            "value": value,
            "average": average,
            "delta": round(value - average, 2) if value is not None and average is not None else None,
            "sample_size": len(samples),
        }

    return {
        "account_id": cache["account_id"],
        "match": serialize_player_matches(cache, [match])[0],
        "comparison": comparison,
        "baseline_match_count": len(other_matches),
    }


def all_pick_draft(ordered, own_team, heroes):
    by_phase = []
    picks = []
    bans = set()
    seen = set()
    for event in ordered:
        hero_id = optional_int(event.get("hero_id"))
        if hero_id is None or hero_id <= 0 or hero_id in seen:
            return None
        seen.add(hero_id)
        if event["is_pick"]:
            team = optional_int(event.get("team"))
            hero = heroes.get((team, hero_id))
            if hero is None:
                return None
            picks.append((team, hero))
        else:
            bans.add(hero_id)
    if len(picks) != 10:
        return None

    for phase in (picks[:4], picks[4:8], picks[8:]):
        team_count = sum(team == own_team for team, _ in phase)
        if team_count * 2 != len(phase):
            return None
        by_phase.append(phase)

    result, revealed = [], []
    unavailable = set(bans)
    for phase_number, phase in enumerate(by_phase, 1):
        for team, hero in phase:
            allied = team == own_team
            result.append({
                "phase": phase_number, "allied": allied, "hero": hero,
                "enemies_revealed": list(revealed) if allied else None,
                "unavailable_hero_ids": sorted(unavailable) if allied else None,
            })
        # All picks are revealed together after the phase.
        revealed.extend(hero for team, hero in phase if team != own_team)
        unavailable.update(hero["hero_id"] for _, hero in phase)
    return {"format": "all_pick", "picks": result, "last_pick_allied": None}


def match_draft(details, own_team, allies, enemies):
    events = details.get("picks_bans")
    mode = details.get("game_mode")
    if mode not in (2, 22) or not isinstance(events, list):
        return None
    # 7.27 introduced the 2–2–1 format on June 28, 2020.
    if mode == 22 and (timestamp(details.get("start_time")) or 0) < 1593302400:
        return None

    heroes = {
        (team, hero["hero_id"]): hero
        for team, lineup in ((own_team, allies), (1 - own_team, enemies))
        for hero in lineup
    }
    if len(allies) != 5 or len(enemies) != 5 or len(heroes) != 10:
        return None

    ordered = {}
    for event in events:
        if not isinstance(event, dict):
            return None
        order = optional_int(event.get("order"))
        if order is None or order < 0 or order in ordered or not isinstance(event.get("is_pick"), bool):
            return None
        ordered[order] = event
    if sorted(ordered) != list(range(len(ordered))):
        return None

    ordered_events = [ordered[order] for order in range(len(ordered))]
    if mode == 22:
        return all_pick_draft(ordered_events, own_team, heroes)

    picks, revealed = [], []
    unavailable = set()
    phase, previous_was_pick = 0, False
    for event in ordered_events:
        hero_id = optional_int(event.get("hero_id"))
        if hero_id is None or hero_id <= 0 or hero_id in unavailable:
            return None
        if not event["is_pick"]:
            unavailable.add(hero_id)
            previous_was_pick = False
            continue
        team = optional_int(event.get("team"))
        hero = heroes.pop((team, hero_id), None)
        if hero is None:
            return None
        if not previous_was_pick:
            phase += 1
        previous_was_pick = True
        allied = team == own_team
        picks.append({
            "phase": phase, "allied": allied, "hero": hero,
            "enemies_revealed": list(revealed) if allied else None,
            "unavailable_hero_ids": sorted(unavailable) if allied else None,
        })
        unavailable.add(hero_id)
        if not allied:
            revealed.append(hero)
    if heroes:
        return None
    return {"format": "captains_mode", "picks": picks, "last_pick_allied": picks[-1]["allied"]}


@app.get("/player/matches/{match_id}/lineups")
async def get_match_lineups(match_id: int = Path(gt=0)):
    return await load_match_lineups(active_cache(), match_id)


async def load_match_lineups(cache: dict[str, Any], match_id: int):
    match = next((row for row in cache["recent"] if row["match_id"] == match_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail="This match is outside the player's synced recent matches")

    key = os.getenv("OPENDOTA_API_KEY")
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            details = await get_json(client, f"/matches/{match_id}", {"api_key": key} if key else None)
        players = valid_rows(details.get("players") if isinstance(details, dict) else None, "match players")
    except ProviderError as error:
        raise HTTPException(status_code=502, detail="Match lineups are unavailable from OpenDota") from error

    slots = {}
    for player in players:
        slot = optional_int(player.get("player_slot"))
        hero_id = optional_int(player.get("hero_id"))
        if slot is not None and 0 <= slot <= 255 and hero_id is not None and hero_id > 0:
            slots[slot] = (hero_id, optional_int(player.get("account_id")) == cache["account_id"])

    own_slot = next((slot for slot, (_, is_you) in slots.items() if is_you), None)
    if own_slot is None:
        raise HTTPException(status_code=404, detail="OpenDota could not identify your team for this match")

    catalog = {hero["hero_id"]: hero for hero in cache["heroes"]}
    allies, enemies = [], []
    for slot, (hero_id, is_you) in sorted(slots.items()):
        hero = catalog.get(hero_id, {})
        lineup = allies if (slot < 128) == (own_slot < 128) else enemies
        lineup.append({
            "slot": slot, "hero_id": hero_id, "is_you": is_you,
            "name": hero.get("name") or f"Hero {hero_id}",
            "image_url": hero.get("image_url") or hero.get("icon_url"),
        })

    own_player = next(row for row in players if optional_int(row.get("account_id")) == cache["account_id"])
    position = provider_match_position(match, own_player)
    return {
        "account_id": cache["account_id"], "side": "Radiant" if own_slot < 128 else "Dire",
        "player_position": position, "player_position_name": POSITION_NAMES.get(position),
        "allies": allies, "enemies": enemies,
        "draft": match_draft(details, int(own_slot >= 128), allies, enemies),
    }


DRAFT_MATCHUPS_CACHE = {}


async def fetch_enemy_matchups(client, enemy_id, params):
    cached = DRAFT_MATCHUPS_CACHE.get(enemy_id)
    if cached and time.monotonic() - cached[0] < CATALOG_TTL_SECONDS:
        return cached[1]
    try:
        rows = valid_rows(await get_json(client, f"/heroes/{enemy_id}/matchups", params), "hero matchups")
    except ProviderError:
        return {}
    matchups = {}
    for row in rows:
        hero_id = optional_int(row.get("hero_id"))
        games = optional_int(row.get("games_played"))
        enemy_wins = optional_int(row.get("wins"))
        if hero_id and games and games > 0 and enemy_wins is not None and 0 <= enemy_wins <= games:
            matchups[hero_id] = (games - enemy_wins, games)
    if matchups:
        if len(DRAFT_MATCHUPS_CACHE) >= 128 and enemy_id not in DRAFT_MATCHUPS_CACHE:
            del DRAFT_MATCHUPS_CACHE[min(DRAFT_MATCHUPS_CACHE, key=lambda hero_id: DRAFT_MATCHUPS_CACHE[hero_id][0])]
        DRAFT_MATCHUPS_CACHE[enemy_id] = (time.monotonic(), matchups)
    return matchups


@app.get("/player/matches/{match_id}/draft-recommendations")
async def get_draft_recommendations(
    match_id: int = Path(gt=0), position: int | None = Query(default=None, ge=1, le=5),
):
    cache = active_cache()
    lineups = await load_match_lineups(cache, match_id)
    draft = lineups["draft"]
    own_pick = next((pick for pick in draft["picks"] if pick["hero"]["is_you"]), None) if draft else None
    if own_pick is None:
        raise HTTPException(status_code=404, detail="A complete public draft is required for pick recommendations")

    match = next(row for row in cache["recent"] if row["match_id"] == match_id)
    position_source = "selected"
    if position is None:
        position = lineups["player_position"]
        position_source = "match_estimate"
        if position is None:
            position = next(iter(curated_positions(own_pick["hero"]["hero_id"])), None)
            position_source = "hero_default"
    if position is None:
        raise HTTPException(status_code=422, detail="Select a position for this pick")

    enemies = own_pick["enemies_revealed"]
    key = os.getenv("OPENDOTA_API_KEY")
    params = {"api_key": key} if key else None
    async with httpx.AsyncClient(timeout=8.0) as client:
        await fetch_hero_catalog(client)
        matchup_rows = await asyncio.gather(*(fetch_enemy_matchups(client, enemy["hero_id"], params) for enemy in enemies))
    cache = await recommendation_cache(cache)
    current = await refresh_current_patch()
    meta = cache["meta"]
    verified = (
        meta.get("position_data_exact") and meta.get("rank_bracket") in RANK_BRACKETS.values()
        and meta_age_seconds(meta) <= MAX_STALE_SECONDS
        and temporal_evidence(meta, datetime.now(timezone.utc), current)["verified"]
    )
    if not verified:
        meta = (load_role_sample(rank_bracket(cache["rank"])[1], HERO_POSITION_PROFILES, datetime.now(timezone.utc))
                or usable_meta(build_opendota_meta(cache["rank"], cache["heroes"])))

    # Compare with the player's available history from before this draft.
    start = timestamp(match.get("start_time"))
    prior_matches = [
        row for row in cache["history"]
        if row["match_id"] != match_id and start and (played := timestamp(row.get("start_time"))) and played < start
    ]
    experience = {row["hero_id"]: (row["wins"], row["games"]) for row in history_hero_totals(prior_matches)}
    eligible = {hero["hero_id"] for hero in cache["heroes"]
                if position in (curated_positions(hero["hero_id"]) if verified else fallback_positions(hero["hero_id"]))
                and (position not in CONDITIONAL_POSITIONS.get(hero["hero_id"], set())
                     or (verified and not meta.get("rank_fallback_applied")))}
    if meta.get("dotabuff_role_sample"):
        eligible = {hero_id for hero_id, row in meta["heroes"].items() if position in row["positions"]}
    eligible -= set(own_pick["unavailable_hero_ids"])
    # Matchup baselines use the same endpoint and scope as the pair evidence.
    # Bounded concurrency and the existing one-hour cache limit provider load.
    semaphore = asyncio.Semaphore(3)

    async def baseline(hero_id, client):
        async with semaphore:
            return hero_id, population_rate(await fetch_enemy_matchups(client, hero_id, params))

    async with httpx.AsyncClient(timeout=8.0) as client:
        baseline_rates = dict(await asyncio.gather(
            *(baseline(hero_id, client) for hero_id in eligible | {e["hero_id"] for e in enemies})
        )) if enemies else {}
    ranked = rank_draft_picks(
        cache["heroes"], eligible,
        meta["heroes"], position, bool(verified), enemies, matchup_rows, experience,
        baseline_rates=baseline_rates,
    )
    return {
        "account_id": cache["account_id"], "position": position, "position_name": POSITION_NAMES[position],
        "position_source": position_source,
        "meta_verified_current": bool(verified), "meta_rank": meta.get("rank_bracket"),
        "meta_rank_fallback": meta.get("rank_fallback_applied", False),
        "dotabuff_role_sample": bool(meta.get("dotabuff_role_sample")),
        "enemies_revealed": enemies, "recommendations": ranked,
        "matchup_model": "population-adjusted-odds-v1",
        "matchup_scope": "OpenDota matchup aggregates; no rank, role or patch filter. "
                         "Expected rates use both heroes' aggregate strength from the same endpoint.",
        "baseline_coverage": sum(value is not None for value in baseline_rates.values()),
    }


def player_stats_payload(cache: dict[str, Any], recent_limit: int = 5) -> dict[str, Any]:
    overview = overview_payload(cache)
    recent = serialize_player_matches(cache, cache["recent"][:recent_limit])
    most_played = sorted(cache["heroes"], key=lambda hero: hero["games"], reverse=True)[:5]
    winrate_history = winrate_history_payload(cache)
    return {
        "player_info": {
            "account_id": overview["account_id"],
            "name": overview["name"],
            "rank": overview["rank"],
        },
        "overview": overview,
        "recent_performance_chart": ["W" if match["is_win"] else "L" for match in cache["recent"]],
        "winrate_trend": winrate_history["winrates"],
        "winrate_history": winrate_history,
        "recent_matches": recent,
        "most_played_heroes": most_played,
        "favorite_hero": cache["favorite_hero"],
        "best_hero": cache["best_hero"],
    }


@app.get("/player/stats")
def get_player_stats(recent_limit: int = Query(default=5, ge=1, le=20)):
    return player_stats_payload(active_cache(), recent_limit)


@app.get("/player/{account_id}/stats")
def get_legacy_player_stats(account_id: int = Path(gt=0)):
    cache = active_cache()
    if normalize_account_id(account_id) != cache["account_id"]:
        raise HTTPException(status_code=404, detail="This is not the active player")
    return player_stats_payload(cache)
