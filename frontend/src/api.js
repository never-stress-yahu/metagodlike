const baseUrl = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");

export async function requestApi(path, options) {
    let response;
    try {
        response = await fetch(baseUrl + path, options);
    } catch (error) {
        if (error.name === "AbortError") throw error;
        throw new Error("Could not reach the metagodlike server.", { cause: error });
    }

    const body = await response.json().catch(() => null);
    if (!response.ok || !body) {
        const detail = body?.detail;
        const message = typeof detail === "string" ? detail : detail?.message;
        const providers = detail?.providers?.join(" · ");
        const error = new Error(
            [message, providers].filter(Boolean).join(" — ") ||
            "The metagodlike API returned an unexpected response (" + response.status + ")."
        );
        error.status = response.status;
        error.retryAfter = response.headers.get("Retry-After");
        throw error;
    }

    return body;
}
