import { useState, useEffect, useRef } from "react";
import { Nav, GrantCard, SectionHeader, EmptyState, CollabCard } from "../components";
import useGrants from "../hooks/useGrants";
import useWorkStore from "../hooks/useWorkStore";
import useUpload from "../hooks/useUpload";
import { useAuth } from "../context/AuthContext";
import api from "../services/api";
import { removeDemoGrants } from "../services/grants";

function ViewToggle({ view, onChange }) {
  const btn = (id, icon, label) => (
    <button
      key={id}
      onClick={() => onChange(id)}
      style={{
        display: "flex", alignItems: "center", gap: 7,
        background: view === id ? "var(--accent-dim)" : "var(--bg-card)",
        border: `1px solid ${view === id ? "var(--accent-dim)" : "var(--border)"}`,
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
  const { grants, proposal, hasRealData, loading: grantsLoading } = useGrants();
  const { profile } = useAuth();
  const { proposals: savedProposals, refresh: refreshWorkStore } = useWorkStore();
  const { upload, loading: uploadLoading, error: uploadError } = useUpload();
  const uploadInputRef = useRef(null);

  const [view,          setView]          = useState("grants");
  const [search,        setSearch]        = useState("");
  const [fitFilter,     setFitFilter]     = useState("all");
  const [sortBy,        setSortBy]        = useState("score");
  const [collabs,       setCollabs]       = useState([]);
  const [collabLoading, setCollabLoading] = useState(false);
  const [collabError,   setCollabError]   = useState(null);
  const [collabFetched, setCollabFetched] = useState(false);

  // ── Saved proposal match selector ─────────────────────────────────────────
  const [selectedProposalId, setSelectedProposalId] = useState(null);
  const [rematchGrants,      setRematchGrants]      = useState(null);  // null = use base grants
  const [rematchLoading,     setRematchLoading]     = useState(false);
  const [rematchError,       setRematchError]       = useState(null);
  const [uploadedProposalName, setUploadedProposalName] = useState("");

  // Saved drafts and builds can both be matched against current grant data.
  const matchableProposals = savedProposals.filter(
    p => p.proposal_context
  );

  const selectedSavedProposal = matchableProposals.find(p => p.id === selectedProposalId) || null;

  const handleSelectSavedProposal = async (item) => {
    if (selectedProposalId === item.id) {
      // Deselect
      setSelectedProposalId(null);
      setRematchGrants(null);
      setRematchError(null);
      setUploadedProposalName("");
      return;
    }

    setSelectedProposalId(item.id);
    setUploadedProposalName("");
    setRematchError(null);

    // If the saved item has stored matches, load them from session grants pool
    if (item.matches_id?.length > 0) {
      // Filter available grants to just the matching IDs, in order
      const storedMatches = removeDemoGrants(
        JSON.parse(sessionStorage.getItem("matches") || "[]")
      );
      const ids = item.matches_id.map(String);
      const matched = storedMatches.filter(g => ids.includes(String(g.grant_id)));
      // Sort by original match order
      matched.sort((a, b) => ids.indexOf(String(a.grant_id)) - ids.indexOf(String(b.grant_id)));

      if (matched.length === ids.length) {
        setRematchGrants(matched);
        return;
      }
    }

    // Otherwise: live re-match against the backend using the stored proposal context
    if (item.proposal_context) {
      setRematchLoading(true);
      try {
        const res = await api.post("/api/match", { proposal: item.proposal_context, top_k: 10 });
        const newMatches = removeDemoGrants(res.data.matches || []);
        setRematchGrants(newMatches);
        // Merge into session for subsequent navigation
        const existing = removeDemoGrants(
          JSON.parse(sessionStorage.getItem("matches") || "[]")
        );
        const existingIds = new Set(existing.map(g => String(g.grant_id)));
        const merged = [...existing, ...newMatches.filter(g => !existingIds.has(String(g.grant_id)))];
        sessionStorage.setItem("matches", JSON.stringify(merged));
        sessionStorage.setItem("proposal", JSON.stringify(item.proposal_context));
      } catch (e) {
        setRematchError("Could not load matches — " + (e?.response?.data?.detail || "try again."));
        setRematchGrants(null);
      } finally {
        setRematchLoading(false);
      }
    }
  };

  const handleSavedProposalChange = (event) => {
    const item = matchableProposals.find(p => p.id === event.target.value);
    if (item) {
      handleSelectSavedProposal(item);
    } else {
      setSelectedProposalId(null);
      setRematchGrants(null);
      setRematchError(null);
      setUploadedProposalName("");
    }
  };

  const handleProposalFile = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!/\.(pdf|docx)$/i.test(file.name)) {
      setRematchError("Choose a PDF or DOCX proposal.");
      return;
    }

    setRematchError(null);
    sessionStorage.removeItem("upload_draft_id");
    const uploaded = await upload(file);
    if (!uploaded) return;

    let uploadedMatches;
    try {
      uploadedMatches = removeDemoGrants(
        JSON.parse(sessionStorage.getItem("matches") || "[]")
      );
    } catch (error) {
      console.error("Could not load uploaded proposal matches.", error);
      setRematchError("The proposal was uploaded, but its grant matches could not be loaded.");
      return;
    }

    setUploadedProposalName(file.name.replace(/\.(pdf|docx)$/i, ""));
    setRematchGrants(uploadedMatches);
    setSelectedProposalId(sessionStorage.getItem("upload_draft_id") || null);
    sessionStorage.setItem("grants_searchMode", "filter");
    setSearchMode("filter");
    await refreshWorkStore();
  };

  // ── Agentic topic search — persisted in sessionStorage so results survive navigation ──
  const [searchMode, setSearchMode] = useState(function() {
    // If we have real matched grants waiting (hasRealData), always start in filter mode
    // so the proposal's matched grants are visible immediately, not stale AI results
    var saved = sessionStorage.getItem("grants_searchMode");
    return saved || "filter";
  });

  // Reset to filter mode whenever a real proposal match arrives
  // (e.g. navigating from Dashboard "View All" with a selected proposal)
  useEffect(function() {
    if (hasRealData && sessionStorage.getItem("grants_searchMode") === "ai") {
      setSearchMode("filter");
      sessionStorage.setItem("grants_searchMode", "filter");
    }
  }, [hasRealData]);
  const [aiQuery, setAiQuery] = useState(function() {
    return sessionStorage.getItem("grants_aiQuery") || "";
  });
  const [aiResults, setAiResults] = useState(function() {
    try {
      var saved = sessionStorage.getItem("grants_aiResults");
      return saved ? removeDemoGrants(JSON.parse(saved)) : null;
    } catch(e) { return null; }
  });
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError,   setAiError]   = useState(null);

  useEffect(() => {
    if (view !== "collabs" || collabFetched || !proposal) return;
    setCollabLoading(true);
    setCollabError(null);
    api.post("/api/collab/match", {
      proposal: proposal,
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

  // The final grants list to display = either rematch results or base grants
  const activeGrants = rematchGrants ?? grants;

  const filteredGrants = activeGrants
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

  const runAiSearch = function() {
    if (!aiQuery.trim()) return;
    setAiLoading(true);
    setAiError(null);
    setAiResults(null);
    api.post("/api/grants/search", { query: aiQuery, top_k: 10 })
      .then(function(res) {
        var results = removeDemoGrants(res.data.grants || []);
        setAiResults(results);
        try {
          sessionStorage.setItem("grants_aiResults", JSON.stringify(results));
          // Merge into the main matches pool so GrantDetail can look them up by ID
          var existing = removeDemoGrants(
            JSON.parse(sessionStorage.getItem("matches") || "[]")
          );
          var existingIds = new Set(existing.map(function(g) { return String(g.grant_id); }));
          var merged = existing.concat(results.filter(function(g) { return !existingIds.has(String(g.grant_id)); }));
          sessionStorage.setItem("matches", JSON.stringify(merged));
        } catch(e) {}
      })
      .catch(function(e) {
        setAiError("Search failed — " + ((e && e.response && e.response.data && e.response.data.detail) || "try again."));
      })
      .finally(function() { setAiLoading(false); });
  };

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
              ? (filteredGrants.length + " grant opportunities" + (selectedSavedProposal ? ` for "${selectedSavedProposal.title}"` : uploadedProposalName ? ` for "${uploadedProposalName}"` : hasRealData ? " matched to your proposal" : ""))
              : collabFetched
                ? (filteredCollabs.length + " NGOs with aligned mission" + (profile ? " — excluding your org" : ""))
                : "Mission-aligned NGOs for joint applications & partnerships"
          }
        />

        {isGrants && (
          <div style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border)",
            borderRadius: 12, padding: "14px 16px", marginBottom: 18,
            display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap",
          }}>
            <label htmlFor="saved-proposal-select" style={{ color: "#bbb", fontSize: 13, fontWeight: 600 }}>
              Match a proposal
            </label>
            <select
              id="saved-proposal-select"
              aria-label="Select a saved proposal"
              value={selectedProposalId || ""}
              onChange={handleSavedProposalChange}
              disabled={!profile || matchableProposals.length === 0 || uploadLoading || rematchLoading}
              style={{
                flex: "1 1 240px", minWidth: 200,
                background: "#111122", border: "1px solid var(--border)",
                color: selectedProposalId ? "#fff" : "var(--text-dim)",
                padding: "10px 12px", borderRadius: 8, fontSize: 13,
                outline: "none",
              }}
            >
              <option value="">
                {profile
                  ? matchableProposals.length ? "Choose an uploaded or saved proposal…" : "No saved proposals yet"
                  : "Sign in to select a saved proposal"}
              </option>
              {matchableProposals.map(item => (
                <option key={item.id} value={item.id}>{item.title}</option>
              ))}
            </select>
            <input
              ref={uploadInputRef}
              type="file"
              accept=".pdf,.docx"
              hidden
              onChange={handleProposalFile}
            />
            <button
              type="button"
              onClick={() => uploadInputRef.current?.click()}
              disabled={uploadLoading || rematchLoading}
              style={{
                background: "var(--accent)", border: "none", color: "#fff",
                padding: "10px 16px", borderRadius: 8, fontSize: 13,
                fontWeight: 700, cursor: uploadLoading || rematchLoading ? "wait" : "pointer",
                opacity: uploadLoading || rematchLoading ? 0.7 : 1,
                whiteSpace: "nowrap",
              }}
            >
              {uploadLoading ? "Uploading & matching…" : "Upload proposal"}
            </button>
            {selectedProposalId && (
              <button
                type="button"
                onClick={() => {
                  setSelectedProposalId(null);
                  setRematchGrants(null);
                  setRematchError(null);
                  setUploadedProposalName("");
                }}
                style={{ background: "none", border: "none", color: "#888",
                  cursor: "pointer", fontSize: 12, padding: "6px" }}
              >
                Clear
              </button>
            )}

            {/* Loading / error states */}
            {rematchLoading && (
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10, color: "#555", fontSize: 12 }}>
                <div style={{ width: 14, height: 14,
                  border: "2px solid #1e1e30", borderTop: "2px solid var(--accent)",
                  borderRadius: "50%", animation: "spin 0.8s linear infinite",
                  flexShrink: 0 }} />
                <style>{"@keyframes spin { to { transform: rotate(360deg); } }"}</style>
                Running live grant match…
              </div>
            )}
            {(rematchError || uploadError) && (
              <p role="alert" style={{ color: "var(--red)", fontSize: 12, margin: "8px 0 0", width: "100%" }}>
                ⚠ {rematchError || uploadError}
              </p>
            )}
          </div>
        )}

        <div style={{ display: "flex", gap: 12, marginBottom: 24, flexWrap: "wrap", alignItems: "center" }}>
          <ViewToggle view={view} onChange={function(v) { setView(v); setSearch(""); }} />

          {/* Search mode toggle — only for grants view */}
          {isGrants && (
            <div style={{ display: "flex", background: "var(--bg-card)",
              border: "1px solid var(--border)", borderRadius: 10, padding: 3, flexShrink: 0 }}>
              {[["filter","Filter"],["ai","Topic search"]].map(function([mode, label]) {
                return (
                  <button key={mode} onClick={function() { setSearchMode(mode); sessionStorage.setItem("grants_searchMode", mode); setAiResults(null); sessionStorage.removeItem("grants_aiResults"); setAiError(null); }} style={{
                    background: searchMode === mode
                      ? "var(--accent-dim)"
                      : "none",
                    border: "none",
                    color: searchMode === mode ? "#fff" : "var(--text-dim)",
                    padding: "7px 14px", borderRadius: 7, fontSize: 12,
                    fontWeight: searchMode === mode ? 700 : 400, cursor: "pointer",
                    transition: "all 0.15s",
                  }}>{label}</button>
                );
              })}
            </div>
          )}

          {/* Regular filter search */}
          {(!isGrants || searchMode === "filter") && (
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
          )}

          {/* Topic search */}
          {isGrants && searchMode === "ai" && (
            <div style={{ display: "flex", gap: 8, flex: 1, minWidth: 260 }}>
              <div style={{ position: "relative", flex: 1 }}>
                <span style={{ position: "absolute", left: 14, top: "50%",
                  transform: "translateY(-50%)", color: "var(--accent)", fontSize: 14 }}>⌕</span>
                <input
                  value={aiQuery}
                  onChange={function(e) { setAiQuery(e.target.value); sessionStorage.setItem("grants_aiQuery", e.target.value); }}
                  onKeyDown={function(e) { if (e.key === "Enter") runAiSearch(); }}
                  placeholder="Describe a topic… e.g. 'affordable housing LA' or 'youth mental health'"
                  style={{
                    width: "100%", background: "var(--bg-card)",
                    border: "1px solid var(--border)",
                    borderRadius: 10, padding: "10px 14px 10px 38px",
                    color: "#fff", fontSize: 14, outline: "none", boxSizing: "border-box",
                  }}
                />
              </div>
              <button
                onClick={runAiSearch}
                disabled={aiLoading || !aiQuery.trim()}
                style={{
                  background: "var(--accent-dim)", border: "none", color: "#fff",
                  padding: "10px 20px", borderRadius: 10, fontSize: 13,
                  fontWeight: 700, cursor: aiLoading ? "not-allowed" : "pointer",
                  opacity: (!aiQuery.trim() || aiLoading) ? 0.6 : 1,
                  flexShrink: 0, whiteSpace: "nowrap",
                  transition: "opacity 0.15s",
                }}
              >
                {aiLoading ? "Searching…" : "Search →"}
              </button>
            </div>
          )}

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

            {/* Topic search results */}
            {searchMode === "ai" && (
              <>
                {aiError && (
                  <div style={{ background: "#2d0f0f", border: "1px solid #7f1d1d",
                    borderRadius: 10, padding: "14px 18px", color: "#ef4444", fontSize: 13 }}>
                    ⚠ {aiError}
                  </div>
                )}
                {aiLoading && (
                  <div style={{ textAlign: "center", padding: "50px 0" }}>
                    <div style={{ width: 32, height: 32, margin: "0 auto 14px",
                      border: "3px solid var(--border)", borderTop: "3px solid var(--accent)",
                      borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
                    <style>{"@keyframes spin { to { transform: rotate(360deg); } }"}</style>
                    <p style={{ color: "#9da89e", fontSize: 13 }}>Searching grant opportunities…</p>
                  </div>
                )}
                {!aiLoading && aiResults !== null && (
                  <>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
                      <span style={{ color: "var(--accent)", fontSize: 12, fontWeight: 700 }}>
                        Topic search
                      </span>
                      <span style={{ color: "#444", fontSize: 12 }}>
                        {aiResults.length} results for "{aiQuery}"
                      </span>
                      <button onClick={function() { setAiResults(null); setAiQuery(""); sessionStorage.removeItem("grants_aiResults"); sessionStorage.removeItem("grants_aiQuery"); sessionStorage.setItem("grants_searchMode", "filter"); setSearchMode("filter"); }}
                        style={{ marginLeft: "auto", background: "none", border: "none",
                          color: "#444", fontSize: 11, cursor: "pointer" }}>
                        Clear ✕
                      </button>
                    </div>
                    {aiResults.length > 0
                      ? aiResults.map(function(grant) { return <GrantCard key={grant.grant_id} grant={grant} />; })
                      : <EmptyState icon="⬡" title="No results found" subtitle={"Try a different topic or be more specific"} />
                    }
                  </>
                )}
                {!aiLoading && aiResults === null && !aiError && (
                  <EmptyState icon="⌕" title="Search by topic"
                    subtitle="Describe your program or community needs to find related opportunities in the grants database." />
                )}
              </>
            )}

            {/* Regular filter results */}
            {searchMode === "filter" && (
              <>
                {grantsLoading
                  ? <EmptyState icon="◎" title="Loading grant matches" subtitle="Checking your saved live grant matches" />
                  : filteredGrants.length > 0
                  ? filteredGrants.map(function(grant) { return <GrantCard key={grant.grant_id} grant={grant} />; })
                  : activeGrants.length === 0
                    ? <EmptyState icon="◎" title="No grant matches yet" subtitle="Upload a proposal to find relevant opportunities, or use topic search to explore the grants database." />
                    : <EmptyState icon="◎" title="No grants match your filters" subtitle="Try adjusting your search or fit level filter" />
                }
              </>
            )}
          </div>
        )}

        {isCollabs && (
          <div>
            {collabLoading && (
              <div style={{ textAlign: "center", padding: "60px 0" }}>
                <div style={{
                  width: 36, height: 36, margin: "0 auto 16px",
                  border: "3px solid var(--border)", borderTop: "3px solid var(--accent)",
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