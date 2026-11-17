import ApiStatus from "../components/ApiStatus";
import HeroStats from "../components/HeroStats";
import useApi from "../useApi";

function Heroes({ accountId, stats }) {
    const request = useApi(accountId == null ? null : "/player/heroes?played_only=true", accountId);
    const data = request.data;

    return (
        <section>
            <header className="dashboard-title">
                <h1>Heroes</h1>
                <p>{data?.stats_scope?.kind === "sampled_history"
                    ? "Hero statistics from " + data.stats_scope.matches + " matches"
                    : "Hero performance statistics"}</p>
            </header>
            {!stats.data && <ApiStatus request={stats} requirePlayer />}
            <ApiStatus request={request} />
            {data && <HeroStats heroes={data.heroes} />}
        </section>
    );
}

export default Heroes;
