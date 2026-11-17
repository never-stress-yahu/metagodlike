"""Rank available picks using population data and pre-match player history."""
from math import isfinite, log1p

from recommendation_context import hero_learning_cost


def rank_draft_picks(heroes, eligible, meta, position, verified, enemies, matchup_rows, experience):
    ranked = []
    for hero in heroes:
        hero_id = hero["hero_id"]
        if hero_id not in eligible:
            continue
        positions = meta.get(hero_id, {}).get("positions", {})
        row = positions.get(position, {})
        games, winrate = row.get("matches", 0), row.get("winrate")
        if games < 200 or not isinstance(winrate, (int, float)) or not isfinite(winrate) or not 0 <= winrate <= 100:
            continue
        if verified and games / sum(stats["matches"] for stats in positions.values()) < 0.10:
            continue

        matches = []
        for enemy, results in zip(enemies, matchup_rows):
            wins, sample = results.get(hero_id, (0, 0))
            if sample >= 20:
                edge = 100 * (wins - sample / 2) / (sample + 50)
                matches.append({
                    "enemy": enemy["name"], "games": sample,
                    "winrate": round(100 * wins / sample, 2), "edge": round(edge, 2),
                })
        # Require evidence for a majority of revealed opponents. Missing pairs
        # contribute zero to the mean and remain visible as missing coverage.
        if enemies and len(matches) * 2 <= len(enemies):
            continue
        edges = [match["edge"] for match in matches]
        matchup = sum(edges) / len(enemies) if enemies else 0
        risk = min(0, *edges) if edges else 0
        personal_wins, personal_games = experience.get(hero_id, (0, 0))
        meta_score = 2 * (winrate - 50) * games / (games + 500) * (1 if verified else 0.6)
        matchup_score = 2 * matchup
        risk_score = risk
        personal_score = max(-3, min(3, 60 * (personal_wins - personal_games / 2) / (personal_games + 40)))
        familiarity = 2 * min(1, log1p(personal_games) / log1p(100))
        learning_cost = hero_learning_cost(hero.get("complexity"), personal_games)
        ranked.append({
            "hero_id": hero_id, "name": hero["name"], "icon_url": hero.get("icon_url"),
            "score": round(meta_score + matchup_score + risk_score + personal_score + familiarity - learning_cost, 2),
            "complexity_name": hero.get("complexity_name"),
            "meta_winrate": winrate, "meta_games": games,
            "player_games": personal_games,
            "player_winrate": round(100 * personal_wins / personal_games, 2) if personal_games else None,
            "matchups": sorted(matches, key=lambda match: -match["edge"]),
            "score_breakdown": {
                "meta": round(meta_score, 2), "matchups": round(matchup_score, 2),
                "worst_matchup": round(risk_score, 2), "personal": round(personal_score, 2),
                "familiarity": round(familiarity, 2),
                "learning_cost": round(-learning_cost, 2),
            },
        })
    return sorted(ranked, key=lambda row: (-row["score"], -row["meta_games"], row["hero_id"]))[:3]
