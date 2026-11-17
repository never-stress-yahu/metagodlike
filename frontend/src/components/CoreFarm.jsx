import { useState } from "react";
import ApiStatus from "./ApiStatus";
import useApi from "../useApi";

const farmMetrics = [
    ["last_hits_per_minute", "Last hits / min"],
    ["last_hits_per_match", "Last hits / match"],
];

function CoreFarmChart({ roles }) {
    const [metric, setMetric] = useState(farmMetrics[0][0]);
    const ceiling = Math.max(1, ...roles.map((role) => role[metric] ?? 0));

    return (
        <div className="core-farm-chart">
            <div className="filter-buttons" role="group" aria-label="Farming chart metric">
                {farmMetrics.map(([id, label]) => (
                    <button type="button" key={id} aria-pressed={metric === id}
                        className={metric === id ? "active" : ""} onClick={() => setMetric(id)}>
                        {label}
                    </button>
                ))}
            </div>
            <ul className="core-farm-bars">
                {roles.map((role) => {
                    const value = role[metric];
                    return (
                        <li className="core-farm-bar" key={role.position}>
                            <span>{role.role}</span>
                            <span className="core-farm-track" aria-hidden="true">
                                {value != null && <span style={{ width: (100 * value / ceiling) + "%" }} />}
                            </span>
                            <strong>{value?.toLocaleString() ?? "—"}</strong>
                        </li>
                    );
                })}
            </ul>
        </div>
    );
}

export default function CoreFarm({ player }) {
    const request = useApi(player ? "/player/core-farm" : null, player?.account_id, player?.synced_at);
    const data = request.data;
    const counted = data?.roles.reduce((sum, role) => sum + role.matches, 0);
    const support = data ? data.recent_matches - counted - data.missing_data : 0;

    return (
        <section className="matches-page">
            <h2>Recent farming by role</h2>
            <ApiStatus request={request} />
            {data && (
                <>
                    <p className="data-warnings">
                        <strong>Counted {counted} of {data.recent_matches} synced matches.</strong>
                        {" · "}{support} support games
                        {" · "}{data.missing_data} games missing role or farming data.
                        Positions are estimated by OpenDota.
                    </p>
                    <CoreFarmChart roles={data.roles} />
                    <div className="table-scroll">
                        <table className="data-table">
                            <thead>
                                <tr className="matches-page-header">
                                    <th scope="col">Role</th><th scope="col">Matches</th>
                                    <th scope="col">Last hits / match</th><th scope="col">Last hits / min</th>
                                </tr>
                            </thead>
                            <tbody>
                                {data.roles.map((row) => (
                                    <tr className="matches-page-row" key={row.position}>
                                        <th scope="row">{row.role}</th><td>{row.matches}</td>
                                        <td>{row.last_hits_per_match ?? "—"}</td>
                                        <td>{row.last_hits_per_minute ?? "—"}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </>
            )}
        </section>
    );
}
