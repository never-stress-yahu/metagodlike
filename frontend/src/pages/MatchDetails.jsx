import { Link, useLocation, useParams } from "react-router-dom";
import ApiStatus from "../components/ApiStatus";
import DraftRecommendations from "../components/DraftRecommendations";
import useApi from "../useApi";

const metricLabels = [
    ["kills", "Kills"],
    ["deaths", "Deaths"],
    ["assists", "Assists"],
    ["kda", "KDA ratio"],
    ["gpm", "Gold per minute"],
    ["xpm", "XP per minute"],
];

const number = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });
const signed = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2, signDisplay: "exceptZero" });
const dateTime = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

function MatchSummary({ match, lineups }) {
    const playedAt = match.start_time == null ? null : new Date(match.start_time * 1000);

    return (
        <>
            <header className="match-detail-header">
                {match.hero_image_url && <img src={match.hero_image_url} alt="" />}
                <div>
                    <h1>{match.hero_name}</h1>
                    <span className={match.is_win ? "victory" : "defeat"}>
                        {match.is_win ? "Victory" : "Defeat"}
                    </span>
                </div>
            </header>
            <dl className="match-detail-facts">
                <div><dt>Match ID</dt><dd>{match.match_id}</dd></div>
                <div><dt>Duration</dt><dd>{match.duration ?? "—"}</dd></div>
                <div><dt>Played</dt><dd>{playedAt ? (
                    <time dateTime={playedAt.toISOString()}>{dateTime.format(playedAt)}</time>
                ) : "—"}</dd></div>
                {(lineups?.player_position_name || match.position_name) && (
                    <div>
                        <dt>Position</dt>
                        <dd>{lineups?.player_position_name || match.position_name}{(lineups?.player_position_name || match.position_source === "provider estimate") && " (estimated)"}</dd>
                    </div>
                )}
            </dl>
        </>
    );
}

function MatchComparison({ data }) {
    const matchCount = data.baseline_match_count;
    return (
        <section className="matches-page match-comparison">
            <h2>Performance vs. your recent average</h2>
            <p className="data-warnings">{matchCount > 0
                ? "Compared with up to " + matchCount + " other recent matches. Games counted can vary by metric."
                : "Sync more matches to calculate your recent average."}</p>
            <div className="table-scroll">
                <table className="data-table">
                    <thead>
                        <tr className="matches-page-header">
                            <th scope="col">Metric</th>
                            <th scope="col">This match</th>
                            <th scope="col">Average</th>
                            <th scope="col">Difference</th>
                            <th scope="col">Games counted</th>
                        </tr>
                    </thead>
                    <tbody>
                        {metricLabels.map(([key, label]) => {
                            const { value, average, delta, sample_size: sampleSize } = data.comparison[key];
                            const change = key === "deaths" ? -delta : delta;
                            const color = change > 0 ? "victory" : change < 0 ? "defeat" : undefined;
                            return (
                                <tr key={key} className="matches-page-row">
                                    <th scope="row">{label}</th>
                                    <td>{value == null ? "—" : number.format(value)}</td>
                                    <td>{average == null ? "—" : number.format(average)}</td>
                                    <td className={color}>{delta == null ? "—" : signed.format(delta)}</td>
                                    <td>{sampleSize}</td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </section>
    );
}


export function MatchLineups({ request }) {
    const lineups = request.data;

    return (
        <section className="matches-page match-comparison">
            <h2>Team lineups</h2>
            <ApiStatus request={request} />
            {lineups && (
                <div className="recommendation-grid match-lineups">
                    {[
                        ["Your team", lineups.side, lineups.allies],
                        ["Opponents", lineups.side === "Radiant" ? "Dire" : "Radiant", lineups.enemies],
                    ].map(([label, side, heroes]) => (
                        <section className="recommendation-list" key={label}>
                            <h3>{label} · {side}</h3>
                            {heroes.length === 0 && <p>No hero picks were reported for this team.</p>}
                            <ul>
                                {heroes.map((hero) => (
                                    <li className="hero-name" key={hero.slot}>
                                        {hero.image_url && <img src={hero.image_url.startsWith("demo/") ? import.meta.env.BASE_URL + hero.image_url : hero.image_url} alt="" />}
                                        <span>{hero.name}{hero.is_you && " (You)"}</span>
                                    </li>
                                ))}
                            </ul>
                        </section>
                    ))}
                </div>
            )}
        </section>
    );
}

export function MatchDraft({ draft }) {
    const allPick = draft?.format === "all_pick";
    const yourPhase = draft?.picks.find((pick) => pick.hero.is_you)?.phase;
    return (
        <section className="matches-page match-comparison">
            <h2>{allPick ? "Draft phases" : "Draft order"}</h2>
            {draft ? (
                <>
                    {allPick ? (
                        <>
                            <p><strong>Your pick</strong> · Phase {yourPhase} of 3</p>
                            <p className="data-warnings">Each team picks 2, 2, then 1 hero. Both teams reveal their picks together, including in the final phase. Reported bans are excluded from suggestions.</p>
                        </>
                    ) : <p><strong>Last pick</strong> · {draft.last_pick_allied ? "Your team" : "Opponents"}</p>}
                    <div className="table-scroll">
                        <table className="data-table">
                            <thead>
                                <tr className="matches-page-header">
                                    {!allPick && <th scope="col">Pick</th>}
                                    <th scope="col">Phase</th>
                                    <th scope="col">Team</th>
                                    <th scope="col">Hero</th>
                                    <th scope="col">Enemies already revealed</th>
                                </tr>
                            </thead>
                            <tbody>
                                {draft.picks.map((pick, index) => (
                                    <tr className="matches-page-row" key={index}>
                                        {!allPick && <td>{index + 1}</td>}
                                        <td>{pick.phase}</td>
                                        <td>{pick.allied ? "Your team" : "Opponents"}</td>
                                        <th scope="row">{pick.hero.name}{pick.hero.is_you && " (You)"}</th>
                                        <td>{pick.enemies_revealed?.map((hero) => hero.name).join(", ") || (pick.allied ? "None yet" : "—")}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </>
            ) : <p>OpenDota did not provide a draft log that can establish the pick order or phases for this match.</p>}
        </section>
    );
}

export default function MatchDetails({ accountId, stats }) {
    const { matchId } = useParams();
    const fromOverview = useLocation().state?.fromOverview === true;
    const validId = /^[1-9]\d*$/.test(matchId);
    const request = useApi(accountId != null && validId ? "/player/matches/" + matchId : null, accountId);
    const data = request.data;
    const lineups = useApi(data ? "/player/matches/" + matchId + "/lineups" : null, accountId);
    const unavailable = request.error?.status === 404 || !validId;

    return (
        <section>
            <Link className="match-back" to={fromOverview ? "/" : "/matches"}>
                {fromOverview ? "← Back to Overview" : "← Back to Matches"}
            </Link>
            {!data && <h1>Match details</h1>}
            {unavailable ? (
                <p role="status">This match is unavailable in your recent synced matches.</p>
            ) : (
                <>
                    {!stats.data && <ApiStatus request={stats} requirePlayer />}
                    <ApiStatus request={request} />
                </>
            )}
            {data && (
                <>
                    <MatchSummary match={data.match} lineups={lineups.data} />
                    <MatchLineups request={lineups} />
                    {lineups.data && <MatchDraft draft={lineups.data.draft} />}
                    {lineups.data?.draft && (
                        <DraftRecommendations key={matchId} matchId={matchId} accountId={accountId} />
                    )}
                    <MatchComparison data={data} />
                </>
            )}
        </section>
    );
}
