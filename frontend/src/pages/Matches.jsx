import { useState } from "react";
import ApiStatus from "../components/ApiStatus";
import MatchRows from "../components/MatchRows";
import useApi from "../useApi";

function Matches({ accountId, stats }) {
    const [filter, setFilter] = useState("All");
    const [search, setSearch] = useState("");
    const recent = useApi(accountId == null ? null : "/player/matches?limit=20", accountId);
    const matches = recent.data?.matches.filter((match) => {
        const matchesFilter = filter === "All" || (filter === "Victory") === match.is_win;
        return matchesFilter && match.hero_name.toLowerCase().includes(search.trim().toLowerCase());
    });

    return (
        <section>
            <header className="dashboard-title">
                <h1>Matches</h1>
                <p>Recent match history</p>
            </header>
            {!stats.data && <ApiStatus request={stats} requirePlayer />}
            <ApiStatus request={recent} />
            {matches && (
                <>
                    <div className="matches-controls">
                        <div className="filter-buttons" aria-label="Filter by result">
                            {["All", "Victory", "Defeat"].map((result) => (
                                <button key={result} type="button" className={filter === result ? "active" : ""}
                                    aria-pressed={filter === result} onClick={() => setFilter(result)}>
                                    {result}
                                </button>
                            ))}
                        </div>
                        <input type="search" aria-label="Search matches by hero" placeholder="Search hero..."
                            value={search} onChange={(event) => setSearch(event.target.value)} />
                    </div>
                    <div className="matches-page">
                        <MatchRows matches={matches} showDuration />
                    </div>
                </>
            )}
        </section>
    );
}

export default Matches;
