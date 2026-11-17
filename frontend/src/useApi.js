import { useEffect, useState } from "react";
import { requestApi } from "./api";

export default function useApi(path, accountId, revision = 0) {
    const [response, setResponse] = useState(null);
    const [attempt, setAttempt] = useState(0);

    useEffect(() => {
        if (!path) return;
        const controller = new AbortController();
        const storeResult = (value) => {
            if (controller.signal.aborted) return;
            setResponse({ path, accountId, revision, attempt, ...value });
        };

        requestApi(path, { signal: controller.signal })
            .then((data) => {
                if (accountId != null && accountId !== data.account_id) {
                    throw new Error("The active player changed. Reload the page to see their statistics.");
                }
                storeResult({ data });
            })
            .catch((error) => storeResult({ error }));

        return () => controller.abort();
    }, [path, accountId, revision, attempt]);

    const current = response?.path === path && response.accountId === accountId &&
        response.revision === revision && response.attempt === attempt ? response : null;

    return {
        data: current?.data,
        error: current?.error,
        loading: Boolean(path && !current),
        retry: () => setAttempt((value) => value + 1),
    };
}
