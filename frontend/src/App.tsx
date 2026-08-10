import { useEffect } from "react";
import { Routes, Route, Outlet } from "react-router-dom";
import { initAuthListener } from "./lib/auth";
import { AppShell } from "./components/layout/AppShell";
import { Home } from "./pages/Home";
import { Companies } from "./pages/Companies";
import { CompanyDeepDive } from "./pages/CompanyDeepDive";
import { InvestorDashboard } from "./pages/InvestorDashboard";

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
      </Route>

      <Route
        element={
          <AppShell variant="investor">
            <Outlet />
          </AppShell>
        }
      >
        <Route path="/dashboard/:ticker" element={<InvestorDashboard />} />
      </Route>
    </Routes>
  );
}
