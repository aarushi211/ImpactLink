import { useNavigate } from "react-router-dom";
import FitBadge from "./FitBadge";
import EligibilityStatus from "./EligibilityStatus";
import GrantFreshness from "./GrantFreshness";

export default function GrantCard({ grant, compact = false }) {
  const navigate = useNavigate();
  const scoreColor = (s) => s >= 60 ? "var(--accent)" : s >= 45 ? "var(--yellow)" : "var(--red)";

  // focus_areas can be a string ("Education, Health") or array ["Education", "Health"]
  const focusAreas = Array.isArray(grant.focus_areas)
    ? grant.focus_areas
    : (grant.focus_areas || "").split(",").map(f => f.trim()).filter(Boolean);

  return (
    <div
      onClick={() => navigate(`/grants/${grant.grant_id}`)}
      role="link" tabIndex={0}
      onKeyDown={event => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); navigate(`/grants/${grant.grant_id}`); }
      }}
      style={{
        background: "var(--bg-card)", border: "1px solid var(--border)",
        borderRadius: 14, padding: compact ? "16px 20px" : "20px 24px",
        cursor: "pointer", display: "grid",
        gridTemplateColumns: "1fr auto auto",
        alignItems: "center", gap: 20,
        transition: "border-color 0.15s",
      }}
      onMouseEnter={e => e.currentTarget.style.borderColor = "var(--accent)"}
      onMouseLeave={e => e.currentTarget.style.borderColor = "var(--border)"}
    >
      {/* Left — title + meta */}
      <div style={{ minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
          <FitBadge level={grant.fit_level} />
          {grant.close_date
            ? <span style={{ fontSize: 11, color: "var(--red)", fontWeight: 500 }}>Due {grant.close_date}</span>
            : <span style={{ fontSize: 11, color: "#444" }}>Rolling deadline</span>
          }
        </div>
        <p style={{ fontWeight: 700, fontSize: 15, color: "#fff", margin: "0 0 3px", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {grant.title}
        </p>
        <EligibilityStatus result={grant.eligibility_check} />
        <GrantFreshness grant={grant} />
        <p style={{ color: "var(--text-muted)", fontSize: 13, margin: "0 0 8px" }}>{grant.agency}</p>

        {!compact && (
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {focusAreas.slice(0, 3).map(f => (
              <span key={f} style={{
                background: "#1a1a2e", color: "#888",
                border: "1px solid #2a2a3e", borderRadius: 6,
                padding: "2px 8px", fontSize: 11,
              }}>{f}</span>
            ))}
          </div>
        )}
      </div>

      {/* Center — budget (hidden in compact mode) */}
      {!compact && (
        <div style={{ textAlign: "center", flexShrink: 0 }}>
          <p style={{ color: "#444", fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", margin: "0 0 4px" }}>Award</p>
          <p style={{ color: "#bbb", fontSize: 13, fontWeight: 600, margin: 0 }}>
            {grant.award_floor > 0 ? `$${(grant.award_floor / 1000).toFixed(0)}K` : "—"}
            {" – "}
            {grant.award_ceiling > 0 ? `$${(grant.award_ceiling / 1000).toFixed(0)}K` : "Open"}
          </p>
        </div>
      )}

      {/* Right — score + arrow */}
      <div style={{ display: "flex", alignItems: "center", gap: 14, flexShrink: 0 }}>
        {Number.isFinite(grant.similarity_score) && <div style={{ textAlign: "center" }}>
          <div style={{
            width: compact ? 48 : 56, height: compact ? 48 : 56,
            borderRadius: "50%",
            border: `3px solid ${scoreColor(grant.similarity_score)}`,
            display: "flex", alignItems: "center", justifyContent: "center",
            background: "var(--bg)",
          }}>
            <span style={{ fontSize: compact ? 12 : 14, fontWeight: 800, color: scoreColor(grant.similarity_score) }}>
              {grant.similarity_score}%
            </span>
          </div>
          <span style={{ fontSize: 10, color: "#444", display: "block", marginTop: 3 }}>match</span>
        </div>}
        <span style={{ color: "var(--accent)", fontSize: 18 }}>→</span>
      </div>
    </div>
  );
}
