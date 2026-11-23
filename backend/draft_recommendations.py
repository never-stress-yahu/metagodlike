"""Rank available picks using population data and pre-match player history."""
from math import isfinite, log1p

from recommendation_context import hero_learning_cost


def population_rate(opponent_results):
    """Rows contain opponents' wins against this hero; each match appears per enemy."""
    games = sum(sample for _, sample in opponent_results.values())
    if not games:
        return None
    wins = sum(sample - opponent_wins for opponent_wins, sample in opponent_results.values())
    return wins / games


def expected_matchup(candidate_rate, enemy_rate):
    """Independent hero-strength baseline on the odds scale."""
    numerator = candidate_rate * (1 - enemy_rate)
    denominator = numerator + (1 - candidate_rate) * enemy_rate
    return numerator / denominator if denominator else 0.5


def rank_draft_picks(heroes, eligible, meta, position, verified, enemies, matchup_rows, experience,
                    *, baseline_rates=None, limit=3):
    # None explicitly retains the original score for reproducible ablations.

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
            expected = 0.5
            if baseline_rates is not None:
                candidate_rate = baseline_rates.get(hero_id)
                enemy_rate = baseline_rates.get(enemy.get("hero_id"))
                if candidate_rate is None or enemy_rate is None:
                    continue
                expected = expected_matchup(candidate_rate, enemy_rate)
            if sample >= 20:
                edge = 100 * (wins - sample * expected) / (sample + 50)
                matches.append({
                    "enemy": enemy["name"], "games": sample,
                    "winrate": round(100 * wins / sample, 2), "edge": round(edge, 2),
                    "expected_winrate": round(100 * expected, 2),
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
    return sorted(ranked, key=lambda row: (-row["score"], -row["meta_games"], row["hero_id"]))[:limit]
