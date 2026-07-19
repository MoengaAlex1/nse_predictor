import { useEffect } from "react";
import { Routes, Route } from "react-router-dom";
import { initAuthListener } from "./lib/auth";
import { Home } from "./pages/Home";
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
      <Route path="/" element={<Home />} />
      <Route path="/companies" element={<Companies />} />
      <Route path="/company/:ticker" element={<CompanyDeepDive />} />
      {/* Auth routes hidden — re-enable when auth is re-introduced */}
      {/* <Route path="/login" element={<Login />} /> */}
      {/* <Route path="/register" element={<Register />} /> */}
    </Routes>
  );
}
