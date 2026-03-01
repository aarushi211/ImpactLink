import { useState } from "react";

import { useNavigate } from "react-router-dom";
import { Nav, StatCard, GrantCard, SectionHeader } from "../components";
import { useAuth } from "../context/AuthContext";
import useGrants from "../hooks/useGrants";
import useWorkStore from "../hooks/useWorkStore";

const TYPE_META = {
  draft:   { icon: "✍", label: "Draft",          color: "var(--accent)" },
  build:   { icon: "✦", label: "Built Proposal",  color: "var(--yellow)" },
  budget:  { icon: "💰", label: "Budget",          color: "var(--green)"  },
};

function itemSubtitle(item, meta) {
  const hasSection = item.section_order?.length > 0;
  const wordCount  = item.word_count;
  const budget     = item.total_requested;
  if (item._type === "budget")
    return budget ? `$${Number(budget).toLocaleString()}` : meta.label;
  if (!hasSection)
    return item.matches_id?.length
      ? `${item.matches_id.length} matches · ready to draft`
      : "Uploaded proposal";
  return wordCount ? `${wordCount.toLocaleString()} words` : meta.label;
}

function WorkItem({ item, active, onSelect, onOpen, onDelete }) {
  const meta     = TYPE_META[item._type || item.type] || TYPE_META.draft;
  const date     = new Date(item.updated_at).toLocaleDateString("en-US",
    { month: "short", day: "numeric" });
  const subtitle    = itemSubtitle(item, meta);
  const isBudget    = (item._type || item.type) === "budget";
  const borderColor = active ? meta.color : "var(--border)";

  return (
    <div
      onClick={onSelect}
      style={{
        background: active ? `${meta.color}11` : "var(--bg-card)",
        border: `1px solid ${borderColor}`,
        borderRadius: 10, padding: "11px 14px",
        display: "flex", alignItems: "center", gap: 10,
        transition: "all 0.15s",
        cursor: isBudget ? "default" : "pointer",
      }}
      onMouseEnter={e => { if (!active) e.currentTarget.style.borderColor = meta.color; }}
      onMouseLeave={e => { if (!active) e.currentTarget.style.borderColor = "var(--border)"; }}
    >
      {/* Active indicator */}
      <div style={{
        width: 32, height: 32, borderRadius: 8, flexShrink: 0,
        background: active ? `${meta.color}22` : "#1a1a2e",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 14, color: meta.color,
      }}>
        {active ? "◉" : meta.icon}
      </div>

      {/* Text */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <p style={{ margin: 0, fontWeight: 600,
          color: active ? "#fff" : "#e0e0f0",
          fontSize: 13, overflow: "hidden", textOverflow: "ellipsis",
          whiteSpace: "nowrap" }}>
          {item.title}
        </p>
        <p style={{ margin: 0, color: "#444", fontSize: 10 }}>
          <span style={{ color: meta.color, fontWeight: 600 }}>{subtitle}</span>
          {item.budget_id ? " · 💰" : ""}
          {" · "}{date}
        </p>
      </div>

      {/* Edit button */}
      <button
        onClick={e => { e.stopPropagation(); onOpen(); }}
        title="Open / Edit"
        style={{
          background: "none", border: "1px solid #2a2a3e",
          color: "#555", cursor: "pointer",
          fontSize: 10, padding: "3px 8px", borderRadius: 5,
          fontWeight: 600, transition: "all 0.15s", flexShrink: 0,
        }}
        onMouseEnter={e => { e.target.style.borderColor = meta.color; e.target.style.color = meta.color; }}
        onMouseLeave={e => { e.target.style.borderColor = "#2a2a3e"; e.target.style.color = "#555"; }}
      >
        Edit
      </button>

      {/* Delete button */}
      <button
        onClick={e => { e.stopPropagation(); onDelete(); }}
        title="Delete"
        style={{
          background: "none", border: "none", color: "#2a2a3e",
          cursor: "pointer", fontSize: 13, padding: "4px 5px", borderRadius: 4,
          transition: "color 0.15s", flexShrink: 0,
        }}
        onMouseEnter={e => e.target.style.color = "var(--red)"}
        onMouseLeave={e => e.target.style.color = "#2a2a3e"}
      >
        ✕
      </button>
    </div>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const { profile } = useAuth();
  const { grants } = useGrants();
  const { drafts, builds, budgets, loading, deleteDraft, deleteBuild, deleteBudget } = useWorkStore();
  const allItems = [
    ...drafts.map(d  => ({ ...d, _type: "draft"  })),
    ...builds.map(b  => ({ ...b, _type: "build"  })),
    ...budgets.map(b => ({ ...b, _type: "budget" })),
  ].sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at));

  const p = profile || {};
  const firstName = (p.org_name || "there").split(" ")[0];
  const recentItems = allItems.slice(0, 8);

  // Active proposal selected in Saved Work — drives grant panel
  const [activeProposalId, setActiveProposalId] = useState(null);
  const activeProposal = allItems.find(i => i.id === activeProposalId) || null;

  // Grants to show: if a proposal is selected and has matches_id, filter + reorder
  // Otherwise fall back to the full grants list from sessionStorage
  const visibleGrants = (() => {
    if (!activeProposal || !activeProposal.matches_id?.length) return grants;
    // Reorder grants to match the saved matches_id order, then append any extras
    const ids = activeProposal.matches_id.map(String);
    const inSet = grants.filter(g => ids.includes(String(g.grant_id)));
    const rest  = grants.filter(g => !ids.includes(String(g.grant_id)));
    // Sort inSet by original matches_id order
    inSet.sort((a, b) => ids.indexOf(String(a.grant_id)) - ids.indexOf(String(b.grant_id)));
    return [...inSet, ...rest];
  })();

  // Derive stats from saved items + profile
  const totalDrafts  = drafts.length + builds.length;
  const totalBudgets = budgets.length;
  const matchSets    = 0; // matches stored in sessionStorage, not work store

  // Clicking a proposal card selects it (updates grant panel) without navigating
  // The "Edit" button on the card navigates to the editor
  const selectProposal = (item) => {
    const type = item._type || item.type;
    if (type === "budget") return; // budgets don't have grant matches
    setActiveProposalId(prev => prev === item.id ? null : item.id); // toggle
    // Also set sessionStorage so Draft/Budget pages pick it up
    sessionStorage.setItem("upload_draft_id", item.id);
    if (item.proposal_context) {
      sessionStorage.setItem("proposal", JSON.stringify(item.proposal_context));
    }
  };

  // Edit button — navigate to the right editor
  const openItem = (item) => {
    const type = item._type || item.type;
    if (type === "build") {
      sessionStorage.setItem("upload_draft_id", item.id);
      navigate(`/build?load=${item.id}`);
    } else if (type === "draft") {
      sessionStorage.setItem("upload_draft_id", item.id);
      if (item.section_order?.length > 0) {
        navigate(`/draft?load=${item.id}${item.grant_id ? `&grant=${item.grant_id}` : ""}`);
      } else {
        navigate(`/draft${item.grant_id ? `?grant=${item.grant_id}` : ""}`);
      }
    } else if (type === "budget") {
      navigate(`/budget?load=${item.id}`);
    }
  };

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)" }}>
      <Nav />
      <div style={{ maxWidth: 1280, margin: "0 auto", padding: "40px" }}>

        <SectionHeader
          label="NGO Dashboard"
          title={`Welcome back, ${firstName} 👋`}
          subtitle={p.mission || "Complete your profile to get better grant matches."}
        />

        {/* Stats */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)",
          gap: 16, marginBottom: 36 }}>
          <StatCard label="Funding Secured"
            value={`$${((p.funding_secured||0)/1000).toFixed(0)}K`}
            sub="lifetime" accent="var(--accent)" />
          <StatCard label="Proposals Written"
            value={totalDrafts}
            sub={`${builds.length} built · ${drafts.length} drafted`}
            accent="var(--yellow)" />
          <StatCard label="Budgets Built"
            value={totalBudgets} sub="saved budgets"
            accent="var(--green)" />
          <StatCard label="Match Sets"
            value={matchSets} sub="uploaded proposals"
            accent="var(--pink)" />
        </div>

        {/* Main grid */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 360px", gap: 24 }}>

          {/* Left */}
          <div>
            {/* Top matched grants */}
            <div style={{ display: "flex", alignItems: "center",
              justifyContent: "space-between", marginBottom: activeProposal ? 8 : 16 }}>
              <div>
                <h2 style={{ fontSize: 18, fontWeight: 700, color: "#fff", margin: 0 }}>
                  Top Matched Grants
                </h2>
                {activeProposal && (
                  <p style={{ color: "var(--accent)", fontSize: 11, fontWeight: 600,
                    margin: "3px 0 0", display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ background: "var(--accent)", borderRadius: "50%",
                      width: 6, height: 6, display: "inline-block", flexShrink: 0 }} />
                    Showing matches for: {activeProposal.title?.length > 36
                      ? activeProposal.title.slice(0, 36) + "…"
                      : activeProposal.title}
                    <button
                      onClick={() => setActiveProposalId(null)}
                      style={{ background: "none", border: "none", color: "#444",
                        cursor: "pointer", fontSize: 11, padding: 0, marginLeft: 2 }}
                    >✕</button>
                  </p>
                )}
              </div>
              <button
                onClick={() => navigate("/grants")}
                style={{ background: "transparent", border: "1px solid var(--border)",
                  color: "var(--accent)", padding: "8px 18px", borderRadius: 8,
                  fontSize: 13, fontWeight: 600, cursor: "pointer", flexShrink: 0 }}
              >
                View All →
              </button>
            </div>

            {visibleGrants.length > 0 ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {visibleGrants.slice(0, 3).map(g => (
                  <GrantCard key={g.grant_id} grant={g} compact />
                ))}
              </div>
            ) : (
              <div style={{ background: "var(--bg-card)",
                border: "1px dashed var(--border)", borderRadius: 12,
                padding: "32px 24px", textAlign: "center" }}>
                <p style={{ fontSize: 28, margin: "0 0 10px" }}>📄</p>
                <p style={{ color: "#fff", fontWeight: 700, fontSize: 15,
                  margin: "0 0 6px" }}>
                  No grant matches yet
                </p>
                <p style={{ color: "#555", fontSize: 13, margin: "0 0 16px" }}>
                  Upload your proposal to get AI-matched grants
                </p>
                <button onClick={() => navigate("/upload")}
                  style={{ background: "var(--accent)", border: "none",
                    color: "#fff", padding: "10px 22px", borderRadius: 8,
                    fontSize: 13, fontWeight: 700, cursor: "pointer" }}>
                  Upload Proposal →
                </button>
              </div>
            )}

            {/* Quick Actions */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr",
              gap: 12, marginTop: 20 }}>
              {[
                { icon: "✦", label: "Build a Proposal",    sub: "Start from scratch with AI guidance",    path: "/build"   },
                { icon: "✍", label: "Draft Assistant",     sub: "AI agents write for a specific funder",  path: "/draft"   },
                { icon: "💰", label: "Budget Builder",      sub: "Generate a localized line-item budget",  path: "/budget"  },
                { icon: "⬆", label: "Upload Proposal",     sub: "Re-run AI matching with new docs",       path: "/upload"  },
              ].map(a => (
                <div key={a.label} onClick={() => navigate(a.path)}
                  style={{ background: "var(--bg-card)", border: "1px solid var(--border)",
                    borderRadius: 14, padding: "18px", cursor: "pointer",
                    transition: "border-color 0.2s" }}
                  onMouseEnter={e => e.currentTarget.style.borderColor = "var(--accent)"}
                  onMouseLeave={e => e.currentTarget.style.borderColor = "var(--border)"}
                >
                  <div style={{ fontSize: 20, marginBottom: 8 }}>{a.icon}</div>
                  <p style={{ fontWeight: 700, color: "#fff", fontSize: 14,
                    margin: "0 0 3px" }}>{a.label}</p>
                  <p style={{ color: "#444", fontSize: 12, margin: 0 }}>{a.sub}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Right */}
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

            {/* Org card */}
            <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)",
              borderRadius: 16, padding: 22 }}>
              <div style={{ display: "flex", alignItems: "center",
                gap: 14, marginBottom: 14 }}>
                <div style={{ width: 46, height: 46, borderRadius: 12, flexShrink: 0,
                  background: "linear-gradient(135deg, var(--accent), var(--accent-dim))",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontWeight: 800, fontSize: 20, color: "#fff" }}>
                  {(p.org_name || "?")[0].toUpperCase()}
                </div>
                <div>
                  <p style={{ fontWeight: 700, color: "#fff", margin: 0, fontSize: 14 }}>
                    {p.org_name || "Your Organization"}
                  </p>
                  <p style={{ color: "var(--text-muted)", fontSize: 11, margin: 0 }}>
                    📍 {p.location || "Location not set"}
                  </p>
                </div>
              </div>

              {p.cause_area && (
                <div style={{ borderTop: "1px solid #1a1a2e", paddingTop: 12,
                  marginBottom: 12 }}>
                  <p style={{ color: "#444", fontSize: 10, fontWeight: 600,
                    textTransform: "uppercase", letterSpacing: "0.08em",
                    margin: "0 0 3px" }}>Cause Area</p>
                  <p style={{ color: "#bbb", fontSize: 13, margin: 0 }}>
                    {p.cause_area}
                  </p>
                </div>
              )}

              {(p.sdgs || []).length > 0 && (
                <div style={{ marginBottom: 14 }}>
                  <p style={{ color: "#444", fontSize: 10, fontWeight: 600,
                    textTransform: "uppercase", letterSpacing: "0.08em",
                    margin: "0 0 7px" }}>SDG Alignment</p>
                  <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                    {(p.sdgs || []).map(sdg => (
                      <span key={sdg} style={{ background: "#1a1a2e",
                        color: "var(--accent)", border: "1px solid #2e2e4e",
                        borderRadius: 5, padding: "2px 8px",
                        fontSize: 10, fontWeight: 600 }}>
                        {sdg.split(":")[0]}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              <button
                onClick={() => navigate("/profile")}
                style={{ width: "100%", background: "transparent",
                  border: "1px solid var(--border)", color: "var(--accent)",
                  padding: "9px 0", borderRadius: 8, fontSize: 12,
                  fontWeight: 600, cursor: "pointer" }}
              >
                Edit Profile
              </button>
            </div>

            {/* Saved work */}
            <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)",
              borderRadius: 16, padding: 22, flex: 1 }}>
              <div style={{ display: "flex", alignItems: "center",
                justifyContent: "space-between", marginBottom: 14 }}>
                <h3 style={{ fontWeight: 700, color: "#fff", fontSize: 14, margin: 0 }}>
                  Saved Work
                </h3>
                {allItems.length > 0 && (
                  <span style={{ color: "#444", fontSize: 11 }}>
                    {allItems.length} item{allItems.length !== 1 ? "s" : ""}
                  </span>
                )}
              </div>

              {loading ? (
                <div style={{ textAlign: "center", padding: "24px 0" }}>
                  <div style={{ width: 24, height: 24, margin: "0 auto",
                    border: "2px solid #1e1e30",
                    borderTop: "2px solid var(--accent)",
                    borderRadius: "50%",
                    animation: "spin 0.8s linear infinite" }} />
                  <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
                </div>
              ) : recentItems.length === 0 ? (
                <div style={{ textAlign: "center", padding: "24px 0" }}>
                  <p style={{ color: "#2a2a3e", fontSize: 12, margin: 0,
                    lineHeight: 1.7 }}>
                    Your drafts, budgets, and proposals will appear here automatically when you save them.
                  </p>
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {recentItems.map(item => (
                    <WorkItem
                      key={item.id}
                      item={item}
                      active={activeProposalId === item.id}
                      onSelect={() => selectProposal(item)}
                      onOpen={() => openItem(item)}
                      onDelete={() => {
                        if (item._type === "draft")  deleteDraft(item.id);
                        if (item._type === "build")  deleteBuild(item.id);
                        if (item._type === "budget") deleteBudget(item.id);
                      }}
                    />
                  ))}
                  {allItems.length > 8 && (
                    <p style={{ color: "#444", fontSize: 11, textAlign: "center",
                      margin: "4px 0 0" }}>
                      +{allItems.length - 8} more items
                    </p>
                  )}
                </div>
              )}
            </div>

          </div>
        </div>
      </div>
    </div>
  );
}