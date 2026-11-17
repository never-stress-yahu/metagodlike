import { useState } from "react";
import ApiStatus from "../components/ApiStatus";
import RecommendationFilters from "../components/RecommendationFilters";
import StartingItems from "../components/StartingItems";
import useApi from "../useApi";

function RecommendationList({ title, heroes, emptyMessage, note }) {
    return (
        <section className="recommendation-list rec-track">
            <header className="rec-track-header">
                <h2>{title}</h2>
                {note && <p>{note}</p>}
            </header>
            {heroes.length ? (
                <ul className="rec-heroes">
                    {heroes.map((hero) => (
                        <li key={hero.hero_id}>
                            <StartingItems hero={hero} position={hero.target_position} difficulty={hero.complexity_name} />
                            <dl className="rec-hero-stats">
                                <div>
                                    <dt>Meta win rate</dt>
                                    <dd>{hero.meta_winrate}%</dd>
                                    <small>{hero.meta_scope === "rank_all_positions_proxy" ? "All positions" : "Selected position"}</small>
                                </div>
                                <div><dt>Sample matches</dt><dd>{hero.meta_matches.toLocaleString()}</dd></div>
                                <div><dt>Your games</dt><dd>{hero.games.toLocaleString()}</dd></div>
                            </dl>
                            {hero.reasons.length > 0 && (
                                <details className="rec-reasons">
                                    <summary>Why this hero</summary>
                                    <ul>{hero.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
                                </details>
                            )}
                        </li>
                    ))}
                </ul>
            ) : <p className="rec-empty">{emptyMessage}</p>}
        </section>
    );
}

function ObservedRoleStats({ data }) {
    return (
        <details className="matches-page">
            <summary>Observed {data.target_position_name} picks · {data.role_candidates.length} heroes</summary>
            <p className="data-warnings">
                At least 200 matches and 10% of the hero's reported picks across the five positions.
                Your win rate uses position-tagged matches from the past 90 days.
            </p>
            <div className="table-scroll">
                <table className="data-table">
                    <thead>
                        <tr className="matches-page-header">
                            <th scope="col">Hero</th><th scope="col">Role matches</th>
                            <th scope="col">Role win rate</th><th scope="col">Share of reported picks</th>
                            <th scope="col">Your role win rate</th>
                        </tr>
                    </thead>
                    <tbody>
                        {data.role_candidates.map((hero) => (
                            <tr className="matches-page-row" key={hero.hero_id}>
                                <th scope="row"><StartingItems hero={hero} position={data.target_position} showIcon={false} /></th>
                                <td>{hero.matches.toLocaleString()}</td>
                                <td>{hero.winrate}%</td>
                                <td>{hero.reported_role_share}%</td>
                                <td>{hero.player_role_games
                                    ? hero.player_role_winrate + "% · " + hero.player_role_games + " games"
                                    : "—"}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </details>
    );
}

export default function Recommendations({ accountId, stats }) {
    const [position, setPosition] = useState("1");
    const [rank, setRank] = useState("");
    const params = new URLSearchParams({ position, limit: "5", allow_historical_learning: "true" });
    if (rank) params.set("meta_rank", rank);
    const request = useApi(accountId == null ? null : "/player/trends?" + params, accountId);
    const data = request.data;
    const historical = data?.meta.evidence_mode === "historical";
    const current = data?.meta.evidence_mode === "verified_current";
    const observedRoles = data?.meta.dotabuff_role_sample;

    return (
        <section className="recommendations-page">
            <header className="dashboard-title">
                <h1>Recommendations</h1>
                <p>Hero suggestions for your position and rank</p>
            </header>
            {!stats.data && <ApiStatus request={stats} requirePlayer />}
            {accountId != null && (
                <RecommendationFilters position={position} rank={rank} playerRank={stats.data?.overview.rank}
                    onPosition={setPosition} onRank={setRank} />
            )}
            <ApiStatus request={request} />
            {data && (
                <>
                    <p className="rec-context">
                        {[data.target_position_name, data.meta.rank_bracket?.replaceAll("_", " "),
                            current && data.meta.current_patch && "Patch " + data.meta.current_patch].filter(Boolean).join(" · ")}
                    </p>
                    {historical && (
                        <div className="recommendation-evidence" role="status">
                            <strong>{observedRoles ? "Dotabuff position sample" : "Historical recommendations"}</strong>
                            <p>
                                {observedRoles
                                    ? "Seven-day All Pick sample for Crusader, collected " + data.meta.collected_at.slice(0, 10) + "."
                                    : data.meta.position_data_exact
                                    ? "Based on the provider's historical position split."
                                    : "Win rates cover all positions. Hero eligibility follows the selected position."}
                                {" "}Current-patch coverage is unverified.
                                {observedRoles && <> <a href={data.meta.source_url} target="_blank" rel="noreferrer">View source</a></>}
                            </p>
                        </div>
                    )}
                    {data.meta.rank_fallback_applied && (
                        <p className="data-warnings">{data.meta.requested_rank_bracket} uses {data.meta.rank_bracket} statistics.</p>
                    )}
                    <div className="recommendation-grid">
                        <RecommendationList title="Recommended for next games" heroes={data.recommended_for_next_games}
                            emptyMessage={data.message || "No recommendations available."} />
                        <RecommendationList title="Worth learning" heroes={data.worth_learning}
                            emptyMessage={data.worth_learning_message}
                            note={!observedRoles && data.worth_learning_evidence_mode === "historical"
                                ? "Practice candidates based on historical stats and curated positions. Current-patch role performance is unverified."
                                : undefined} />
                    </div>
                    {data.role_candidates?.length > 0 && <ObservedRoleStats data={data} />}
                    {data.meta.warnings.length > 0 && (
                        <details className="data-warnings">
                            <summary>Meta data notes</summary>
                            <ul>{data.meta.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
                        </details>
                    )}
                </>
            )}
        </section>
    );
}
