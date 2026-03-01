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
      <div style={{
        maxWidth: 1100, margin: "0 auto",
        padding: "100px 40px 60px",
        display: "grid", gridTemplateColumns: "1fr 1fr",
        gap: 60, alignItems: "center",
      }}>
        <div>
          <span style={{
            display: "inline-flex", alignItems: "center", gap: 6,
            background: "#1a1a2e", border: "1px solid #2e2e4e",
            color: "var(--accent)", padding: "6px 14px", borderRadius: 20,
            fontSize: 12, fontWeight: 600, marginBottom: 24,
          }}>
            ✦ AI-Powered NGO Intelligence
          </span>
          <h1 style={{
            fontSize: 52, fontWeight: 800, letterSpacing: "-0.04em",
            color: "#fff", lineHeight: 1.1, marginBottom: 20,
          }}>
            Scale Your NGO's Impact with{" "}
            <span style={{ color: "var(--accent)" }}>Intelligent Grant Strategy</span>
          </h1>
          <p style={{
            color: "var(--text-muted)", fontSize: 17,
            lineHeight: 1.7, marginBottom: 36,
          }}>
            ImpactLink AI helps NGOs find funding, match with funders,
            and draft winning proposals — all in one place.
          </p>
          <div style={{ display: "flex", gap: 12 }}>
            <button
              onClick={() => navigate("/login")}
              style={{
                background: "var(--accent)", border: "none", color: "#fff",
                padding: "14px 28px", borderRadius: 10,
                fontSize: 15, fontWeight: 700, cursor: "pointer",
              }}
            >
              Get Started Free →
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

        {/* Feature cards */}
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {[
            { icon: "✦", title: "AI Grant Matching",        desc: "Upload your proposal, get ranked matches with fit scores and explanations." },
            { icon: "✍", title: "Smart Proposal Drafting",  desc: "Build from scratch or let agents rewrite for each funder's priorities." },
            { icon: "💰", title: "Locality-Aware Budgets",  desc: "Cost-of-living adjusted line-item budgets with a built-in revision chatbot." },
            { icon: "🤝", title: "NGO Collaboration",       desc: "Connect with organizations working on the same mission for joint proposals." },
          ].map(f => (
            <div key={f.title} style={{
              background: "var(--bg-card)", border: "1px solid var(--border)",
              borderRadius: 14, padding: "18px 22px",
              display: "flex", gap: 16, alignItems: "flex-start",
            }}>
              <div style={{
                width: 38, height: 38, borderRadius: 10, flexShrink: 0,
                background: "#1a1a2e",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 17, color: "var(--accent)",
              }}>{f.icon}</div>
              <div>
                <p style={{ fontWeight: 700, color: "#fff", fontSize: 14, margin: "0 0 3px" }}>{f.title}</p>
                <p style={{ color: "var(--text-muted)", fontSize: 12, margin: 0, lineHeight: 1.5 }}>{f.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}