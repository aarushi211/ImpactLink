import { useNavigate, useLocation } from "react-router-dom";

export default function Nav() {
  const navigate = useNavigate();
  const { pathname } = useLocation();

  const links = [
    { label: "Dashboard",       path: "/dashboard" },
    { label: "View Grants",     path: "/grants" },
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
      <div
        onClick={() => navigate("/")}
        style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}
      >
        <span style={{ fontSize: 22 }}>⊚</span>
        <span style={{ fontWeight: 800, fontSize: 18, color: "#fff", letterSpacing: "-0.02em" }}>
          ImpactLink AI
        </span>
      </div>

      <div style={{ display: "flex", gap: 32, fontSize: 14 }}>
        {links.map(link => (
          <span
            key={link.path}
            onClick={() => navigate(link.path)}
            style={{
              cursor: "pointer",
              color: pathname === link.path ? "var(--accent)" : "var(--text-dim)",
              fontWeight: pathname === link.path ? 600 : 400,
              transition: "color 0.15s",
            }}
            onMouseEnter={e => { if (pathname !== link.path) e.target.style.color = "#bbb"; }}
            onMouseLeave={e => { if (pathname !== link.path) e.target.style.color = "var(--text-dim)"; }}
          >
            {link.label}
          </span>
        ))}
      </div>

      <div style={{
        width: 36, height: 36, borderRadius: "50%",
        background: "linear-gradient(135deg, var(--accent), var(--accent-dim))",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontWeight: 800, fontSize: 14, color: "#fff", cursor: "pointer",
      }}>
        A
      </div>
    </nav>
  );
}