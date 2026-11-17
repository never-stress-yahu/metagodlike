import { useState } from "react";
import ApiStatus from "./ApiStatus";
import useApi from "../useApi";

const positions = ["Carry", "Mid", "Offlane", "Soft Support", "Hard Support"];

function PickCard({ hero, revealedCount }) {
    return (
        <li>
            <div className="hero-name">
                {hero.icon_url && <img src={hero.icon_url} alt="" />}
                <strong>{hero.name}</strong>
            </div>
            <p>Meta win rate {hero.meta_winrate}% · {hero.meta_games} games</p>
            <p>Your pre-match record {hero.player_games > 0
                ? hero.player_winrate + "% · " + hero.player_games + " games"
                : "—"}</p>
            <p>Difficulty · {hero.complexity_name ?? "Unknown"}</p>
            {revealedCount > 0 && (
                <details>
                    <summary>Matchups · {hero.matchups.length}/{revealedCount} enemies covered</summary>
                    <ul>
                        {hero.matchups.map((pair) => (
                            <li key={pair.enemy}>
                                <span className={pair.edge > 0 ? "victory" : pair.edge < 0 ? "defeat" : undefined}>
                                    {pair.winrate}% vs {pair.enemy}
                                </span>
                                {" · "}{pair.games} games
                            </li>
                        ))}
                    </ul>
                </details>
            )}
            <details>
                <summary>Ranking score · {hero.score}</summary>
                <p>Meta {hero.score_breakdown.meta} · Matchups {hero.score_breakdown.matchups}
                    {" · "}Worst matchup {hero.score_breakdown.worst_matchup}
                    {" · "}Personal win rate {hero.score_breakdown.personal}
                    {" · "}Familiarity {hero.score_breakdown.familiarity}
                    {" · "}Learning cost {hero.score_breakdown.learning_cost}</p>
            </details>
        </li>
    );
}

export default function DraftRecommendations({ accountId, matchId }) {
    const [position, setPosition] = useState("");
    const path = "/player/matches/" + matchId + "/draft-recommendations";
    const request = useApi(position ? path + "?position=" + position : path, accountId);
    const result = request.data;

    return (
        <section className="matches-page match-comparison">
            <h2>Top picks for your turn</h2>
            <div className="recommendation-controls">
                <label>Position
                    <select value={position} onChange={(event) => setPosition(event.target.value)}>
                        <option value="">
                            {result?.position_source === "hero_default" ? "Hero default" : "Auto"}
                            {result && !position ? " · " + result.position_name : ""}
                        </option>
                        {positions.map((name, index) => <option key={name} value={index + 1}>{name}</option>)}
                    </select>
                </label>
            </div>
            <ApiStatus request={request} />
            {result && (
                <>
                    <p className="data-warnings">
                        {result.meta_verified_current ? "Verified current-patch role meta"
                            : result.dotabuff_role_sample ? "Dotabuff position sample (patch coverage unverified)"
                                : "Historical all-position meta"}
                        {" · "}{result.meta_rank?.replaceAll("_", " ") || "Rank unavailable"}
                        {result.meta_rank_fallback && " (rank proxy)"}
                        {" · "}Historical matchup data across ranks
                    </p>
                    <p>{result.enemies_revealed.length
                        ? "Enemies revealed before your pick: " + result.enemies_revealed.map((hero) => hero.name).join(", ")
                        : "No opponents had been revealed at your pick."}</p>
                    {result.recommendations.length ? (
                        <ol className="draft-picks">
                            {result.recommendations.map((hero) => (
                                <PickCard key={hero.hero_id} hero={hero} revealedCount={result.enemies_revealed.length} />
                            ))}
                        </ol>
                    ) : <p role="status">No available heroes had enough meta or matchup data for this position.</p>}
                </>
            )}
        </section>
    );
}
