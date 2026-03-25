import { useParams, useNavigate } from "react-router-dom";
import { Nav, FitBadge, ScoreRing } from "../components";
import useGrants from "../hooks/useGrants";

export default function GrantDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { grants, loading } = useGrants();
  const grant = grants.find(g => String(g.grant_id) === String(id));

  if (loading) return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <Nav />
      <p style={{ color: "var(--text-muted)" }}>Loading...</p>
    </div>
  );

  if (!grant) return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <Nav />
      <div style={{ textAlign: "center", color: "var(--text-muted)" }}>
        <p style={{ fontSize: 48, marginBottom: 16 }}>◎</p>
        <p style={{ fontSize: 18, fontWeight: 600, color: "#fff", marginBottom: 16 }}>Grant not found</p>
        <button onClick={() => navigate("/grants")} style={{ background: "var(--accent)", border: "none", color: "#fff", padding: "10px 24px", borderRadius: 8, cursor: "pointer", fontWeight: 600 }}>
          Back to Grants
        </button>
      </div>
    </div>
  );

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)" }}>
      <Nav />
      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "40px" }}>

        {/* Back */}
        <button
          onClick={() => navigate("/grants")}
          style={{ background: "none", border: "none", color: "var(--text-dim)", fontSize: 14, cursor: "pointer", marginBottom: 24, display: "flex", alignItems: "center", gap: 6, padding: 0 }}
        >
          ← Back to Grants
        </button>

        {/* Header */}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 24, marginBottom: 32 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
              <FitBadge level={grant.fit_level} />
              {grant.close_date
                ? <span style={{ fontSize: 12, color: "var(--red)", fontWeight: 600 }}>⏰ Due {grant.close_date}</span>
                : <span style={{ fontSize: 12, color: "#444" }}>Rolling deadline</span>
              }
            </div>
            <h1 style={{ fontSize: 28, fontWeight: 800, letterSpacing: "-0.03em", color: "#fff", margin: "0 0 8px" }}>
              {grant.title}
            </h1>
            <p style={{ color: "var(--text-muted)", fontSize: 15, margin: 0 }}>
              {grant.agency} · {grant.top_agency}
            </p>
          </div>
          <div style={{ flexShrink: 0 }}>
            <ScoreRing score={grant.similarity_score} size={80} />
          </div>
        </div>

        {/* Two Column */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 340px", gap: 24 }}>

          {/* Left */}
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

            {/* Description */}
            <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 16, padding: 24 }}>
              <h3 style={{ fontWeight: 700, color: "#fff", fontSize: 15, margin: "0 0 12px" }}>About This Grant</h3>
              <p style={{ color: "#bbb", fontSize: 14, lineHeight: 1.7, margin: 0 }}>{grant.description}</p>
            </div>

            {/* AI Match Explanation */}
            <div style={{ background: "#0f0f1e", border: "1px solid #2a2a4e", borderRadius: 16, padding: 24 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
                <span>✦</span>
                <h3 style={{ fontWeight: 700, color: "var(--accent)", fontSize: 15, margin: 0 }}>Why This Matches Your Profile</h3>
              </div>
              <p style={{ color: "#bbb", fontSize: 14, lineHeight: 1.7, margin: "0 0 14px" }}>{grant.match_explanation}</p>
              <div style={{ background: "#1a1a30", borderRadius: 10, padding: "12px 16px", display: "flex", gap: 10 }}>
                <span style={{ flexShrink: 0 }}>💡</span>
                <p style={{ color: "#888", fontSize: 13, lineHeight: 1.6, margin: 0 }}>
                  <strong style={{ color: "#bbb" }}>Tip: </strong>{grant.application_tip}
                </p>
              </div>
            </div>

            {/* Eligibility */}
            <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 16, padding: 24 }}>
              <h3 style={{ fontWeight: 700, color: "#fff", fontSize: 15, margin: "0 0 12px" }}>Eligibility</h3>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {(grant.eligibility || []).map((e, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span style={{ color: "var(--green)", fontSize: 14, flexShrink: 0 }}>✓</span>
                    <span style={{ color: "#bbb", fontSize: 14 }}>{e}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* How to Apply */}
            <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 16, padding: 24 }}>
              <h3 style={{ fontWeight: 700, color: "#fff", fontSize: 15, margin: "0 0 16px" }}>How to Apply</h3>
              <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                {(grant.steps || []).map((step, i) => (
                  <div key={i} style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
                    <div style={{
                      width: 28, height: 28, borderRadius: "50%", flexShrink: 0,
                      background: "#1a1a2e", border: "1px solid #2a2a4e",
                      display: "flex", alignItems: "center", justifyContent: "center",
                      fontSize: 12, fontWeight: 700, color: "var(--accent)",
                    }}>
                      {i + 1}
                    </div>
                    <p style={{ color: "#bbb", fontSize: 14, margin: 0, paddingTop: 4, lineHeight: 1.5 }}>{step}</p>
                  </div>
                ))}
              </div>
              <a
                href={grant.application_url}
                target="_blank"
                rel="noreferrer"
                style={{
                  display: "block", marginTop: 20, textAlign: "center",
                  background: "transparent", border: "1px solid var(--border)",
                  color: "var(--text-dim)", padding: "10px", borderRadius: 8,
                  fontSize: 13, fontWeight: 600,
                }}
              >
                View on Grants.gov ↗
              </a>
            </div>
          </div>

          {/* Right Sidebar */}
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <button
              onClick={() => navigate(`/draft?grant=${grant.grant_id}`)}
              style={{
                width: "100%", background: "var(--accent)", border: "none",
                color: "#fff", padding: "14px", borderRadius: 12,
                fontSize: 15, fontWeight: 700, cursor: "pointer",
              }}
            >
              ✍ Draft Proposal with AI
            </button>
            <button style={{
              width: "100%", background: "var(--bg-card)", border: "1px solid var(--border)",
              color: "#fff", padding: "14px", borderRadius: 12,
              fontSize: 15, fontWeight: 600, cursor: "pointer",
            }}>
              ＋ Add to Tracker
            </button>
            <button
               onClick={() => navigate(`/budget?grant=${grant.grant_id}`)}
               style={{
                 width: "100%", background: "transparent", border: "1px solid #7c6fef",
                 color: "#7c6fef", padding: "12px", borderRadius: 12,
                 fontSize: 14, fontWeight: 700, cursor: "pointer",
               }}
             >
               💰 Build Budget with AI
             </button>

            {/* Grant Details */}
            <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 16, padding: 24 }}>
              <h3 style={{ fontWeight: 700, color: "#fff", fontSize: 14, margin: "0 0 16px" }}>Grant Details</h3>
              {[
                { label: "Opportunity #", value: grant.opportunity_number },
                { label: "Award Range",   value: grant.award_floor > 0 ? `$${(grant.award_floor/1000).toFixed(0)}K – $${(grant.award_ceiling/1000).toFixed(0)}K` : "Not specified" },
                { label: "Deadline",      value: grant.close_date || "Rolling" },
                { label: "Contact",       value: grant.contact_email },
              ].map(row => (
                <div key={row.label} style={{ marginBottom: 14 }}>
                  <p style={{ color: "#444", fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", margin: "0 0 3px" }}>{row.label}</p>
                  <p style={{ color: "#bbb", fontSize: 13, margin: 0, wordBreak: "break-all" }}>{row.value}</p>
                </div>
              ))}
            </div>

            {/* Focus Areas */}
            <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 16, padding: 24 }}>
              <h3 style={{ fontWeight: 700, color: "#fff", fontSize: 14, margin: "0 0 12px" }}>Focus Areas</h3>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {(Array.isArray(grant.focus_areas) ? grant.focus_areas : (grant.focus_areas || "").split(",").map(f => f.trim()).filter(Boolean)).map(f => (
                  <span key={f} style={{
                    background: "#1a1a2e", color: "var(--accent)",
                    border: "1px solid #2e2e4e", borderRadius: 6,
                    padding: "4px 10px", fontSize: 12, fontWeight: 600,
                  }}>{f}</span>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}