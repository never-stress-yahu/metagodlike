import { useId, useState } from "react";

const ticks = [100, 75, 50, 25, 0];

function WinRateChart({ history }) {
    const gradientId = useId();
    const [selected, setSelected] = useState(null);
    const groups = history?.groups ?? [];
    const data = groups.map((group, index) => {
        const total = groups.slice(0, index + 1).reduce((sum, row) => sum + row.matches, 0);
        const x = 2 + 96 * total / history.sample_size;
        const dates = [...new Set([group.start_date, group.end_date].filter(Boolean))].join(" – ");
        const label = (dates || "Date unavailable") + " · " + group.winrate + "% · " + group.wins + " wins in " + group.matches + " matches";
        return { ...group, x, total, label };
    });
    const selectedIndex = data.findIndex((point) => point.group === selected);
    const activeIndex = selectedIndex >= 0 ? selectedIndex : data.length - 1;
    const active = data[activeIndex];
    const line = data.map((point) => point.x + "," + (100 - point.winrate)).join(" ");

    return (
        <section className="winrate-chart">
            <header className="winrate-header">
                <div>
                    <h2>Win Rate</h2>
                    <p>Win rate by group of up to {history?.group_size ?? 20} matches</p>
                </div>
                {active && <strong className="winrate-value">{active.winrate}%</strong>}
            </header>
            {active ? (
                <>
                    <div className="chart-wrapper">
                        <div className="chart-axis" aria-hidden="true">
                            {ticks.map((tick) => <span key={tick} style={{ top: (100 - tick) + "%" }}>{tick}%</span>)}
                        </div>
                        <div className="chart">
                            <svg className="chart-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
                                <defs>
                                    <linearGradient id={gradientId} x2="0" y2="1" gradientUnits="objectBoundingBox">
                                        <stop offset="0%" stopColor="#64d6aa" stopOpacity=".28" />
                                        <stop offset="100%" stopColor="#64d6aa" stopOpacity="0" />
                                    </linearGradient>
                                </defs>
                                {ticks.map((tick) => (
                                    <line key={tick} x1="0" x2="100" y1={100 - tick} y2={100 - tick}
                                        className={tick === 50 ? "chart-midline" : "chart-gridline"}
                                        vectorEffect="non-scaling-stroke" />
                                ))}
                                {data.length > 1 && <polygon points={data[0].x + ",100 " + line + " " + data.at(-1).x + ",100"}
                                    fill={"url(#" + gradientId + ")"} />}
                                <polyline points={line} fill="none" stroke="#76e0b5" strokeWidth="2"
                                    strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
                            </svg>
                            {data.map((point) => (
                                <button type="button" className="chart-point" key={point.group}
                                    style={{ left: point.x + "%", bottom: point.winrate + "%" }}
                                    aria-label={point.label} aria-pressed={active.group === point.group}
                                    onClick={() => setSelected(point.group)} />
                            ))}
                        </div>
                        <div className="chart-numbers" aria-hidden="true">
                            <span>0</span><span>{history.sample_size.toLocaleString()} matches</span>
                        </div>
                    </div>
                    <div className="winrate-footer">
                        <p className="chart-detail" aria-live="polite">Through match {active.total} · {active.label}</p>
                        {data.length > 1 && (
                            <div className="winrate-navigation">
                                <button type="button" aria-label="Previous group" disabled={activeIndex === 0}
                                    onClick={() => setSelected(data[activeIndex - 1].group)}>‹</button>
                                <button type="button" aria-label="Next group" disabled={activeIndex === data.length - 1}
                                    onClick={() => setSelected(data[activeIndex + 1].group)}>›</button>
                            </div>
                        )}
                    </div>
                </>
            ) : <p>{history ? "No match history available." : "Sync your Steam account to load win rate history."}</p>}
        </section>
    );
}

export default WinRateChart;
