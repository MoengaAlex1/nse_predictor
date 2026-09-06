import { useEffect } from "react";
import { Routes, Route, Outlet, Navigate, useParams } from "react-router-dom";
import { initAuthListener } from "./lib/auth";
import { TerminalShell } from "./layouts/TerminalShell";
import { Home } from "./pages/Home";
import { Companies } from "./pages/Companies";
import { CompanyDeepDive } from "./pages/CompanyDeepDive";
import { InvestorChart } from "./pages/InvestorChart";
import { Screener } from "./pages/Screener";
import { Sectors } from "./pages/Sectors";
import { Portfolios } from "./pages/Portfolios";
import { News } from "./pages/News";
import { Calendar } from "./pages/Calendar";

/**
 * Route contract (phase 1 task 5):
 *   /chart/:ticker    chart-first workspace
 *   /company/:ticker  research-first profile
 * /dashboard/:ticker was a third, near-duplicate security view; it redirects
 * into the chart workspace and keeps the ticker.
 */
const DashboardRedirect = () => {
  const { ticker = "" } = useParams<{ ticker: string }>();
  return <Navigate to={`/chart/${ticker}`} replace />;
};

export default function App() {
  useEffect(() => {
    const unsubscribe = initAuthListener();
    return unsubscribe;
  }, []);

  return (
    <Routes>
      {/* One shell for every route — only the main panel swaps. */}
      <Route
        element={
          <TerminalShell>
            <Outlet />
          </TerminalShell>
        }
      >
        <Route path="/" element={<Home />} />
        <Route path="/companies" element={<Companies />} />
        <Route path="/screener" element={<Screener />} />
        <Route path="/company/:ticker" element={<CompanyDeepDive />} />
        <Route path="/chart/:ticker" element={<InvestorChart />} />
        <Route path="/sectors" element={<Sectors />} />
        <Route path="/portfolios" element={<Portfolios />} />
        <Route path="/news" element={<News />} />
        <Route path="/calendar" element={<Calendar />} />
        <Route path="/dashboard/:ticker" element={<DashboardRedirect />} />
        {/* Unknown paths land on Discover rather than a blank screen. */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
