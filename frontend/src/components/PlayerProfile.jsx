import { useState } from "react";
import useApi from "../useApi";

const ranks = ["", "Herald", "Guardian", "Crusader", "Archon", "Legend", "Ancient", "Divine", "Immortal"];

function PlayerProfile({ player }) {
    const { data } = useApi(player.avatar_url ? null : "/player/avatar", player.account_id);
    const [failedAvatar, setFailedAvatar] = useState(null);
    const avatar = player.avatar_url || data?.avatar_url;
    const tier = Math.floor(player.rank / 10);
    const medal = ranks[tier];
    const stars = player.rank % 10;
    const rank = medal && medal !== "Immortal" && stars >= 1 && stars <= 5
        ? medal + " " + stars
        : medal || "Unranked / unavailable";

    return (
        <div className="player-profile">
            <div className="player-avatar" aria-hidden="true">
                {avatar && avatar !== failedAvatar
                    ? <img src={avatar} alt="" width="70" height="70" referrerPolicy="no-referrer"
                        onError={() => setFailedAvatar(avatar)} />
                    : Array.from(player.name)[0]?.toUpperCase()}
            </div>
            <div>
                <h2>{player.name}</h2>
                <div className="profile-meta">
                    <p>Steam account ID: {player.account_id}</p>
                    <p className="player-rank">
                        {medal && <img src={"/ranks/rank_icon_" + tier + ".png"} alt="" width="32" height="32" />}
                        <span>{rank}</span>
                    </p>
                    <p>Source: {player.source}</p>
                </div>
            </div>
        </div>
    );
}

export default PlayerProfile;
