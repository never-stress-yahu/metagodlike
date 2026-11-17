import MatchRows from "./MatchRows";

function RecentMatches({ matches }) {
    return (
        <section className="recent-matches">
            <h2>Recent Matches</h2>
            {matches ? <MatchRows matches={matches} /> : <p>Sync your Steam account to load recent matches.</p>}
        </section>
    );
}

export default RecentMatches;
