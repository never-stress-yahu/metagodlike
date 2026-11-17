import { Link } from "react-router-dom";

const integer = new Intl.NumberFormat();

export default function HeroPool({ stats }) {
    const featured = stats.favorite_hero;
    if (!featured?.games) return null;

    const alternates = (stats.most_played_heroes ?? [])
        .filter((hero) => hero.hero_id !== featured.hero_id && hero.games > 0).slice(0, 4);

    return (
        <section className="hero-pool" aria-labelledby="hero-pool-title">
            <header className="hero-pool-heading">
                <h2 id="hero-pool-title">Most Played Heroes</h2>
                <Link to="/heroes">View all <span aria-hidden="true">→</span></Link>
            </header>
            <div className="hero-pool-feature">
                {featured.image_url && <img src={featured.image_url} alt="" />}
                <div className="hero-pool-caption">
                    <h3>{featured.name}</h3>
                    <span>{integer.format(featured.games)} matches · {featured.winrate}% win rate</span>
                </div>
            </div>
            {alternates.length > 0 && (
                <ul className="hero-pool-list">
                    {alternates.map((hero) => (
                        <li key={hero.hero_id}>
                            {hero.image_url ? <img src={hero.image_url} alt="" loading="lazy" /> : <span aria-hidden="true" />}
                            <div><strong>{hero.name}</strong><small>{integer.format(hero.games)} matches</small></div>
                            <span>{hero.winrate}%</span>
                        </li>
                    ))}
                </ul>
            )}
        </section>
    );
}
