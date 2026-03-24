import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function Nav() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { profile, logout } = useAuth();

  const links = [
    { label: "Dashboard",       path: "/dashboard" },
    { label: "View Grants",     path: "/grants" },
    { label: "Build Proposal",  path: "/build" },
    { label: "Draft Assistant", path: "/draft" },
    { label: "Budget Builder",  path: "/budget" },
    { label: "Upload",          path: "/upload" },
  ];

  return (
    <nav style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "0 40px", height: 64,
      borderBottom: "1px solid var(--border)",
      background: "var(--bg-nav)",
      position: "sticky", top: 0, zIndex: 100,
    }}>
      {/* Logo */}
      <div
        onClick={() => navigate("/")}
        style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}
      >
        <span style={{ fontSize: 22 }}>⊚</span>
        <span style={{ fontWeight: 800, fontSize: 18, color: "#fff",
          letterSpacing: "-0.02em" }}>
          ImpactLink AI
        </span>
      </div>

      {/* Links */}
      <div style={{ display: "flex", gap: 28, fontSize: 13 }}>
        {links.map(link => (
          <span
            key={link.path}
            onClick={() => navigate(link.path)}
            style={{
              cursor: "pointer",
              color: pathname === link.path ? "var(--accent)" : "var(--text-dim)",
              fontWeight: pathname === link.path ? 600 : 400,
              transition: "color 0.15s",
              // Highlight "Build Proposal" even when not active
              ...(link.path === "/build" && pathname !== "/build" ? {
                color: "#a89ff5",
              } : {}),
            }}
            onMouseEnter={e => { if (pathname !== link.path) e.target.style.color = "#bbb"; }}
            onMouseLeave={e => {
              if (pathname !== link.path)
                e.target.style.color = link.path === "/build" ? "#a89ff5" : "var(--text-dim)";
            }}
          >
            {link.path === "/build" && (
              <span style={{ marginRight: 4, fontSize: 11 }}>✍</span>
            )}
            {link.label}
          </span>
        ))}
      </div>

      {/* Right — avatar / auth */}
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        {profile ? (
          <>
            <span
              onClick={() => navigate("/profile")}
              style={{
                color: "#555", fontSize: 12, cursor: "pointer",
                transition: "color 0.15s",
              }}
              onMouseEnter={e => e.target.style.color = "#bbb"}
              onMouseLeave={e => e.target.style.color = "#555"}
            >
              {profile.org_name.length > 18
                ? profile.org_name.slice(0,18) + "…"
                : profile.org_name}
            </span>
            <div
              onClick={() => navigate("/profile")}
              style={{
                width: 36, height: 36, borderRadius: "50%", cursor: "pointer",
                background: "linear-gradient(135deg, var(--accent), var(--accent-dim))",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontWeight: 800, fontSize: 14, color: "#fff",
                border: "2px solid transparent",
                transition: "border-color 0.15s",
              }}
              onMouseEnter={e => e.currentTarget.style.borderColor = "#a89ff5"}
              onMouseLeave={e => e.currentTarget.style.borderColor = "transparent"}
              title="View profile"
            >
              {profile.org_name[0].toUpperCase()}
            </div>
          </>
        ) : (
          <button
            onClick={() => navigate("/login")}
            style={{
              background: "transparent", border: "1px solid var(--border)",
              color: "var(--accent)", padding: "7px 18px", borderRadius: 8,
              fontSize: 13, fontWeight: 600, cursor: "pointer",
              transition: "all 0.15s",
            }}
            onMouseEnter={e => { e.target.style.background = "var(--accent)"; e.target.style.color = "#fff"; }}
            onMouseLeave={e => { e.target.style.background = "transparent"; e.target.style.color = "var(--accent)"; }}
          >
            Sign In
          </button>
        )}
        {profile && (
          <button
            onClick={logout}
            style={{
              background: "transparent", border: "1px solid #2a2a4e",
              color: "#555", padding: "5px 12px", borderRadius: 6,
              fontSize: 11, fontWeight: 600, cursor: "pointer",
              transition: "all 0.15s",
            }}
            onMouseEnter={e => { e.target.style.color = "var(--red)"; e.target.style.borderColor = "var(--red)"; }}
            onMouseLeave={e => { e.target.style.color = "#555"; e.target.style.borderColor = "#2a2a4e"; }}
          >
            Sign Out
          </button>
        )}
      </div>
    </nav>
  );
}