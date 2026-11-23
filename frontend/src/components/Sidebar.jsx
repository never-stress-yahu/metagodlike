import { Link, NavLink } from "react-router-dom";

const demoOnly = import.meta.env.VITE_DEMO_MODE === "true";
const base = import.meta.env.BASE_URL;

const links = [
    ["/", "Overview", "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z"],
    ["/matches", "Matches", "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"],
    ["/heroes", "Heroes", "M12 3l8 3v5c0 5-3 8-8 10-5-2-8-5-8-10V6l8-3zM9 12l2 2 4-4"],
    ["/recommendations", "Recommendations", "M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3z"],
    ["/demo", "Demo", "M8 5l11 7-11 7V5z"],
    ["/about", "About Us", "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 11v6M12 7h.01"],
    ["/logic", "Logic", "M8 4H5v16h3M16 4h3v16h-3M9 12h6M12 9v6"],
];

function Sidebar() {
    return (
        <aside className="sidebar">
            <Link to="/" className="sidebar-brand" aria-label="metagodlike home">
                <img className="sidebar-brand-icon" src={base + "favicon.svg?v=2"} alt="" width="34" height="34" />
                <span className="sidebar-wordmark">
                    <img src={base + "metagodlike-wordmark-source.png"} alt="metagodlike" />
                </span>
            </Link>
            <nav aria-label="Main navigation">
                {links.filter(([path]) => !demoOnly || ["/demo", "/logic", "/about"].includes(path)).map(([path, label, shape]) => (
                    <NavLink key={path} to={path} end={path === "/"} className={path === "/logic" ? "logic-nav-link" : undefined}>
                        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                            strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                            <path d={shape} />
                        </svg>
                        {label}
                    </NavLink>
                ))}
            </nav>
        </aside>
    );
}

export default Sidebar;
