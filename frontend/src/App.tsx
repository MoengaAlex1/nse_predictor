import { useEffect } from "react";
import { Routes, Route } from "react-router-dom";
import { initAuthListener } from "./lib/auth";
import { AppShell } from "./components/layout/AppShell";
import { Home } from "./pages/Home";
import { Companies } from "./pages/Companies";
import { CompanyDeepDive } from "./pages/CompanyDeepDive";

export default function App() {
  useEffect(() => {
    const unsubscribe = initAuthListener();
    return unsubscribe;
  }, []);

  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/companies" element={<Companies />} />
        <Route path="/company/:ticker" element={<CompanyDeepDive />} />
      </Routes>
    </AppShell>
  );
}
