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
  ];

  return (
    <nav className="app-nav" style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "0 40px", height: 64,
      borderBottom: "1px solid var(--border)",
      background: "var(--bg-nav)",
      position: "sticky", top: 0, zIndex: 100,
    }}>
      {/* Logo */}
      <div
        onClick={() => navigate("/")}
        style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}
      >
        <span style={{
          width: 32, height: 32, display: "grid", placeItems: "center",
          borderRadius: 9, background: "#1a1a2e", color: "var(--accent)",
          fontSize: 12, fontWeight: 800, letterSpacing: "0.02em",
        }}>IL</span>
        <span style={{ fontWeight: 700, fontSize: 17, color: "#fff",
          letterSpacing: "-0.025em" }}>
          ImpactLink
        </span>
      </div>

      {/* Links */}
      {profile && (
        <div className="app-nav-links">
          {links.map(link => (
            <button
              className="app-nav-link"
              key={link.path}
              type="button"
              aria-current={pathname === link.path ? "page" : undefined}
              onClick={() => navigate(link.path)}
            >
              {link.label}
            </button>
          ))}
        </div>
      )}

      {/* Right — avatar / auth */}
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        {profile ? (
          <>
            <span
              onClick={() => navigate("/profile")}
              style={{
                color: "var(--text-muted)", fontSize: 12, cursor: "pointer",
                transition: "color 0.15s",
              }}
              onMouseEnter={e => e.target.style.color = "#fff"}
              onMouseLeave={e => e.target.style.color = "var(--text-muted)"}
            >
              {profile.org_name.length > 18
                ? profile.org_name.slice(0,18) + "…"
                : profile.org_name}
            </span>
            <div
              onClick={() => navigate("/profile")}
              style={{
                width: 36, height: 36, borderRadius: "50%", cursor: "pointer",
                background: "var(--accent-dim)",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontWeight: 800, fontSize: 14, color: "#fff",
                border: "2px solid transparent",
                transition: "border-color 0.15s",
              }}
              onMouseEnter={e => e.currentTarget.style.borderColor = "var(--accent)"}
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
              background: "transparent", border: "1px solid var(--border)",
              color: "var(--text-muted)", padding: "5px 12px", borderRadius: 6,
              fontSize: 11, fontWeight: 600, cursor: "pointer",
              transition: "all 0.15s",
            }}
            onMouseEnter={e => { e.target.style.color = "var(--red)"; e.target.style.borderColor = "var(--red)"; }}
            onMouseLeave={e => { e.target.style.color = "var(--text-muted)"; e.target.style.borderColor = "var(--border)"; }}
          >
            Sign Out
          </button>
        )}
      </div>
    </nav>
  );
}