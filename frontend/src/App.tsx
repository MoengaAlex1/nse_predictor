import { useEffect } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { initAuthListener } from "./lib/auth";
import { Companies } from "./pages/Companies";
import { CompanyDeepDive } from "./pages/CompanyDeepDive";
import { Login } from "./pages/Login";
import { Register } from "./pages/Register";

export default function App() {
  useEffect(() => {
    const unsubscribe = initAuthListener();
    return unsubscribe;
  }, []);

  return (
    <Routes>
      <Route path="/" element={<Navigate to="/companies" replace />} />
      <Route path="/companies" element={<Companies />} />
      <Route path="/company/:ticker" element={<CompanyDeepDive />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
    </Routes>
  );
}
