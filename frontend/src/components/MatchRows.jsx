import { Link } from "react-router-dom";

export default function MatchRows({ matches, showDuration = false }) {
    const rowClass = showDuration ? "matches-page-row" : "match-row";
    const headerClass = showDuration ? "matches-page-header" : "matches-header";

    if (!matches.length) return <p>No matches to display.</p>;

    return (
        <div className="table-scroll">
            <table className="data-table">
                <thead>
                    <tr className={headerClass}>
                        <th scope="col">Hero</th>
                        <th scope="col">Result</th>
                        <th scope="col">K / D / A</th>
                        <th scope="col">GPM</th>
                        {showDuration && <th scope="col">Duration</th>}
                    </tr>
                </thead>
                <tbody>
                    {matches.map((match) => (
                        <tr className={rowClass + " match-with-details"} key={match.match_id}>
                            <td>
                                <div className="hero-name">
                                    {match.hero_image_url && <img src={match.hero_image_url} alt="" loading="lazy" />}
                                    <Link className="match-details-link" to={"/matches/" + match.match_id}
                                        state={{ fromOverview: !showDuration }}
                                        aria-label={"View match " + match.match_id + " as " + match.hero_name}>
                                        {match.hero_name}
                                    </Link>
                                </div>
                            </td>
                            <td>
                                <span className={"match-result " + (match.is_win ? "victory" : "defeat")}>
                                    {match.is_win ? "Victory" : "Defeat"}
                                </span>
                            </td>
                            <td>{match.kda_string}</td>
                            <td>{match.gpm ?? "—"}</td>
                            {showDuration && <td>{match.duration ?? "—"}</td>}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}
