import { lazy, Suspense, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Matches from "./pages/Matches";
import MatchDetails from "./pages/MatchDetails";
import Heroes from "./pages/Heroes";
import Recommendations from "./pages/Recommendations";
import AboutUs from "./pages/AboutUs";
import Layout from "./components/Layout";
import useApi from "./useApi";

const Logic = lazy(() => import("./pages/Logic"));

function App() {
    const [revision, setRevision] = useState(0);
    const stats = useApi("/player/stats?recent_limit=20", undefined, revision);
    const accountId = stats.data?.overview.account_id;

    return (
        <BrowserRouter>
            <Layout>
                <Routes>
                    <Route path="/" element={
                        <Dashboard stats={stats} onSync={() => setRevision((value) => value + 1)} />
                    } />
                    <Route path="/matches" element={<Matches accountId={accountId} stats={stats} />} />
                    <Route path="/matches/:matchId" element={<MatchDetails accountId={accountId} stats={stats} />} />
                    <Route path="/heroes" element={<Heroes accountId={accountId} stats={stats} />} />
                    <Route path="/recommendations" element={<Recommendations accountId={accountId} stats={stats} />} />
                    <Route path="/about" element={<AboutUs />} />
                    <Route path="/logic" element={
                        <Suspense fallback={<p role="status">Loading Logic…</p>}>
                            <Logic />
                        </Suspense>
                    } />
                    <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
            </Layout>
        </BrowserRouter>
    );
}

export default App;
