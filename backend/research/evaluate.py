"""Reproduce frozen evaluations and generate the browser demo without network access."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
from statistics import mean
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from draft_recommendations import population_rate, rank_draft_picks

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/research"
WEIGHTS = (10, 20, 40, 80)


def personal_predictions(matches):
    matches = sorted({m["match_id"]: m for m in matches}.values(), key=lambda m: (m["start_time"], m["match_id"]))
    history = defaultdict(list)
    predictions = []
    for index, match in enumerate(matches):
        time, hero, won = match["start_time"], match["hero_id"], int(match["is_win"])
        past = [(2 ** (-(time - t) / (30 * 86400)), y)
                for t, y in history[hero] if 0 < time - t <= 90 * 86400]
        history[hero].append((time, won))
        if not past or index < int(len(matches) * .6):
            continue
        games = sum(w for w, _ in past)
        wins = sum(w * y for w, y in past)
        values = {"neutral": .5, "personal": wins / games}
        values.update({str(weight): (wins + weight * .5) / (games + weight) for weight in WEIGHTS})
        predictions.append({
            "split": "validation" if index < int(len(matches) * .8) else "test",
            "outcome": won, "predictions": values,
        })
    return predictions


def errors(rows, split):
    selected = [r for r in rows if r["split"] == split]
    return {name: mean((r["predictions"][name] - r["outcome"]) ** 2 for r in selected)
            for name in ("neutral", "personal", *(str(w) for w in WEIGHTS))} if selected else {}


def draft_comparison(evidence):
    meta = {int(k): {"positions": {int(p): v for p, v in row["positions"].items()}}
            for k, row in evidence["meta"]["heroes"].items()}
    tables = {int(k): {int(h): tuple(pair) for h, pair in rows.items()}
              for k, rows in evidence["matchups"].items()}
    rates = {hero: population_rate(rows) for hero, rows in tables.items()}
    output = []
    for case in evidence["cases"]:
        args = (evidence["heroes"], set(case["eligible"]), meta, case["position"], False,
                case["enemies"], [tables[e["hero_id"]] for e in case["enemies"]],
                {int(k): tuple(v) for k, v in case["experience"].items()})
        full = rank_draft_picks(*args, baseline_rates=rates, limit=len(evidence["heroes"]))
        raw = {h["hero_id"]: h for h in rank_draft_picks(*args, limit=len(evidence["heroes"]))}
        variants = {}
        for name, keys in {
            "population": ("meta",),
            "personal": ("meta", "personal", "familiarity", "learning_cost"),
            "full": tuple(full[0]["score_breakdown"]) if full else (),
        }.items():
            ranked = []
            for hero in full:
                row = dict(hero)
                row["score"] = round(sum(hero["score_breakdown"][key] for key in keys), 2)
                if name == "full":
                    row["score"] = hero["score"]
                row["score_breakdown"] = {k: v if k in keys else 0
                                          for k, v in hero["score_breakdown"].items()}
                ranked.append(row)
            variants[name] = sorted(ranked, key=lambda h: (-h["score"], -h["meta_games"], h["hero_id"]))[:3]
        variants["raw"] = sorted((raw[h["hero_id"]] for h in full),
                                 key=lambda h: (-h["score"], -h["meta_games"], h["hero_id"]))[:3]
        output.append({
            "match_id": case["match_id"], "position": case["position"], "actual_hero": case["actual_hero"],
            "position_source": case["position_source"], "lineups": case["lineups"],
            "enemies": case["enemies"], "eligible_count": len(case["eligible"]),
            "scored_count": len(full), "variants": variants,
        })
    return output


def run():
    histories = json.loads((DATA / "personal-history.json").read_text(encoding="utf8"))
    players = {p["player"]: personal_predictions(p["matches"]) for p in histories["players"]}
    validation = {name: errors(rows, "validation") for name, rows in players.items()}
    usable = [scores for scores in validation.values() if scores]
    if not usable:
        raise ValueError("No validation predictions")
    selected = min(WEIGHTS, key=lambda w: (mean(s[str(w)] for s in usable), w))
    report = {
        "selected_weight": selected, "selection": "Lowest mean per-player validation Brier; chronological 60/20/20",
        "input_sha256": {name: hashlib.sha256((DATA / name).read_text(encoding="utf8").encode("utf8")).hexdigest()
                         for name in ("personal-history.json", "drafts.json")},
        "players": {name: {
            "validation_count": sum(r["split"] == "validation" for r in rows),
            "test_count": sum(r["split"] == "test" for r in rows),
            "validation": validation[name], "test": errors(rows, "test"),
        } for name, rows in players.items()},
    }
    evidence = json.loads((DATA / "drafts.json").read_text(encoding="utf8"))
    cases = draft_comparison(evidence)
    report["drafts"] = [{"match_id": c["match_id"], "eligible": c["eligible_count"],
                         "scored": c["scored_count"],
                         "top_three": {k: [h["name"] for h in v] for k, v in c["variants"].items()}}
                        for c in cases]
    (DATA / "results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8", newline="\n")
    demo = {"collected_at": evidence["collected_at"],
            "scope": "Saved historical drafts with later population statistics. Positions are provider estimates.",
            "cases": cases}
    demo["meta_scope"] = evidence["meta"]["source"]
    demo["meta_rank"] = evidence["meta"]["rank_bracket"]
    demo["meta_rank_fallback"] = evidence["meta"]["rank_fallback_applied"]
    assets_path = DATA / "assets.json"
    if assets_path.exists():
        assets = json.loads(assets_path.read_text(encoding="utf8"))

        def local_images(value):
            if isinstance(value, dict):
                return {key: local_images(child) for key, child in value.items()}
            if isinstance(value, list):
                return [local_images(child) for child in value]
            if isinstance(value, str) and value in assets:
                return assets[value]["path"]
            return value

        demo = local_images(demo)
    target = ROOT / "frontend/src/data/draft-demo.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(demo, indent=2) + "\n", encoding="utf8", newline="\n")
    lines = [
        "# Reproducible evaluation", "",
        "Run the following from the backend directory. All inputs are committed. No database, account, or network is required.",
        "", "    python research/evaluate.py", "",
        "## Personal estimates", "",
        "Four convenience-sampled public player histories are deduplicated and ordered by match time. The first 60% supplies warm-up history, the next 20% selects the prior weight, and the final 20% is held out. Each prediction uses only preceding games on the hero within 90 days. Outcomes already observed during validation and test may update later predictions. Roles are pooled because reliable position labels are unavailable.", "",
        f"The selected prior weight is **{selected}**, chosen from 10, 20, 40 and 80 by mean per-player validation Brier. The production default remains 40 pending broader evidence. All priors here are neutral 50% because historical role-and-patch baselines are unavailable.", "",
        "| Player | Test predictions | Neutral | Personal | Fixed 40 | Selected weight |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, row in report["players"].items():
        values = row["test"]
        if values:
            lines.append(f'| {name} | {row["test_count"]} | {values["neutral"]:.4f} | {values["personal"]:.4f} | {values["40"]:.4f} | {values[str(selected)]:.4f} |')
    tests = [r["test"] for r in report["players"].values() if r["test"]]
    lines.extend(["", f'Mean per-player held-out Brier is **{mean(r[str(selected)] for r in tests):.4f}** with the selected weight, **{mean(r["personal"] for r in tests):.4f}** for personal rate, and **0.2500** for neutral prediction.',
                  "", "Four players provide exploratory evidence only. These results evaluate a smoothing component. They do not establish the effectiveness of the full recommendation score or generalize to all ranks.",
                  "", "## Draft ranking ablation", "",
                  "Every variant ranks the same candidates that passed corrected-model evidence checks. Population uses meta alone. Personal adds experience, personal results and complexity. Full adds population-adjusted matchups and risk. Raw uses the previous 50% matchup baseline. All cases retain pre-match player history, while population statistics were collected later.",
                  "", "| Match | Candidates scored / eligible | Population top pick | Personal top pick | Full top pick | Previous model |",
                  "| --- | ---: | --- | --- | --- | --- |"])
    for c in cases:
        tops = [c["variants"][v][0]["name"] if c["variants"][v] else "Unavailable"
                for v in ("population", "personal", "full", "raw")]
        lines.append(f'| {c["match_id"]} | {c["scored_count"]} / {c["eligible_count"]} | ' + " | ".join(tops) + " |")
    lines.extend(["", "These comparisons measure ranking changes and evidence coverage. Winners of unplayed alternatives are unobserved, so they cannot measure counterfactual win-rate improvement.",
                  "", "## External review still needed", "",
                  "For a user study, prepare the same draft views with model labels hidden and output order randomized. Ask experienced players to rate role fit, counterpick reasoning, missing information, and usefulness before revealing the method. Record disagreements and failures as well as positive feedback. No human-review results have been collected.",
                  "", "Full validation scores, per-player counts, rankings and SHA-256 input hashes (UTF-8 with LF line endings) are in [results.json](../data/research/results.json). Source URLs and collection time are stored with the inputs. Public identifiers make these records pseudonymized, not anonymous.", ""])
    (ROOT / "docs/evaluation.md").write_text("\n".join(lines), encoding="utf8")
    print("Selected", selected, "drafts", len(cases), "test predictions",
          sum(r["test_count"] for r in report["players"].values()))


if __name__ == "__main__":
    run()
