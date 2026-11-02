import { useNavigate, Navigate } from "react-router-dom";
import Nav from "../components/Nav";
import { useAuth } from "../context/AuthContext";

export default function Landing() {
  const navigate = useNavigate();
  const { profile, loading } = useAuth();

  // Logged-in users go straight to dashboard
  if (!loading && profile) return <Navigate to="/dashboard" replace />;

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)" }}>
      <Nav />
      <main className="landing-layout">
        <div>
          <span style={{
            display: "inline-flex", alignItems: "center", gap: 6,
            color: "var(--accent)", fontSize: 13, fontWeight: 600,
            letterSpacing: "0.03em", marginBottom: 20,
          }}>
            FUNDING WORKSPACE FOR NONPROFITS
          </span>
          <h1 className="landing-title" style={{ color: "#fff", marginBottom: 20 }}>
            Find funding.
            <br />
            Focus on the work.
          </h1>
          <p style={{
            color: "var(--text-muted)", fontSize: 17, maxWidth: 520,
            lineHeight: 1.7, marginBottom: 32,
          }}>
            One practical workspace to discover relevant grants, organize
            applications, and prepare clear, funder-ready proposals.
          </p>
          <div style={{ display: "flex", gap: 12 }}>
            <button
              onClick={() => navigate("/login")}
              style={{
                background: "var(--accent-dim)", border: "none", color: "#fff",
                padding: "14px 28px", borderRadius: 10,
                fontSize: 15, fontWeight: 700, cursor: "pointer",
              }}
            >
              Get started
            </button>
            <button
              onClick={() => navigate("/login")}
              style={{
                background: "transparent", border: "1px solid var(--border)",
                color: "#fff", padding: "14px 28px", borderRadius: 10,
                fontSize: 15, fontWeight: 600, cursor: "pointer",
              }}
            >
              Sign In
            </button>
          </div>
        </div>

        {/* Workspace features */}
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {[
            { icon: "01", title: "Find relevant grants", desc: "Search opportunities and review how they align with your work." },
            { icon: "02", title: "Prepare applications", desc: "Develop proposal sections around each funder’s requirements." },
            { icon: "03", title: "Plan your budget", desc: "Build a clear, location-aware budget with compliance checks." },
            { icon: "04", title: "Work with partners", desc: "Discover organizations with complementary missions." },
          ].map(f => (
            <div className="landing-feature" key={f.title}>
              <div className="landing-feature-icon" style={{ fontSize: 12, fontWeight: 700 }}>
                {f.icon}
              </div>
              <div>
                <p style={{ fontWeight: 650, color: "#fff", fontSize: 14, margin: "0 0 4px" }}>{f.title}</p>
                <p style={{ color: "var(--text-muted)", fontSize: 13, margin: 0, lineHeight: 1.55 }}>{f.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}