import { useState } from "react";
import { requestApi } from "../api";

export default function PlayerSync({ onSync }) {
    const [steamId, setSteamId] = useState("");
    const [pending, setPending] = useState(false);
    const [error, setError] = useState("");

    async function sync(event) {
        event.preventDefault();
        if (pending) return;

        const id = steamId.trim();
        if (!/^\d{1,17}$/.test(id)) {
            setError("Enter a numeric Steam32 or Steam64 ID.");
            return;
        }

        setError("");
        setPending(true);
        try {
            await requestApi("/sync/" + id, { method: "POST" });
            onSync();
        } catch (err) {
            setError(err.retryAfter ? err.message + " Try again in " + err.retryAfter + " seconds." : err.message);
        } finally {
            setPending(false);
        }
    }

    return (
        <form className="player-sync" onSubmit={sync}>
            <label htmlFor="steam-id">Steam account</label>
            <div className="player-sync-controls">
                <input id="steam-id" type="text" inputMode="numeric" placeholder="Steam32 or Steam64 ID"
                    required value={steamId} disabled={pending} onChange={(event) => setSteamId(event.target.value)}
                    aria-describedby="steam-id-hint" />
                <button type="submit" disabled={pending}>{pending ? "Syncing…" : "Sync player"}</button>
            </div>
            <p id="steam-id-hint">Enable “Expose Public Match Data” in Dota 2 to import your match history.</p>
            {pending && <p role="status">Fetching matches and hero statistics…</p>}
            {error && <p className="api-error" role="alert">{error}</p>}
        </form>
    );
}
