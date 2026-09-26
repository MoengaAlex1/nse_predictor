import { useEffect } from "react";
import { Routes, Route, Outlet, Navigate, useParams } from "react-router-dom";
import { initAuthListener } from "./lib/auth";
import { AppShell } from "./components/layout/AppShell";
import { Home } from "./pages/Home";
import { Companies } from "./pages/Companies";
import { CompanyDeepDive } from "./pages/CompanyDeepDive";
import { InvestorDashboard } from "./pages/InvestorDashboard";
import { InvestorChart } from "./pages/InvestorChart";
import { Screener } from "./pages/Screener";
import { toBase } from "./lib/ticker";

// Redirect suffixed URLs (/company/ABSA.NR, /chart/ABSA_NR) to the canonical
// base form. Any inbound Link or bookmark using the legacy suffix still
// works; we just rewrite the URL before the target page component mounts
// so hooks receive a normalised ticker and the address bar shows the
// canonical form.
function TickerRedirect({ base }: { base: string }) {
  const { ticker: raw = "" } = useParams<{ ticker: string }>();
  const canonical = toBase(raw);
  if (!canonical || canonical === raw.toUpperCase()) {
    return null;
  }
  return <Navigate to={`${base}/${canonical}`} replace />;
}

// Route element that redirects a suffixed ticker to the canonical URL,
// otherwise renders the child page. Wrapping like this keeps the page
// components clean — they never see a .NR/.KE/_NR-suffixed param.
function CanonicalTicker({ base, children }: { base: string; children: React.ReactNode }) {
  const { ticker: raw = "" } = useParams<{ ticker: string }>();
  const canonical = toBase(raw);
  if (canonical && raw && canonical !== raw.toUpperCase()) {
    return <Navigate to={`${base}/${canonical}`} replace />;
  }
  return <>{children}</>;
}
void TickerRedirect;

export default function App() {
  useEffect(() => {
    const unsubscribe = initAuthListener();
    return unsubscribe;
  }, []);

  return (
    <Routes>
      <Route
        element={
          <AppShell>
            <Outlet />
          </AppShell>
        }
      >
        <Route path="/" element={<Home />} />
        <Route path="/companies" element={<Companies />} />
        <Route
          path="/company/:ticker"
          element={
            <CanonicalTicker base="/company">
              <CompanyDeepDive />
            </CanonicalTicker>
          }
        />
        <Route path="/screener" element={<Screener />} />
      </Route>

      <Route
        element={
          <AppShell variant="investor">
            <Outlet />
          </AppShell>
        }
      >
        <Route
          path="/dashboard/:ticker"
          element={
            <CanonicalTicker base="/dashboard">
              <InvestorDashboard />
            </CanonicalTicker>
          }
        />
      </Route>

      {/* Workstation route uses a minimal chrome variant so the
          TradingView-style chart canvas + right sidebar dominate the
          viewport instead of competing with 5 rows of AppShell nav. */}
      <Route
        element={
          <AppShell variant="workstation">
            <Outlet />
          </AppShell>
        }
      >
        <Route
          path="/chart/:ticker"
          element={
            <CanonicalTicker base="/chart">
              <InvestorChart />
            </CanonicalTicker>
          }
        />
      </Route>
    </Routes>
  );
}
