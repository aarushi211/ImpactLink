import { useState, useEffect } from "react";
import { Nav, GrantCard, SectionHeader, EmptyState, CollabCard } from "../components";
import useGrants from "../hooks/useGrants";
import { useAuth } from "../context/AuthContext";
import api from "../services/api";

function ViewToggle({ view, onChange }) {
  const btn = (id, icon, label) => (
    <button
      key={id}
      onClick={() => onChange(id)}
      style={{
        display: "flex", alignItems: "center", gap: 7,
        background: view === id ? (id === "grants" ? "var(--accent)" : "#7c3aed") : "var(--bg-card)",
        border: `1px solid ${view === id ? (id === "grants" ? "var(--accent)" : "#7c3aed") : "var(--border)"}`,
        color: view === id ? "#fff" : "var(--text-dim)",
        padding: "9px 18px", borderRadius: 9,
        fontSize: 13, fontWeight: 700, cursor: "pointer",
        transition: "all 0.15s",
      }}
    >
      <span>{icon}</span> {label}
    </button>
  );
  return (
    <div style={{ display: "flex", gap: 8 }}>
      {btn("grants",  "◎", "Grants")}
      {btn("collabs", "⬡", "Collaborators")}
    </div>
  );
}

export default function GrantsList() {
  const { grants, proposal, hasRealData } = useGrants();
  const { profile } = useAuth();

  const [view,          setView]          = useState("grants");
  const [search,        setSearch]        = useState("");
  const [fitFilter,     setFitFilter]     = useState("all");
  const [sortBy,        setSortBy]        = useState("score");
  const [collabs,       setCollabs]       = useState([]);
  const [collabLoading, setCollabLoading] = useState(false);
  const [collabError,   setCollabError]   = useState(null);
  const [collabFetched, setCollabFetched] = useState(false);

  useEffect(() => {
    if (view !== "collabs" || collabFetched || !proposal) return;
    setCollabLoading(true);
    setCollabError(null);
    api.post("/api/collab/match", {
      proposal: proposal,
      ngo_id: profile ? profile.id : null,
      top_k: 6,
    })
      .then(function(res) {
        setCollabs(res.data.collabs || []);
        setCollabFetched(true);
      })
      .catch(function(e) {
        setCollabError(
          (e && e.response && e.response.data && e.response.data.detail)
            ? e.response.data.detail
            : "Could not load collaborator matches."
        );
      })
      .finally(function() {
        setCollabLoading(false);
      });
  }, [view, collabFetched, proposal, profile]);

  const filteredGrants = grants
    .filter(function(g) { return fitFilter === "all" || g.fit_level === fitFilter; })
    .filter(function(g) {
      var s = search.toLowerCase();
      var fa = Array.isArray(g.focus_areas) ? g.focus_areas.join(" ") : (g.focus_areas || "");
      return g.title.toLowerCase().includes(s) ||
             g.agency.toLowerCase().includes(s) ||
             fa.toLowerCase().includes(s);
    })
    .sort(function(a, b) {
      return sortBy === "score"
        ? b.similarity_score - a.similarity_score
        : a.title.localeCompare(b.title);
    });

  const filteredCollabs = collabs
    .filter(function(c) {
      var s = search.toLowerCase();
      return c.org_name.toLowerCase().includes(s) ||
             (c.mission || "").toLowerCase().includes(s) ||
             (c.cause_area || "").toLowerCase().includes(s) ||
             (c.shared_focus || "").toLowerCase().includes(s);
    })
    .sort(function(a, b) {
      return sortBy === "score"
        ? b.similarity_score - a.similarity_score
        : a.org_name.localeCompare(b.org_name);
    });

  var isGrants  = view === "grants";
  var isCollabs = view === "collabs";

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)" }}>
      <Nav />
      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "40px" }}>

        <SectionHeader
          label="Grant Intelligence"
          title={isGrants ? "Matched Grants" : "NGO Collaborators"}
          subtitle={
            isGrants
              ? (filteredGrants.length + " grants ranked by AI match score" + (hasRealData ? " for your proposal" : " (demo data)"))
              : collabFetched
                ? (filteredCollabs.length + " NGOs with aligned mission" + (profile ? " — excluding your org" : ""))
                : "Mission-aligned NGOs for joint applications & partnerships"
          }
        />

        <div style={{ display: "flex", gap: 12, marginBottom: 24, flexWrap: "wrap", alignItems: "center" }}>
          <ViewToggle view={view} onChange={function(v) { setView(v); setSearch(""); }} />

          <div style={{ position: "relative", flex: 1, minWidth: 200 }}>
            <span style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", color: "#444", fontSize: 16 }}>⌕</span>
            <input
              value={search}
              onChange={function(e) { setSearch(e.target.value); }}
              placeholder={isGrants ? "Search grants, agencies, focus areas…" : "Search org name, mission, cause area…"}
              style={{
                width: "100%", background: "var(--bg-card)", border: "1px solid var(--border)",
                borderRadius: 10, padding: "10px 14px 10px 40px",
                color: "#fff", fontSize: 14, outline: "none", boxSizing: "border-box",
              }}
            />
          </div>

          {isGrants && (
            <div style={{ display: "flex", gap: 6 }}>
              {["all", "strong", "moderate", "weak"].map(function(f) {
                return (
                  <button
                    key={f}
                    onClick={function() { setFitFilter(f); }}
                    style={{
                      background: fitFilter === f ? "var(--accent)" : "var(--bg-card)",
                      border: "1px solid " + (fitFilter === f ? "var(--accent)" : "var(--border)"),
                      color: fitFilter === f ? "#fff" : "var(--text-dim)",
                      padding: "8px 16px", borderRadius: 8,
                      fontSize: 13, fontWeight: 600, cursor: "pointer",
                      textTransform: "capitalize",
                    }}
                  >
                    {f === "all" ? "All" : f}
                  </button>
                );
              })}
            </div>
          )}

          <select
            value={sortBy}
            onChange={function(e) { setSortBy(e.target.value); }}
            style={{
              background: "var(--bg-card)", border: "1px solid var(--border)",
              color: "var(--text-dim)", padding: "8px 14px",
              borderRadius: 8, fontSize: 13, cursor: "pointer", outline: "none",
            }}
          >
            <option value="score">{isGrants ? "Best Match" : "Best Alignment"}</option>
            <option value="title">{isGrants ? "A–Z" : "Name A–Z"}</option>
          </select>
        </div>

        {isGrants && (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {filteredGrants.length > 0
              ? filteredGrants.map(function(grant) { return <GrantCard key={grant.grant_id} grant={grant} />; })
              : <EmptyState icon="◎" title="No grants match your filters" subtitle="Try adjusting your search or fit level filter" />
            }
          </div>
        )}

        {isCollabs && (
          <div>
            {collabLoading && (
              <div style={{ textAlign: "center", padding: "60px 0" }}>
                <div style={{
                  width: 36, height: 36, margin: "0 auto 16px",
                  border: "3px solid #1e1e30", borderTop: "3px solid #7c3aed",
                  borderRadius: "50%", animation: "spin 0.8s linear infinite",
                }} />
                <style>{"@keyframes spin { to { transform: rotate(360deg); } }"}</style>
                <p style={{ color: "#444", fontSize: 13 }}>Finding mission-aligned NGOs…</p>
              </div>
            )}

            {collabError && !collabLoading && (
              <div style={{ background: "#2d0f0f", border: "1px solid #7f1d1d", borderRadius: 10, padding: "16px 20px", color: "var(--red)", fontSize: 13 }}>
                ⚠ {collabError}
              </div>
            )}

            {!collabLoading && !collabError && !proposal && (
              <EmptyState icon="⬡" title="Upload a proposal first" subtitle="Collaborator matching is based on your mission and activities." />
            )}

            {!collabLoading && !collabError && proposal && collabFetched && filteredCollabs.length === 0 && (
              <EmptyState icon="⬡" title="No collaborators found" subtitle={search ? "Try a different search term" : "No other NGOs with similar missions registered yet."} />
            )}

            {!collabLoading && filteredCollabs.length > 0 && (
              <div>
                <div style={{ background: "#160d2a", border: "1px solid #3b1f6e", borderRadius: 10, padding: "12px 18px", marginBottom: 18, display: "flex", alignItems: "center", gap: 12 }}>
                  <span style={{ fontSize: 18 }}>⬡</span>
                  <div>
                    <p style={{ color: "#a78bfa", fontWeight: 700, fontSize: 13, margin: "0 0 2px" }}>Collaboration opportunities</p>
                    <p style={{ color: "#555", fontSize: 12, margin: 0 }}>NGOs with the most similar mission, activities, and SDG alignment. Reach out to explore joint applications or partnerships.</p>
                  </div>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  {filteredCollabs.map(function(collab) { return <CollabCard key={collab.ngo_id} collab={collab} />; })}
                </div>
              </div>
            )}
          </div>
        )}

      </div>
    </div>
  );
}