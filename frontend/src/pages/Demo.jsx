import { useState } from "react";
import { Link } from "react-router-dom";
import data from "../data/draft-demo.json";
import { PickCard } from "../components/DraftRecommendations";
import { MatchDraft, MatchLineups } from "./MatchDetails";
import "./Demo.css";

const variants = {
    full: "Full recommendation",
    population: "Population only",
    personal: "Population + personal",
    raw: "Previous matchup model",
};
const positions = ["", "Carry", "Mid", "Offlane", "Soft Support", "Hard Support"];

export default function Demo() {
    const [caseIndex, setCaseIndex] = useState(0);
    const [variant, setVariant] = useState("full");
    const sample = data.cases[caseIndex];
    const ownPick = sample.lineups.draft.picks.find((pick) => pick.hero.is_you);
    const heroes = sample.variants[variant];
    const leader = heroes[0];
    const comparison = leader?.score_breakdown;
    const strongest = comparison && Object.entries(comparison).sort((a, b) => b[1] - a[1])[0];
    const factorNames = {
        meta: "population performance", matchups: "matchup advantage",
        personal: "personal results", familiarity: "experience",
        learning_cost: "learning cost", worst_matchup: "worst-matchup risk",
    };

    return (
        <div className="demo-page">
            <header className="dashboard-title">
                <p className="demo-eyebrow">Interactive project demo</p>
                <h1>Choose a hero. Understand the trade-offs.</h1>
                <p>Two teams choose five heroes each. This review reconstructs what one player knew at their turn,
                    then compares the available choices using population results, experience and opposing picks.</p>
            </header>

            <section className="matches-page demo-controls">
                <label>Saved match
                    <select value={caseIndex} onChange={(event) => setCaseIndex(Number(event.target.value))}>
                        {data.cases.map((item, index) => (
                            <option key={item.match_id} value={index}>
                                {item.match_id} · {positions[item.position]}
                            </option>
                        ))}
                    </select>
                </label>
                <label>Scoring model
                    <select value={variant} onChange={(event) => setVariant(event.target.value)}>
                        {Object.entries(variants).map(([value, label]) => (
                            <option key={value} value={value}>{label}</option>
                        ))}
                    </select>
                </label>
                <p className="data-warnings">Saved results · {data.collected_at.slice(0, 10)} · {positions[sample.position]} ({sample.position_source}).
                    Population and matchup data were collected after these matches. Population uses {data.meta_rank}{data.meta_rank_fallback ? " as a rank proxy" : ""} all-position data. Matchups have no rank, role or patch filter.</p>
            </section>

            <section className="matches-page demo-decision">
                <h2>Your decision point</h2>
                <p>The recorded pick was <strong>{ownPick.hero.name}</strong>.
                    At that turn, <strong>{sample.enemies.length} opponents</strong> were visible.
                    The model has sufficient evidence for {sample.scored_count} of {sample.eligible_count} available role candidates.</p>
                <div className="demo-enemies">
                    {sample.enemies.map((hero) => (
                        <div className="hero-name" key={hero.hero_id}>
                            {hero.image_url && <img src={hero.image_url.startsWith("demo/") ? import.meta.env.BASE_URL + hero.image_url : hero.image_url} alt="" />}
                            <span>{hero.name}</span>
                        </div>
                    ))}
                </div>
            </section>

            <section className="matches-page match-comparison">
                <h2>{variants[variant]}</h2>
                {leader && <p><strong>{leader.name}</strong> ranks first in this saved scenario.
                    Its largest score contribution is {factorNames[strongest[0]]} ({strongest[1] > 0 ? "+" : ""}{strongest[1]} points).
                    Switch models to see which choices change.</p>}
                <ol className="draft-picks">
                    {heroes.map((hero) => (
                        <PickCard key={hero.hero_id + variant + sample.match_id}
                            hero={hero} revealedCount={sample.enemies.length} />
                    ))}
                </ol>
                <p className="data-warnings">
                    {variant === "raw" ? "Previous model compares pair win rates with 50%."
                        : "Adjusted edges compare each pair with an expectation based on both heroes' overall results in the same matchup source."}
                    {" "}The selected model controls which terms enter the total. These comparisons show ranking changes.
                    Outcomes for alternative picks are unknown.
                </p>
            </section>

            <details className="demo-context">
                <summary>Inspect the teams and complete pick sequence</summary>
                <MatchLineups request={{ data: sample.lineups }} />
                <MatchDraft draft={sample.lineups.draft} />
            </details>
            <footer className="demo-links">
                <Link to="/logic#draft">Read the formulas</Link>
                <a href="https://github.com/never-stress-yahu/metagodlike/blob/main/docs/evaluation.md">Evaluation and limits</a>
                <a href="https://github.com/never-stress-yahu/metagodlike">Source code</a>
            </footer>
        </div>
    );
}
