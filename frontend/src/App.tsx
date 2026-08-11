import { useEffect } from "react";
import { Routes, Route, Outlet } from "react-router-dom";
import { initAuthListener } from "./lib/auth";
import { AppShell } from "./components/layout/AppShell";
import { Home } from "./pages/Home";
import { Companies } from "./pages/Companies";
import { CompanyDeepDive } from "./pages/CompanyDeepDive";
import { InvestorDashboard } from "./pages/InvestorDashboard";
import { InvestorChart } from "./pages/InvestorChart";
import { Screener } from "./pages/Screener";

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
        <Route path="/company/:ticker" element={<CompanyDeepDive />} />
        <Route path="/screener" element={<Screener />} />
      </Route>

      <Route
        element={
          <AppShell variant="investor">
            <Outlet />
          </AppShell>
        }
      >
        <Route path="/dashboard/:ticker" element={<InvestorDashboard />} />
        <Route path="/chart/:ticker" element={<InvestorChart />} />
      </Route>
    </Routes>
  );
}
