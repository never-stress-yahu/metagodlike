import CoreFarm from "../components/CoreFarm";
import ApiStatus from "../components/ApiStatus";
import HeroPool from "../components/HeroPool";
import PlayerProfile from "../components/PlayerProfile";
import PlayerSync from "../components/PlayerSync";
import StatCard from "../components/StatCard";
import RecentMatches from "../components/RecentMatches";
import WinRateChart from "../components/WinRateChart";

function Dashboard({ stats, onSync }) {
    const player = stats.data?.overview;
    const showHeroPool = stats.data?.favorite_hero?.games > 0;

    return (
        <section className="overview-page">
            <header className="dashboard-title">
                <h1>Overview</h1>
                <p>Player performance and recent activity</p>
            </header>
            {!player && stats.error?.status !== 409 && <ApiStatus request={stats} />}
            {player ? (
                <div className="overview-profile">
                    <PlayerProfile player={player} />
                    <details className="change-player">
                        <summary>Change Steam account</summary>
                        <PlayerSync onSync={onSync} />
                    </details>
                </div>
            ) : (
                <div className="player-profile player-profile-empty">
                    <h2>Your Player Profile</h2>
                    <PlayerSync onSync={onSync} />
                </div>
            )}
            <div className="stats overview-stats">
                <StatCard metric="matches" title={player?.totals_scope === "sampled_history" ? "Sampled Matches" : "Total Matches"}
                    value={player?.total_matches?.toLocaleString() ?? "—"} />
                <StatCard metric="winrate" winrate={player?.winrate} title="Win Rate" value={player ? player.winrate + "%" : "—"} />
                <StatCard metric="kda" title="Recent KDA" value={player?.recent_kda ?? "—"} />
                <StatCard metric="gpm" title="Recent GPM" value={player?.recent_gpm ?? "—"} />
            </div>
            {player?.warnings.length > 0 && (
                <details className="data-warnings">
                    <summary>Data notes</summary>
                    <ul>{[...new Set(player.warnings)].map((warning) => <li key={warning}>{warning}</li>)}</ul>
                </details>
            )}
            <div className={showHeroPool ? "overview-analysis" : "overview-analysis overview-analysis-single"}>
                <WinRateChart history={stats.data?.winrate_history} />
                {showHeroPool && <HeroPool stats={stats.data} />}
            </div>
            {player && <CoreFarm player={player} />}
            <RecentMatches matches={stats.data?.recent_matches} />
        </section>
    );
}

export default Dashboard;
