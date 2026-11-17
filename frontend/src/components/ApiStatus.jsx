import { Link } from "react-router-dom";

export default function ApiStatus({ request, requirePlayer = false }) {
    if (request.loading) return <p role="status">Loading player data…</p>;

    if (request.error?.status === 409 && requirePlayer) {
        return <p>Sync a Steam account on the <Link to="/">Overview</Link> page to see player data.</p>;
    }

    if (request.error) {
        return (
            <div className="api-error" role="alert">
                <p>{request.error.message}</p>
                <button type="button" onClick={request.retry}>Retry</button>
            </div>
        );
    }

    return null;
}
