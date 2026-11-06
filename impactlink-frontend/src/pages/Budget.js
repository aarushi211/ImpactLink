import { useState, useRef, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Nav } from "../components";
import useGrants from "../hooks/useGrants";
import useBudget from "../hooks/useBudget";
import useWorkStore from "../hooks/useWorkStore";
import BudgetInputs, { emptyCostInputs } from "../components/BudgetInputs";
import AiPrivacyNotice from "../components/AiPrivacyNotice";

// ── helpers ──────────────────────────────────────────────────────────────────

const fmt = (n) =>
  n != null ? "$" + Number(n).toLocaleString("en-US") : "—";

const CATEGORY_COLORS = {
  Personnel:      "#7c6fef",
  Equipment:      "#4ade80",
  Travel:         "#facc15",
  Marketing:      "#f472b6",
  "Indirect Costs": "#fb923c",
  Administration: "#38bdf8",
  Training:       "#a78bfa",
  Supplies:       "#34d399",
};
const catColor = (name) => {
  for (const [k, v] of Object.entries(CATEGORY_COLORS)) {
    if (name.toLowerCase().includes(k.toLowerCase())) return v;
  }
  return "#7c6fef";
};

// Bar width as % of total
const barPct = (amount, total) =>
  total > 0 ? Math.max(2, Math.round((amount / total) * 100)) : 0;

// ── sub-components ────────────────────────────────────────────────────────────

function BudgetTable({ items, total }) {
  return (
    <div style={{ width: "100%" }}>
      {/* header */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "1fr 2fr 120px 100px",
        padding: "7px 16px",
        borderBottom: "1px solid #1e1e30",
        marginBottom: 4,
      }}>
        {["Category", "Justification", "Amount", "Share"].map(h => (
          <span key={h} style={{ fontSize: 10, fontWeight: 800, color: "#333",
            textTransform: "uppercase", letterSpacing: "0.08em" }}>
            {h}
          </span>
        ))}
      </div>

      {/* rows */}
      {items.map((item, i) => {
        const color = catColor(item.category);
        const pct   = barPct(item.amount, total);
        return (
          <div
            key={i}
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 2fr 120px 100px",
              padding: "11px 16px",
              borderRadius: 8,
              marginBottom: 2,
              background: i % 2 === 0 ? "#111120" : "transparent",
              transition: "background 0.1s",
            }}
            onMouseEnter={e => e.currentTarget.style.background = "#1a1a2e"}
            onMouseLeave={e => e.currentTarget.style.background = i % 2 === 0 ? "#111120" : "transparent"}
          >
            {/* category pill */}
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{
                width: 8, height: 8, borderRadius: "50%",
                background: color, flexShrink: 0,
              }} />
              <span style={{ fontSize: 12, fontWeight: 700, color: "#e0e0f0" }}>
                {item.category}
              </span>
            </div>

            {/* description */}
            <span style={{ fontSize: 12, color: "#666", lineHeight: 1.5, paddingRight: 16 }}>
              {item.description}
            </span>

            {/* amount */}
            <span style={{ fontSize: 13, fontWeight: 700, color: color }}>
              {fmt(item.amount)}
            </span>

            {/* bar + % */}
            <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
              <div style={{
                flex: 1, height: 6, background: "#1e1e30", borderRadius: 3, overflow: "hidden",
              }}>
                <div style={{
                  width: `${pct}%`, height: "100%",
                  background: color, borderRadius: 3,
                  transition: "width 0.6s cubic-bezier(0.4,0,0.2,1)",
                }} />
              </div>
              <span style={{ fontSize: 10, color: "#444", minWidth: 28, textAlign: "right" }}>
                {pct}%
              </span>
            </div>
          </div>
        );
      })}

      {/* total row */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "1fr 2fr 120px 100px",
        padding: "12px 16px",
        borderTop: "1px solid #1e1e30",
        marginTop: 4,
      }}>
        <span style={{ fontSize: 12, fontWeight: 800, color: "#e0e0f0", gridColumn: "1/3" }}>
          Total Requested
        </span>
        <span style={{ fontSize: 14, fontWeight: 900, color: "var(--accent)" }}>
          {fmt(total)}
        </span>
      </div>
    </div>
  );
}


function ChatMessage({ msg }) {
  const isUser = msg.role === "user";
  return (
    <div style={{
      display: "flex",
      justifyContent: isUser ? "flex-end" : "flex-start",
      marginBottom: 12,
    }}>
      {!isUser && (
        <div style={{
          width: 28, height: 28, borderRadius: "50%", flexShrink: 0,
          background: "var(--accent-dim)",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 11, fontWeight: 800, color: "#fff", marginRight: 8, alignSelf: "flex-end",
        }}>✦</div>
      )}
      <div style={{
        maxWidth: "82%",
        background: isUser ? "var(--accent)" : "#111120",
        border: isUser ? "none" : "1px solid #1e1e30",
        borderRadius: isUser ? "16px 16px 4px 16px" : "4px 16px 16px 16px",
        padding: "10px 14px",
      }}>
        <p style={{ margin: 0, fontSize: 13, color: isUser ? "#fff" : "#ccc", lineHeight: 1.6 }}>
          {msg.content}
        </p>
        {msg.budgetUpdated && (
          <p style={{ margin: "6px 0 0", fontSize: 11, color: "#4ade80", fontWeight: 700 }}>
            ✓ Budget updated
          </p>
        )}
      </div>
    </div>
  );
}


// ── main page ─────────────────────────────────────────────────────────────────

export default function Budget() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const grantParam = searchParams.get("grant");
  const { grants, proposal } = useGrants();
  const { budget, loading, error, generate, refine, reset } = useBudget();
  const { saveBudget, updateBudget, budgets, proposals } = useWorkStore();
  const savedBudgetId = useRef(null);
  const restoredBudgetId = useRef(null);
  const pendingBudgetSave = useRef(Promise.resolve());
  const [saveError, setSaveError] = useState(null);
  const [preloadedBudget, setPreloadedBudget] = useState(null);
  const [costInputs, setCostInputs] = useState(emptyCostInputs);
  useEffect(() => {
    const inputs = budget?.cost_inputs || preloadedBudget?.cost_inputs;
    if (inputs) setCostInputs(inputs);
  }, [budget, preloadedBudget]);

  // saved proposal selector
  const [selectedProposalId, setSelectedProposalId] = useState(
    sessionStorage.getItem("upload_draft_id") || ""
  );
  const activeProposal    = proposals.find(p => p.id === selectedProposalId);
  const resolvedProposal  = activeProposal?.proposal_context
    || preloadedBudget?.proposal_context
    || proposal   // from useGrants (sessionStorage)
    || null;

  // grant + budget amount selection
  const [selectedGrantId, setSelectedGrantId] = useState(grantParam || "");
  const [maxBudget,       setMaxBudget]       = useState("");

  // chat state
  const [messages,  setMessages]  = useState([]);
  const [input,     setInput]     = useState("");
  const [chatReady, setChatReady] = useState(false);

  const chatEndRef  = useRef(null);
  const inputRef    = useRef(null);

  const selectedGrant = grants.find(g => String(g.grant_id) === String(selectedGrantId));

  // When user picks a saved proposal, auto-load its linked budget if one exists
  useEffect(() => {
    if (searchParams.get("load") || budget || !activeProposal?.budget_id) return;
    const linked = budgets.find(b => b.id === activeProposal.budget_id);
    if (linked && savedBudgetId.current !== linked.id) {
      savedBudgetId.current = linked.id;
      setPreloadedBudget(linked);
      setMaxBudget(String(linked.max_budget || linked.total_requested || ""));
      setChatReady(true);
      setMessages([{ role: "assistant", content: "Restored this proposal's saved budget. You can request adjustments below." }]);
    }
  }, [activeProposal?.budget_id, budgets, searchParams, budget]);

  // Sync selectedGrantId with grantParam if it changes
  useEffect(() => {
    if (grantParam) {
      setSelectedGrantId(grantParam);
    }
  }, [grantParam, grants]); // Also depend on grants to ensure we can find it

  // Load saved budget if ?load=<id>
  const loadBudgetId = searchParams.get("load");
  useEffect(() => {
    if (!loadBudgetId || !budgets.length || restoredBudgetId.current === loadBudgetId) return;
    const saved = budgets.find(b => b.id === loadBudgetId);
    if (!saved) return;
    restoredBudgetId.current = saved.id;
    savedBudgetId.current = saved.id;
    setSelectedProposalId(saved.proposal_id || "");
    setSelectedGrantId(saved.grant_id || "");
    setMaxBudget(String(saved.max_budget || saved.total_requested || ""));
    setChatReady(true);
    setMessages([{ role: "assistant", content: "Restored your saved budget. You can review it or request adjustments below." }]);
    reset();
    setPreloadedBudget(saved);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadBudgetId, budgets]);

  // Reload a saved budget when navigated to from Dashboard


  // Only an explicit award ceiling can pre-fill the maximum request.
  useEffect(() => {
    // Only pre-fill if we have a grant selected AND it's in our grants list
    if (loadBudgetId) return;
    const grant = grants.find(g => String(g.grant_id) === String(selectedGrantId));
    
    if (grant) {
      const ceiling = grant.award_ceiling;
      
      let amount = 0;
      if (ceiling && Number(ceiling) > 0) {
        amount = Number(ceiling);
      }

      setMaxBudget(amount > 0 ? String(amount) : "");
    }
  }, [selectedGrantId, grants, loadBudgetId]);

  // scroll chat to bottom on new messages
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // ── handlers ───────────────────────────────────────────

  const handleGenerate = async () => {
    if (!maxBudget) return;
    await pendingBudgetSave.current.catch(() => {});
    savedBudgetId.current = null;
    setPreloadedBudget(null);
    reset();
    setMessages([]);
    setChatReady(false);
    await generate(resolvedProposal || {}, Number(maxBudget), costInputs);
  };

  // Persist each generated or refined budget, retaining the same saved ID.
  useEffect(() => {
    if (!budget) return;
    const payload = {
      ...budget,
      title: selectedGrant?.title || preloadedBudget?.title || activeProposal?.title || "Budget",
      grant_title: selectedGrant?.title || preloadedBudget?.grant_title || "", grant_id: selectedGrantId || "",
      max_budget: budget.max_budget || Number(maxBudget) || 0, proposal_id: activeProposal?.id || preloadedBudget?.proposal_id || null,
      proposal_type: activeProposal?._type || preloadedBudget?.proposal_type || null,
      proposal_context: budget.cost_inputs ? { ...(resolvedProposal || {}), budget_inputs: budget.cost_inputs } : resolvedProposal,
      items: budget.items, total_requested: budget.total_requested,
      locality_explanation: budget.locality_explanation,
    };
    pendingBudgetSave.current = pendingBudgetSave.current.catch(() => {}).then(async () => {
      const saved = savedBudgetId.current
        ? await updateBudget(savedBudgetId.current, payload)
        : await saveBudget(payload);
      if (!saved) throw new Error("Could not save the budget. Please try again.");
      savedBudgetId.current = saved.id;
      setSaveError(null);
    }).catch(error => setSaveError(error.message));
    if (!chatReady) {
      setChatReady(true);
      setMessages([{ role: "assistant", content: `Your ${budget.items.length}-line budget totals ${fmt(budget.total_requested)}. ${budget.locality_explanation || ""} Ask me to adjust any category.` }]);
    }
    // Save only when the generated budget changes, not on work-store refresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [budget]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || !displayBudget || loading) return;
    setInput("");

    const userMsg = { role: "user", content: text };
    setMessages(prev => [...prev, userMsg]);

    await refine(displayBudget, text);
  };

  // when refine returns a new budget, add assistant ack
  const displayBudget = budget || preloadedBudget;
  const prevBudgetRef = useRef(null);
  useEffect(() => {
    if (displayBudget && prevBudgetRef.current && displayBudget !== prevBudgetRef.current) {
      setMessages(prev => [...prev, {
        role: "assistant",
        content: displayBudget.chat_response || displayBudget.locality_explanation,
        budgetUpdated: !displayBudget.clarification,
      }]);
    }
    prevBudgetRef.current = displayBudget;
  }, [budget, displayBudget]);

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // ── derived ────────────────────────────────────────────

  const canGenerate = (costInputs.staff.length > 0 || costInputs.direct_costs.length > 0) && !!maxBudget && Number(maxBudget) > 0;
  const isGenerating = loading === "generating";
  const isRefining   = loading === "refining";

  // ── render ─────────────────────────────────────────────

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", display: "flex", flexDirection: "column" }}>
      <Nav />
      {saveError && <p role="alert" style={{ color: "#ef4444", margin: 16 }}>{saveError}</p>}

      {/* ── App Bar ─────────────────────────── */}
      <div style={{
        background: "#13131f", borderBottom: "1px solid #1e1e30",
        padding: "0 24px", height: 48,
        display: "flex", alignItems: "center", gap: 12,
        position: "sticky", top: 64, zIndex: 90,
      }}>
        <button
          onClick={() => navigate(-1)}
          style={{ background: "none", border: "none", color: "#555", fontSize: 13, cursor: "pointer", padding: 0 }}
        >←</button>
        <span style={{ color: "#fff", fontWeight: 700, fontSize: 13 }}>Budget Builder</span>
        {displayBudget && (
          <span style={{
            background: "#0d2e1a", color: "#4ade80",
            border: "1px solid #166534",
            borderRadius: 5, padding: "2px 9px", fontSize: 10, fontWeight: 700,
          }}>
            {fmt(displayBudget.total_requested)}
          </span>
        )}
      </div>

      {/* ── Body ────────────────────────────── */}
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>

        {/* ── Left: Config + Table ─────────── */}
        <div style={{
          width: "50%", flexShrink: 0, overflowY: "auto",
          padding: "32px 40px 80px",
          display: "flex", flexDirection: "column", gap: 24,
        }}>

          {/* Config card */}
          <div style={{
            background: "var(--bg-card)", border: "1px solid var(--border)",
            borderRadius: 12, padding: "20px 24px",
          }}>
            <p style={{ color: "#333", fontSize: 10, fontWeight: 800,
              textTransform: "uppercase", letterSpacing: "0.1em", margin: "0 0 14px" }}>
              Budget Setup
            </p>

            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              {/* Saved Proposal picker */}
              <div style={{ flex: 1, minWidth: 200 }}>
                <label style={{ display: "block", color: "#555", fontSize: 11,
                  fontWeight: 600, marginBottom: 6 }}>
                  Saved Proposal
                </label>
                <select
                  value={selectedProposalId}
                  onChange={e => {
                    reset();
                    setPreloadedBudget(null);
                    savedBudgetId.current = null;
                    setCostInputs(emptyCostInputs());
                    setSelectedProposalId(e.target.value);
                    sessionStorage.setItem("upload_draft_id", e.target.value);
                  }}
                  style={{
                    width: "100%", background: "#1a1a28",
                    border: "1px solid var(--border)",
                    color: selectedProposalId ? "#ddd" : "#444",
                    padding: "9px 10px", borderRadius: 8, fontSize: 12,
                    cursor: "pointer", outline: "none",
                  }}
                >
                  <option value="">Use uploaded proposal…</option>
                  {proposals.map(p => (
                    <option key={p.id} value={p.id}>
                      {p._type === "build" ? "✦ " : "✍ "}
                      {p.title.length > 44 ? p.title.slice(0, 44) + "…" : p.title}
                      {p.budget_id ? " · 💰" : ""}
                    </option>
                  ))}
                </select>
              </div>

              {/* Grant picker */}
              <div style={{ flex: 1, minWidth: 200 }}>
                <label style={{ display: "block", color: "#555", fontSize: 11,
                  fontWeight: 600, marginBottom: 6 }}>
                  Target Grant (optional)
                </label>
                <select
                  value={selectedGrantId}
                  onChange={e => setSelectedGrantId(e.target.value)}
                  style={{
                    width: "100%", background: "#1a1a28",
                    border: "1px solid var(--border)", color: selectedGrantId ? "#ddd" : "#444",
                    padding: "9px 10px", borderRadius: 8, fontSize: 12,
                    cursor: "pointer", outline: "none",
                  }}
                >
                  <option value="">Select a grant…</option>
                  {grants.map(g => (
                    <option key={g.grant_id} value={g.grant_id}>
                      {g.title.length > 48 ? g.title.slice(0, 48) + "…" : g.title}
                    </option>
                  ))}
                </select>
              </div>

              {/* Budget amount */}
              <div style={{ minWidth: 160 }}>
                <label style={{ display: "block", color: "#555", fontSize: 11,
                  fontWeight: 600, marginBottom: 6 }}>
                  Grant Maximum ($)
                </label>
                <input
                  type="number"
                  value={maxBudget}
                  onChange={e => setMaxBudget(e.target.value)}
                  placeholder="e.g. 250000"
                  style={{
                    width: "100%", background: "#1a1a28",
                    border: "1px solid var(--border)", color: "#e0e0f0",
                    padding: "9px 10px", borderRadius: 8, fontSize: 12, outline: "none",
                  }}
                />
              </div>

              {/* Generate button */}
              <div style={{ display: "flex", alignItems: "flex-end" }}>
                <button
                  onClick={handleGenerate}
                  disabled={!canGenerate || isGenerating}
                  style={{
                    padding: "9px 20px", borderRadius: 8, border: "none",
                    background: canGenerate && !isGenerating ? "var(--accent)" : "#1a1a28",
                    color: canGenerate && !isGenerating ? "#fff" : "#333",
                    fontSize: 13, fontWeight: 700,
                    cursor: canGenerate && !isGenerating ? "pointer" : "not-allowed",
                    whiteSpace: "nowrap",
                  }}
                >
                  {isGenerating ? "⟳ Building…" : budget ? "↺ Regenerate" : "✦ Build Budget"}
                </button>
              </div>
            </div>

            <BudgetInputs value={costInputs} onChange={setCostInputs} disabled={!!loading} />

            {/* Proposal context chips */}
            {resolvedProposal && (
              <div style={{ marginTop: 14, display: "flex", gap: 8, flexWrap: "wrap" }}>
                {resolvedProposal.organization_name && (
                  <span style={{ background: "#1e1e30", color: "#666",
                    border: "1px solid #2a2a3e", borderRadius: 20,
                    padding: "3px 10px", fontSize: 11 }}>
                    🏢 {resolvedProposal.organization_name}
                  </span>
                )}
                {(resolvedProposal.geographic_focus || [])[0] && (
                  <span style={{ background: "#1e1e30", color: "#666",
                    border: "1px solid #2a2a3e", borderRadius: 20,
                    padding: "3px 10px", fontSize: 11 }}>
                    📍 {resolvedProposal.geographic_focus[0]}
                  </span>
                )}
                {resolvedProposal.project_title && (
                  <span style={{ background: "#1e1e30", color: "#666",
                    border: "1px solid #2a2a3e", borderRadius: 20,
                    padding: "3px 10px", fontSize: 11 }}>
                    📄 {resolvedProposal.project_title.slice(0, 40)}{resolvedProposal.project_title.length > 40 ? "…" : ""}
                  </span>
                )}
              </div>
            )}

            {!resolvedProposal && (
              <p style={{ marginTop: 12, color: "#444", fontSize: 12 }}>
                No proposal uploaded yet.{" "}
                <span
                  onClick={() => navigate("/grants")}
                  style={{ color: "var(--accent)", cursor: "pointer", fontWeight: 600 }}
                >
                  Choose or upload one in Grants
                </span>{" "}
                to link a proposal to this budget, or enter cost assumptions below.
              </p>
            )}
          </div>

          {/* Loading state */}
          {isGenerating && (
            <div style={{
              background: "var(--bg-card)", border: "1px solid var(--border)",
              borderRadius: 12, padding: "48px 24px", textAlign: "center",
            }}>
              <div style={{
                width: 40, height: 40, margin: "0 auto 16px",
                border: "3px solid var(--border)",
                borderTop: "3px solid var(--accent)",
                borderRadius: "50%",
                animation: "spin 0.8s linear infinite",
              }} />
              <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
              <p style={{ color: "#fff", fontWeight: 700, fontSize: 15, margin: "0 0 6px" }}>
                Building your budget…
              </p>
              <p style={{ color: "#555", fontSize: 12, margin: 0 }}>
                Calculating salary and fringe · Applying the indirect cost base · Checking the ceiling
              </p>
            </div>
          )}

          {/* Error */}
          {error && (
            <div style={{
              background: "#2d0f0f", border: "1px solid #7f1d1d",
              borderRadius: 10, padding: "14px 18px", color: "var(--red)", fontSize: 13,
            }}>
              ⚠ {error}
            </div>
          )}

          {/* Budget table */}
          {displayBudget && !isGenerating && (
            <>
              {displayBudget.model_version === 2 && <div style={{ padding: 16, border: "1px solid var(--border)", borderRadius: 8, color: "#ddd", fontSize: 13 }}>
                {displayBudget.funding_gap > 0
                  ? <p role="alert">Costs exceed the grant ceiling by {fmt(displayBudget.funding_gap)}. Staffing and unit costs have been preserved. Choose a scope change or edit the inputs.</p>
                  : <p>Costs are within the ceiling. Unrequested capacity: {fmt(displayBudget.unallocated_amount)}. Funder requirements still need review.</p>}
                {(displayBudget.compliance_summary?.warnings || []).map((warning, index) => <p key={index} style={{ color: "#facc15" }}>{warning}</p>)}
                {displayBudget.compliance_summary?.indirect && <p>Indirect base: {displayBudget.compliance_summary.indirect.base} {fmt(displayBudget.compliance_summary.indirect.base_amount)} × {displayBudget.compliance_summary.indirect.rate_pct}%. Charged indirect: {fmt(displayBudget.compliance_summary.indirect.calculated_amount)}.</p>}
                {(displayBudget.scope_options || []).map((option, index) => <div key={index} style={{ borderTop: "1px solid var(--border)", paddingTop: 10, marginTop: 10 }}>
                  <p>{option.label} Saves {fmt(option.savings)}; remaining funding gap {fmt(option.funding_gap)}.</p>
                  <button disabled={!!loading} onClick={async () => {
                    await pendingBudgetSave.current.catch(() => {});
                    setCostInputs(option.cost_inputs);
                    setMessages(previous => [...previous, { role: "user", content: `Apply scope change: ${option.label}` }]);
                    await generate(resolvedProposal || {}, displayBudget.max_budget, option.cost_inputs);
                  }}>Apply this scope change</button>
                </div>)}
              </div>}
              {/* Locality explanation banner */}
              <div style={{
                background: "#0d1a2e", border: "1px solid #1e3a5f",
                borderRadius: 10, padding: "12px 18px",
                display: "flex", gap: 10, alignItems: "flex-start",
              }}>
                <span style={{ fontSize: 16, flexShrink: 0 }}>📍</span>
                <p style={{ margin: 0, color: "#7cb9f5", fontSize: 13, lineHeight: 1.6 }}>
                  {displayBudget.locality_explanation}
                </p>
              </div>

              {/* Table */}
              <div style={{
                background: "var(--bg-card)", border: "1px solid var(--border)",
                borderRadius: 12, overflow: "hidden",
              }}>
                <div style={{
                  padding: "14px 16px 10px",
                  borderBottom: "1px solid var(--border)",
                  display: "flex", alignItems: "center", justifyContent: "space-between",
                }}>
                  <p style={{ margin: 0, fontWeight: 700, fontSize: 13, color: "#e0e0f0" }}>
                    Line Items
                  </p>
                  <span style={{ color: "#444", fontSize: 12 }}>
                    {displayBudget.items.length} categories · {fmt(displayBudget.total_requested)} total
                  </span>
                </div>
                <div style={{ padding: "8px 0 16px" }}>
                  <BudgetTable items={displayBudget.items} total={displayBudget.total_requested} />
                </div>
              </div>

              {/* Donut-style summary pills */}
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {displayBudget.items.map((item, i) => (
                  <div key={i} style={{
                    background: "var(--bg-card)", border: "1px solid var(--border)",
                    borderRadius: 8, padding: "8px 14px",
                    display: "flex", alignItems: "center", gap: 8,
                  }}>
                    <span style={{
                      width: 8, height: 8, borderRadius: "50%",
                      background: catColor(item.category), flexShrink: 0,
                    }} />
                    <span style={{ fontSize: 11, color: "#888" }}>{item.category}</span>
                    <span style={{ fontSize: 12, fontWeight: 700, color: catColor(item.category) }}>
                      {fmt(item.amount)}
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}

          {/* Empty state */}
          {!displayBudget && !isGenerating && !error && (
            <div style={{
              background: "var(--bg-card)", border: "1px dashed var(--border)",
              borderRadius: 12, padding: "60px 24px", textAlign: "center",
            }}>
              <p style={{ fontSize: 36, margin: "0 0 12px" }}>💰</p>
              <p style={{ fontWeight: 700, color: "#e0e0f0", fontSize: 18, margin: "0 0 8px" }}>
                No budget yet
              </p>
              <p style={{ color: "#555", fontSize: 13, maxWidth: 360, margin: "0 auto" }}>
                Select a grant, set the maximum amount, and click Build Budget.
                Generate a location-aware line-item breakdown based on your proposal.
              </p>
            </div>
          )}
        </div>

        {/* ── Right: Chat Panel ───────────── */}
        <div style={{
          width: "50%", flexShrink: 0,
          background: "#0d0d16", borderLeft: "1px solid var(--border)",
          display: "flex", flexDirection: "column",
          position: "sticky", top: 112,
          height: "calc(100vh - 112px)",
        }}>

          {/* Chat header */}
          <div style={{
            padding: "14px 16px", borderBottom: "1px solid var(--border)",
            display: "flex", alignItems: "center", gap: 10,
          }}>
            <div style={{
              width: 28, height: 28, borderRadius: "50%",
              background: "var(--accent-dim)",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 12, fontWeight: 800, color: "#fff",
            }}>✦</div>
            <div>
              <p style={{ margin: 0, fontWeight: 700, color: "#e0e0f0", fontSize: 13 }}>
                Budget Advisor
              </p>
              <p style={{ margin: 0, color: "#444", fontSize: 11 }}>
                {chatReady ? "Ready to refine" : "Generate a budget to start"}
              </p>
            </div>
          </div>

          {/* Messages */}
          <div style={{ flex: 1, overflowY: "auto", padding: "16px 14px" }}>
            {!chatReady && !isGenerating && (
              <div style={{ textAlign: "center", marginTop: 60 }}>
                <p style={{ fontSize: 28, margin: "0 0 12px" }}>💬</p>
                <p style={{ color: "#333", fontSize: 13, lineHeight: 1.6, maxWidth: 220, margin: "0 auto" }}>
                  Generate a budget first, then ask me to adjust any line item.
                </p>
                <div style={{ marginTop: 20, display: "flex", flexDirection: "column", gap: 6 }}>
                  {[
                    "Increase travel budget",
                    "Move $5k from equipment to training",
                    "Add a marketing line item",
                  ].map(s => (
                    <div key={s} style={{
                      background: "#111120", border: "1px solid #1e1e30",
                      borderRadius: 8, padding: "7px 12px",
                      color: "#444", fontSize: 11, textAlign: "left",
                    }}>
                      "{s}"
                    </div>
                  ))}
                </div>
              </div>
            )}

            {messages.map((msg, i) => (
              <ChatMessage key={i} msg={msg} />
            ))}

            {isRefining && (
              <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 0" }}>
                <div style={{
                  width: 28, height: 28, borderRadius: "50%",
                  background: "var(--accent-dim)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 11, color: "#fff",
                }}>✦</div>
                <div style={{ display: "flex", gap: 5 }}>
                  {[0, 1, 2].map(i => (
                    <div key={i} style={{
                      width: 7, height: 7, borderRadius: "50%",
                      background: "var(--accent)", opacity: 0.4,
                      animation: `pulse 1.2s ease-in-out ${i * 0.2}s infinite`,
                    }} />
                  ))}
                </div>
              </div>
            )}
            <style>{`
              @keyframes pulse {
                0%, 100% { opacity: 0.3; transform: scale(0.8); }
                50%       { opacity: 1;   transform: scale(1); }
              }
            `}</style>

            <div ref={chatEndRef} />
          </div>

          {/* Suggestion chips */}
          {chatReady && messages.length < 3 && (
            <div style={{ padding: "0 12px 8px", display: "flex", gap: 5, flexWrap: "wrap" }}>
              {[
                "Increase personnel",
                "Reduce travel by 20%",
                "Add a contingency line",
                "Shift budget to equipment",
              ].map(s => (
                <button
                  key={s}
                  onClick={() => { setInput(s); inputRef.current?.focus(); }}
                  style={{
                    background: "#111120", border: "1px solid #1e1e30",
                    borderRadius: 20, padding: "5px 10px",
                    color: "#555", fontSize: 11, cursor: "pointer",
                    transition: "all 0.15s",
                  }}
                  onMouseEnter={e => { e.target.style.borderColor = "var(--accent)"; e.target.style.color = "var(--accent)"; }}
                  onMouseLeave={e => { e.target.style.borderColor = "#1e1e30"; e.target.style.color = "#555"; }}
                >
                  {s}
                </button>
              ))}
            </div>
          )}

          {/* Input */}
          <div style={{
            padding: "10px 12px", borderTop: "1px solid var(--border)",
            display: "flex", gap: 8, alignItems: "flex-end",
          }}>
            <textarea
              ref={inputRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={chatReady ? "e.g. Move $5k from travel to training…" : "Generate a budget first…"}
              disabled={!chatReady || !!loading}
              rows={2}
              style={{
                flex: 1, background: "#111120",
                border: "1px solid var(--border)", borderRadius: 10,
                color: "#e0e0f0", padding: "9px 12px",
                fontSize: 12, resize: "none", outline: "none",
                fontFamily: "DM Sans, sans-serif",
                opacity: chatReady ? 1 : 0.4,
              }}
            />
            <button
              onClick={handleSend}
              disabled={!input.trim() || !chatReady || !!loading}
              style={{
                width: 36, height: 36, borderRadius: 10, border: "none",
                background: input.trim() && chatReady && !loading ? "var(--accent)" : "#1e1e30",
                color: "#fff", fontSize: 16, cursor: "pointer",
                display: "flex", alignItems: "center", justifyContent: "center",
                flexShrink: 0, transition: "background 0.15s",
              }}
            >
              ↑
            </button>
          </div>
        </div>
      </div>
      <div style={{ padding: "0 40px 16px", flexShrink: 0 }}><AiPrivacyNotice /></div>
    </div>
  );
}
