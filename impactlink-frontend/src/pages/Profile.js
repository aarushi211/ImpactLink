import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Nav } from "../components";
import { useAuth } from "../context/AuthContext.js";

const SDG_OPTIONS = [
  "SDG 1: No Poverty", "SDG 2: Zero Hunger", "SDG 3: Good Health",
  "SDG 4: Quality Education", "SDG 5: Gender Equality", "SDG 6: Clean Water",
  "SDG 7: Clean Energy", "SDG 8: Decent Work", "SDG 10: Reduced Inequalities",
  "SDG 11: Sustainable Cities", "SDG 13: Climate Action", "SDG 17: Partnerships",
];
const CAUSE_AREAS = [
  "Education & Youth", "Health & Wellbeing", "Economic Empowerment",
  "Environment & Climate", "Women & Gender", "Food Security",
  "Humanitarian Aid", "Human Rights", "Community Development",
  "Arts & Culture", "Technology & Innovation",
];

const inputStyle = {
  width: "100%", background: "#111120",
  border: "1px solid #1e1e30", borderRadius: 8,
  color: "#e0e0f0", padding: "9px 12px",
  fontSize: 13, outline: "none", boxSizing: "border-box",
};

function Section({ title, children }) {
  return (
    <div style={{
      background: "var(--bg-card)", border: "1px solid var(--border)",
      borderRadius: 12, padding: "20px 24px", marginBottom: 16,
    }}>
      <p style={{ margin: "0 0 16px", fontWeight: 700, color: "#fff", fontSize: 14,
        borderBottom: "1px solid var(--border)", paddingBottom: 12 }}>
        {title}
      </p>
      {children}
    </div>
  );
}

function Field({ label, children }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <label style={{ display: "block", color: "#555", fontSize: 11,
        fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em",
        marginBottom: 6 }}>
        {label}
      </label>
      {children}
    </div>
  );
}

export default function Profile() {
  const navigate = useNavigate();
  const { profile, logout, updateProfile } = useAuth();

  const [saving,  setSaving]  = useState(false);
  const [saved,   setSaved]   = useState(false);
  const [error,   setError]   = useState("");

  // editable fields — seeded from profile
  const [mission,    setMission]    = useState(profile?.mission    || "");
  const [location,   setLocation]   = useState(profile?.location   || "");
  const [causeArea,  setCauseArea]  = useState(profile?.cause_area || "");
  const [website,    setWebsite]    = useState(profile?.website    || "");
  const [teamSize,   setTeamSize]   = useState(profile?.team_size  || "");
  const [geoFocus,   setGeoFocus]   = useState((profile?.geographic_focus || [])[0] || "");
  const [selSDGs,    setSelSDGs]    = useState(profile?.sdgs || []);
  const [collabOpen, setCollabOpen] = useState(profile?.collab_open ?? true);
  const [collabInts, setCollabInts] = useState((profile?.collab_interests || []).join(", "));

  const [activities, setActivities] = useState(
    (profile?.key_activities || []).join("\n")
  );

  const toggleSDG = (s) =>
    setSelSDGs(prev => prev.includes(s) ? prev.filter(x => x !== s) : [...prev, s]);

  const handleSave = async () => {
    setSaving(true); setError(""); setSaved(false);
    try {
      await updateProfile({
        mission,
        location,
        cause_area:       causeArea,
        website,
        team_size:        teamSize,
        geographic_focus: geoFocus ? [geoFocus] : [],
        sdgs:             selSDGs,
        collab_open:      collabOpen,
        collab_interests: collabInts.split(",").map(s => s.trim()).filter(Boolean),
        key_activities:   activities.split("\n").map(s => s.trim()).filter(Boolean),
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (err) {
      setError(err?.response?.data?.detail || "Save failed.");
    } finally { setSaving(false); }
  };

  if (!profile) {
    return (
      <div style={{ minHeight: "100vh", background: "var(--bg)", display: "flex",
        flexDirection: "column" }}>
        <Nav />
        <div style={{ flex: 1, display: "flex", alignItems: "center",
          justifyContent: "center", flexDirection: "column", gap: 16 }}>
          <p style={{ color: "#555", fontSize: 15 }}>You're not signed in.</p>
          <button
            onClick={() => navigate("/login")}
            style={{ background: "var(--accent)", border: "none", color: "#fff",
              padding: "10px 24px", borderRadius: 8, fontSize: 13,
              fontWeight: 700, cursor: "pointer" }}
          >
            Sign In
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", display: "flex",
      flexDirection: "column" }}>
      <Nav />

      <div style={{ maxWidth: 900, margin: "0 auto", padding: "36px 40px 80px",
        width: "100%" }}>

        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
          marginBottom: 28 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <div style={{
              width: 56, height: 56, borderRadius: 14, flexShrink: 0,
              background: "linear-gradient(135deg, var(--accent), #4f46e5)",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontWeight: 900, fontSize: 24, color: "#fff",
            }}>
              {(profile.org_name || "?")[0].toUpperCase()}
            </div>
            <div>
              <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: "#fff",
                letterSpacing: "-0.02em" }}>
                {profile.org_name}
              </h1>
              <p style={{ margin: 0, color: "#555", fontSize: 13 }}>{profile.email}</p>
            </div>
          </div>

          <div style={{ display: "flex", gap: 10 }}>
            <button
              onClick={() => navigate("/dashboard")}
              style={{ background: "transparent", border: "1px solid var(--border)",
                color: "#888", padding: "9px 18px", borderRadius: 8,
                fontSize: 13, fontWeight: 600, cursor: "pointer" }}
            >
              ← Dashboard
            </button>
            <button
              onClick={logout}
              style={{ background: "transparent", border: "1px solid #2d0f0f",
                color: "var(--red)", padding: "9px 18px", borderRadius: 8,
                fontSize: 13, fontWeight: 600, cursor: "pointer" }}
            >
              Sign Out
            </button>
          </div>
        </div>

        {/* Stats row */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)",
          gap: 12, marginBottom: 24 }}>
          {[
            { label: "Funding Secured", value: `$${((profile.funding_secured||0)/1000).toFixed(0)}K`, color: "var(--accent)" },
            { label: "Grants Won",      value: profile.total_won || 0,                                 color: "var(--green)" },
            { label: "Applied",         value: profile.total_applied || 0,                             color: "var(--yellow)" },
            { label: "Since",           value: profile.created_at ? new Date(profile.created_at).getFullYear() : "—", color: "#888" },
          ].map(s => (
            <div key={s.label} style={{ background: "var(--bg-card)",
              border: "1px solid var(--border)", borderRadius: 10, padding: "14px 16px" }}>
              <p style={{ margin: "0 0 4px", color: "#444", fontSize: 10,
                fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em" }}>
                {s.label}
              </p>
              <p style={{ margin: 0, color: s.color, fontWeight: 800, fontSize: 22 }}>
                {s.value}
              </p>
            </div>
          ))}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 340px", gap: 16 }}>

          {/* Left column */}
          <div>
            <Section title="Organization Profile">
              <Field label="Mission Statement">
                <textarea
                  style={{ ...inputStyle, resize: "none", minHeight: 80 }}
                  value={mission} onChange={e => setMission(e.target.value)}
                  placeholder="What is your organization's core mission?"
                />
              </Field>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <Field label="Location">
                  <input style={inputStyle} value={location}
                    onChange={e => setLocation(e.target.value)}
                    placeholder="Nairobi, Kenya" />
                </Field>
                <Field label="Team Size">
                  <select style={{ ...inputStyle, cursor: "pointer" }}
                    value={teamSize} onChange={e => setTeamSize(e.target.value)}>
                    <option value="">Select…</option>
                    {["1–5","6–15","16–50","51–200","200+"].map(s =>
                      <option key={s} value={s}>{s} people</option>)}
                  </select>
                </Field>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <Field label="Cause Area">
                  <select style={{ ...inputStyle, cursor: "pointer" }}
                    value={causeArea} onChange={e => setCauseArea(e.target.value)}>
                    <option value="">Select…</option>
                    {CAUSE_AREAS.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </Field>
                <Field label="Primary Region">
                  <input style={inputStyle} value={geoFocus}
                    onChange={e => setGeoFocus(e.target.value)}
                    placeholder="Sub-Saharan Africa" />
                </Field>
              </div>
              <Field label="Website">
                <input style={inputStyle} value={website}
                  onChange={e => setWebsite(e.target.value)}
                  placeholder="https://yourorg.org" />
              </Field>
            </Section>

            <Section title="Key Activities">
              <p style={{ color: "#444", fontSize: 12, margin: "0 0 10px" }}>
                One activity per line — used to improve grant matching and proposal drafting.
              </p>
              <textarea
                style={{ ...inputStyle, resize: "vertical", minHeight: 110 }}
                value={activities}
                onChange={e => setActivities(e.target.value)}
                placeholder={"Digital literacy workshops\nVocational training programs\nCommunity outreach"}
              />
            </Section>
          </div>

          {/* Right column */}
          <div>
            <Section title="SDG Alignment">
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {SDG_OPTIONS.map(sdg => {
                  const active = selSDGs.includes(sdg);
                  return (
                    <button key={sdg} type="button" onClick={() => toggleSDG(sdg)}
                      style={{
                        background: active ? "var(--accent)" : "#111120",
                        border: `1px solid ${active ? "var(--accent)" : "#1e1e30"}`,
                        color: active ? "#fff" : "#555",
                        borderRadius: 20, padding: "5px 10px",
                        fontSize: 11, cursor: "pointer", transition: "all 0.12s",
                      }}>
                      {sdg.split(":")[0]}
                    </button>
                  );
                })}
              </div>
            </Section>

            <Section title="NGO Collaboration">
              <p style={{ color: "#444", fontSize: 12, margin: "0 0 12px", lineHeight: 1.6 }}>
                Mark yourself as open to collaborating with other NGOs on joint proposals.
              </p>

              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
                marginBottom: 14 }}>
                <span style={{ color: "#888", fontSize: 13 }}>Open to collaboration</span>
                <div
                  onClick={() => setCollabOpen(p => !p)}
                  style={{
                    width: 44, height: 24, borderRadius: 12, cursor: "pointer",
                    background: collabOpen ? "var(--accent)" : "#1e1e30",
                    position: "relative", transition: "background 0.2s",
                    flexShrink: 0,
                  }}
                >
                  <div style={{
                    position: "absolute",
                    top: 2, left: collabOpen ? 22 : 2,
                    width: 20, height: 20, borderRadius: "50%",
                    background: "#fff", transition: "left 0.2s",
                  }} />
                </div>
              </div>

              <Field label="Collab Interests" >
                <input
                  style={inputStyle}
                  value={collabInts}
                  onChange={e => setCollabInts(e.target.value)}
                  placeholder="Climate, Education, Health equity…"
                  disabled={!collabOpen}
                />
              </Field>

              <div style={{ background: "#0d1a2e", borderRadius: 8, padding: "10px 12px",
                marginTop: 4 }}>
                <p style={{ margin: 0, color: "#7cb9f5", fontSize: 11, lineHeight: 1.6 }}>
                  🤝 NGO matching is coming soon. When enabled, your profile will appear
                  to similar organizations for potential joint proposals.
                </p>
              </div>
            </Section>
          </div>
        </div>

        {/* Save bar */}
        <div style={{
          position: "sticky", bottom: 0, background: "var(--bg-nav)",
          borderTop: "1px solid var(--border)",
          padding: "14px 0", marginTop: 4,
          display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 12,
        }}>
          {error  && <p style={{ color: "var(--red)",   fontSize: 12, margin: 0 }}>⚠ {error}</p>}
          {saved  && <p style={{ color: "var(--green)", fontSize: 12, margin: 0 }}>✓ Saved</p>}
          <button
            onClick={handleSave}
            disabled={saving}
            style={{
              background: saving ? "#1a1a28" : "var(--accent)",
              border: "none", borderRadius: 9, color: saving ? "#333" : "#fff",
              padding: "11px 28px", fontSize: 13, fontWeight: 700,
              cursor: saving ? "wait" : "pointer",
            }}
          >
            {saving ? "Saving…" : "Save Changes"}
          </button>
        </div>
      </div>
    </div>
  );
}