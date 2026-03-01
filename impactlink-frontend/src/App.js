import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Landing from "./pages/Landing";
import Dashboard from "./pages/Dashboard";
import GrantsList from "./pages/GrantsList";
import GrantDetail from "./pages/GrantDetail";
import Upload from "./pages/Upload";
import Draft from "./pages/Draft";
import Budget from "./pages/Budget";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/"              element={<Landing />} />
        <Route path="/dashboard"     element={<Dashboard />} />
        <Route path="/grants"        element={<GrantsList />} />
        <Route path="/grants/:id"    element={<GrantDetail />} />
        <Route path="/upload"        element={<Upload />} />
        <Route path="/draft"         element={<Draft />} />
        <Route path="/budget"        element={<Budget />} />
        <Route path="*"              element={<Navigate to="/" />} />
      </Routes>
    </BrowserRouter>
  );
}