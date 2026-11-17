import { useState } from "react";

function HeroStats({ heroes }) {
    const [search, setSearch] = useState("");
    const [sortByWinRate, setSortByWinRate] = useState(false);

    const filtered = heroes.filter((hero) =>
        hero.name.toLowerCase().includes(search.trim().toLowerCase())
    );
    if (sortByWinRate) filtered.sort((a, b) => b.winrate - a.winrate);

    return (
        <div className="hero-stats">
            <div className="hero-controls">
                <input type="search" aria-label="Search heroes" placeholder="Search hero..."
                    value={search} onChange={(event) => setSearch(event.target.value)} />
                <button type="button" aria-pressed={sortByWinRate} onClick={() => setSortByWinRate(true)}>
                    Sort by Win Rate
                </button>
                <button type="button" onClick={() => { setSortByWinRate(false); setSearch(""); }}>
                    Reset
                </button>
            </div>
            {!filtered.length ? <p>No heroes to display.</p> : (
                <div className="table-scroll">
                    <table className="data-table">
                        <thead>
                            <tr className="hero-header">
                                <th scope="col">Hero</th>
                                <th scope="col">Matches</th>
                                <th scope="col">Wins</th>
                                <th scope="col">Losses</th>
                                <th scope="col">Win Rate</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filtered.map((hero) => (
                                <tr className="hero-row" key={hero.hero_id}>
                                    <td>
                                        <div className="hero-name">
                                            {hero.icon_url && <img src={hero.icon_url} alt="" loading="lazy" />}
                                            <span>{hero.name}</span>
                                        </div>
                                    </td>
                                    <td>{hero.games}</td>
                                    <td>{hero.wins}</td>
                                    <td>{hero.losses}</td>
                                    <td>{hero.winrate}%</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}

export default HeroStats;
