import "./AboutUs.css";

const developers = [
    { name: "Abdolla Margulan", roles: "Frontend", avatar: "/team/margulan.png" },
    { name: "Kaldybekov Arnur", roles: "Backend · Logic · Frontend", avatar: "/team/arnur.png" },
];

function AboutUs() {
    return (
        <div className="about-page">
            <header className="dashboard-title about-heading">
                <h1>About Us</h1>
            </header>

            <div className="about-grid">
                {developers.map(({ name, roles, avatar }) => (
                    <article className="about-card" key={name}>
                        <img className="about-avatar" src={import.meta.env.BASE_URL + avatar.slice(1)} alt="" width="88" height="88" />
                        <div>
                            <h2>{name}</h2>
                            <p>{roles}</p>
                        </div>
                    </article>
                ))}
            </div>

            <figure className="about-quote">
                <blockquote>
                    <p>“The foundation of every state is the education of its youth.”</p>
                </blockquote>
                <figcaption>― <strong>Diogenes</strong></figcaption>
            </figure>
        </div>
    );
}

export default AboutUs;
