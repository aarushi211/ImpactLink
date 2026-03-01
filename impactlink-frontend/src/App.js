import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider }  from "./context/AuthContext";
import ProtectedRoute    from "./components/ProtectedRoute";

import Landing       from "./pages/Landing";
import Login         from "./pages/Login";
import Profile       from "./pages/Profile";
import Dashboard     from "./pages/Dashboard";
import GrantsList    from "./pages/GrantsList";
import GrantDetail   from "./pages/GrantDetail";
import Upload        from "./pages/Upload";
import Draft         from "./pages/Draft";
import Budget        from "./pages/Budget";
import BuildProposal from "./pages/BuildProposal";

const P = ({ children }) => <ProtectedRoute>{children}</ProtectedRoute>;

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public */}
          <Route path="/"      element={<Landing />} />
          <Route path="/login" element={<Login />} />

          {/* Protected */}
          <Route path="/dashboard"  element={<P><Dashboard /></P>} />
          <Route path="/profile"    element={<P><Profile /></P>} />
          <Route path="/grants"     element={<P><GrantsList /></P>} />
          <Route path="/grants/:id" element={<P><GrantDetail /></P>} />
          <Route path="/upload"     element={<P><Upload /></P>} />
          <Route path="/draft"      element={<P><Draft /></P>} />
          <Route path="/budget"     element={<P><Budget /></P>} />
          <Route path="/build"      element={<P><BuildProposal /></P>} />

          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}