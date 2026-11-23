from draft_recommendations import expected_matchup, population_rate, rank_draft_picks


def test_expected_rate_accounts_for_both_heroes():
    assert expected_matchup(.58, .5) == .58
    assert expected_matchup(.58, .58) == .5
    assert expected_matchup(.5, .58) < .5


def test_adjusted_edge_can_be_negative_above_fifty_percent():
    heroes = [{"hero_id": 1, "name": "Candidate", "complexity": 1}]
    args = (heroes, {1}, {1: {"positions": {2: {"matches": 1000, "winrate": 58}}}},
            2, True, [{"hero_id": 2, "name": "Opponent"}], [{1: (53, 100)}], {})
    pick = rank_draft_picks(*args, baseline_rates={1: .58, 2: .5})[0]
    assert pick["matchups"][0]["edge"] < 0
    assert pick["matchups"][0]["expected_winrate"] == 58
    assert rank_draft_picks(*args, baseline_rates={}) == []


def test_population_baseline_inverts_opponents_wins():
    assert population_rate({2: (40, 100), 3: (80, 200)}) == .6
    assert population_rate({}) is None

def test_walk_forward_predictions_ignore_later_outcomes():
    from research.evaluate import personal_predictions
    rows = [{"match_id": i, "hero_id": 1, "start_time": i * 86400,
             "is_win": i % 2 == 0} for i in range(1, 21)]
    before = personal_predictions(rows)
    changed = [dict(row) for row in rows]
    changed[-1]["is_win"] = not changed[-1]["is_win"]
    after = personal_predictions(changed)
    assert [r["predictions"] for r in before] == [r["predictions"] for r in after]
    assert before[-1]["outcome"] != after[-1]["outcome"]
    assert personal_predictions(rows + [rows[-1]]) == before

def test_http_draft_uses_adjusted_model_and_discloses_scope(monkeypatch):
    import json
    from pathlib import Path
    from unittest.mock import AsyncMock
    from fastapi.testclient import TestClient
    import main

    evidence = json.loads((Path(__file__).resolve().parents[1] / "data/research/drafts.json").read_text(encoding="utf8"))
    case = evidence["cases"][0]
    meta = dict(evidence["meta"])
    meta["heroes"] = {int(k): {"positions": {int(p): v for p, v in row["positions"].items()}}
                      for k, row in meta["heroes"].items()}
    tables = {int(k): {int(h): tuple(pair) for h, pair in rows.items()}
              for k, rows in evidence["matchups"].items()}
    cache = {"account_id": 1, "rank": 80, "heroes": evidence["heroes"], "meta": meta,
             "recent": [{"match_id": case["match_id"], "start_time": case["start_time"]}], "history": []}
    monkeypatch.setattr(main, "active_cache", lambda: cache)
    monkeypatch.setattr(main, "load_match_lineups", AsyncMock(return_value=case["lineups"]))
    monkeypatch.setattr(main, "fetch_hero_catalog", AsyncMock())
    monkeypatch.setattr(main, "recommendation_cache", AsyncMock(return_value=cache))
    monkeypatch.setattr(main, "refresh_current_patch", AsyncMock(return_value={}))
    monkeypatch.setattr(main, "load_role_sample", lambda *args: None)
    monkeypatch.setattr(main, "build_opendota_meta", lambda *args: meta)
    monkeypatch.setattr(main, "fallback_positions", lambda hero: [case["position"]] if hero in case["eligible"] else [])
    monkeypatch.setattr(main, "CONDITIONAL_POSITIONS", {})

    async def matchups(client, hero, params):
        return tables.get(hero, {})

    monkeypatch.setattr(main, "fetch_enemy_matchups", matchups)
    client = TestClient(main.app)
    response = client.get(f'/player/matches/{case["match_id"]}/draft-recommendations?position={case["position"]}')
    assert response.status_code == 200
    body = response.json()
    assert body["matchup_model"] == "population-adjusted-odds-v1"
    assert "no rank, role or patch filter" in body["matchup_scope"]
    assert len(body["recommendations"]) == 3
    assert any(pair["expected_winrate"] != 50
               for hero in body["recommendations"] for pair in hero["matchups"])
