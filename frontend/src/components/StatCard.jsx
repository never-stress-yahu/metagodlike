const statIcons = {
    matches: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
    winrate: "M3 19h18M5 15l5-5 4 3 6-8m-5 0h5v5",
    kda: "M3 12h4l3-7 4 14 3-7h4",
    gpm: "M20 8c0 2-3.6 3-8 3S4 10 4 8s3.6-3 8-3 8 1 8 3ZM4 8v8c0 2 3.6 3 8 3s8-1 8-3V8M4 12c0 2 3.6 3 8 3s8-1 8-3",
};

function StatCard({ title, value, metric, winrate }) {
    const hasWinrate = Number.isFinite(winrate);
    const difference = hasWinrate ? winrate - 50 : 0;
    const accent = difference > 0 ? "#a8efcb" : "#ffaaa8";
    const strength = Math.min(100, Math.abs(difference) * 3.3);
    const style = difference === 0 ? undefined : {
        "--stat-accent": accent,
        "--stat-strength": strength + "%",
    };

    return (
        <div className={"stat-card stat-" + metric} style={style}>
            <p className="stat-card-label">
                <span className="stat-card-icon" aria-hidden="true">
                    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                        strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                        <path d={statIcons[metric]} />
                    </svg>
                </span>
                {title}
            </p>
            <h2>{value}</h2>
        </div>
    );
}

export default StatCard;
