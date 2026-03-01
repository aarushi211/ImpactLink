/**
 * CollabCard — displays a single NGO collaboration match.
 *
 * Props:
 *   collab  — CollabResult object from /api/collab/match
 */

const COLLAB_TYPE_COLOR = {
  "Joint proposal":    "var(--accent)",
  "Sub-grant":         "var(--yellow)",
  "Referral":          "var(--green)",
  "Data sharing":      "#a78bfa",
  "Capacity building": "var(--pink)",
};

const SCORE_COLOR = (s) =>
  s >= 70 ? "var(--accent)" : s >= 50 ? "var(--yellow)" : "var(--green)";

export default function CollabCard({ collab }) {
  const typeColor = COLLAB_TYPE_COLOR[collab.collab_type] || "var(--accent)";
  const scoreColor = SCORE_COLOR(collab.similarity_score);

  return (
    <div style={{
      background: "var(--bg-card)", border: "1px solid var(--border)",
      borderRadius: 14, padding: "20px 24px",
      display: "grid", gridTemplateColumns: "1fr auto",
      alignItems: "start", gap: 20,
      transition: "border-color 0.15s",
    }}
    onMouseEnter={e => e.currentTarget.style.borderColor = typeColor}
    onMouseLeave={e => e.currentTarget.style.borderColor = "var(--border)"}
    >
      {/* Left — org info + explanation */}
      <div style={{ minWidth: 0 }}>

        {/* Top row: collab type badge + location */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
          <span style={{
            background: `${typeColor}22`, color: typeColor,
            border: `1px solid ${typeColor}55`,
            borderRadius: 20, padding: "2px 10px",
            fontSize: 10, fontWeight: 700, letterSpacing: "0.05em",
          }}>
            {collab.collab_type}
          </span>
          {collab.location && (
            <span style={{ color: "#444", fontSize: 11 }}>
              📍 {collab.location}
            </span>
          )}
          {collab.shared_focus && (
            <span style={{
              background: "#1a1a2e", color: "#888",
              border: "1px solid #2a2a3e", borderRadius: 6,
              padding: "2px 8px", fontSize: 10,
            }}>
              {collab.shared_focus}
            </span>
          )}
        </div>

        {/* Org name */}
        <p style={{
          fontWeight: 700, fontSize: 16, color: "#fff",
          margin: "0 0 4px", whiteSpace: "nowrap",
          overflow: "hidden", textOverflow: "ellipsis",
        }}>
          {collab.org_name}
        </p>

        {/* Mission */}
        {collab.mission && (
          <p style={{ color: "var(--text-muted)", fontSize: 13, margin: "0 0 10px", lineHeight: 1.5 }}>
            {collab.mission.length > 140
              ? collab.mission.slice(0, 140) + "…"
              : collab.mission}
          </p>
        )}

        {/* Why collaborate */}
        <div style={{
          background: "#0d0d1a", border: "1px solid #1e1e30",
          borderLeft: `3px solid ${typeColor}`,
          borderRadius: 8, padding: "10px 14px", marginBottom: 12,
        }}>
          <p style={{ color: "#555", fontSize: 10, fontWeight: 700,
            textTransform: "uppercase", letterSpacing: "0.08em", margin: "0 0 4px" }}>
            Why collaborate
          </p>
          <p style={{ color: "#bbb", fontSize: 12, margin: 0, lineHeight: 1.6 }}>
            {collab.collab_explanation}
          </p>
        </div>

        {/* Tags row: SDGs + activities */}
        <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
          {(collab.sdgs || []).slice(0, 3).map(sdg => (
            <span key={sdg} style={{
              background: "#1a1a2e", color: "var(--accent)",
              border: "1px solid #2e2e4e", borderRadius: 5,
              padding: "2px 7px", fontSize: 10, fontWeight: 600,
            }}>
              {sdg.split(":")[0]}
            </span>
          ))}
          {(collab.key_activities || []).slice(0, 2).map(act => (
            <span key={act} style={{
              background: "#1a1a2e", color: "#666",
              border: "1px solid #2a2a3e", borderRadius: 5,
              padding: "2px 7px", fontSize: 10,
            }}>
              {act.length > 24 ? act.slice(0, 24) + "…" : act}
            </span>
          ))}
        </div>

        {/* Footer: website + team size */}
        {(collab.website || collab.team_size) && (
          <div style={{ display: "flex", gap: 16, marginTop: 10, alignItems: "center" }}>
            {collab.website && (
              <a href={collab.website} target="_blank" rel="noopener noreferrer"
                onClick={e => e.stopPropagation()}
                style={{ color: typeColor, fontSize: 11, fontWeight: 600, textDecoration: "none" }}>
                🔗 Visit website
              </a>
            )}
            {collab.team_size && (
              <span style={{ color: "#444", fontSize: 11 }}>
                👥 {collab.team_size}
              </span>
            )}
            {collab.founding_year && (
              <span style={{ color: "#444", fontSize: 11 }}>
                Est. {collab.founding_year}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Right — similarity score ring */}
      <div style={{ textAlign: "center", flexShrink: 0 }}>
        <div style={{
          width: 60, height: 60, borderRadius: "50%",
          border: `3px solid ${scoreColor}`,
          display: "flex", alignItems: "center", justifyContent: "center",
          background: "var(--bg)", marginBottom: 4,
        }}>
          <span style={{ fontSize: 14, fontWeight: 800, color: scoreColor }}>
            {Math.round(collab.similarity_score)}%
          </span>
        </div>
        <span style={{ fontSize: 10, color: "#444" }}>alignment</span>
      </div>
    </div>
  );
}