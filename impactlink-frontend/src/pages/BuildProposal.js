import { useState, useRef, useEffect, useReducer, useCallback } from "react";
import { useNavigate, useSearchParams, useLocation } from "react-router-dom";
import { Nav } from "../components";
import useGrants from "../hooks/useGrants";
import { useAuth } from "../context/AuthContext";
import api, { reviseSection, checkProposalConsistency, saveSessionChecklist } from "../services/api";
import useWorkStore from "../hooks/useWorkStore";
import useProposalSession from "../hooks/useProposalSession";
import { createProposalPdf } from "../utils/proposalPdf";
import { proposalContext, stageProposalMatch } from "../services/proposals";
import BuildDraftPreview, { buildPreviewReducer } from "../components/BuildDraftPreview";
import { ApplicationRequirementsEditor, ApplicationReview } from "../components/ApplicationRequirements";
import AiPrivacyNotice from "../components/AiPrivacyNotice";
import "./Draft.css";
import ConsistencyReview from "../components/ConsistencyReview";
import { applicationCheck, lengthCheck, sectionRequirements, applicationChecklistInput, aiPolicyCheck, emptyApplicationSpec } from "../utils/application";

// ── helpers ───────────────────────────────────────────────────

function loadJsPDF() {
  return new Promise((resolve, reject) => {
    if (window.jspdf) return resolve();
    const s = document.createElement("script");
    s.src = "https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js";
    s.onload = resolve; s.onerror = reject;
    document.head.appendChild(s);
  });
}

const STEP_ICONS = ["🎯","⚡","👥","🏛","📊","💰","🌱"];

const ORCHESTRATION_STEPS = [
  { id: "vocab",    agent: "VocabExtractor",   label: "Extract funder vocabulary" },
  { id: "slots",    agent: "SlotExtractor",    label: "Collect organization details" },
  { id: "plan",     agent: "PlanningAgent",    label: "Analyze grant & build drafting plan" },
  { id: "wave1",    agent: "SectionSubgraph",  label: "Wave 1 — problem, solution, beneficiaries" },
  { id: "wave2",    agent: "SectionSubgraph",  label: "Wave 2 — goals, evaluation, budget" },
  { id: "wave3",    agent: "SectionSubgraph",  label: "Wave 3 — executive summary, sustainability" },
  { id: "coherence",agent: "CoherenceAgent",   label: "Cross-section coherence check" },
  { id: "review",   agent: "Human Gate",       label: "Ready for your review" },
];

const DRAFTING_STEP_IDS = ["plan", "wave1", "wave2", "wave3", "coherence"];

const AGENT_COLORS = {
  VocabExtractor:   "#8b5cf6",
  SlotExtractor:    "#6366f1",
  PlanningAgent:    "#a78bfa",
  draft_sections:   "#6c63ff",
  SectionDraftAgent:"#6c63ff",
  SectionScoringAgent:"#f59e0b",
  SectionRewriteAgent:"#ef4444",
  SectionToolAgent: "#10b981",
  CoherenceAgent:   "#14b8a6",
  "Human Gate":     "#22c55e",
};

function stepStatusFromGate(stepId, gate, isDrafting) {
  const order = ORCHESTRATION_STEPS.map(s => s.id);
  const idx = order.indexOf(stepId);

  if (gate === "none" && stepId === "vocab") return "active";
  if (gate === "slot_filling") {
    if (idx < 1) return "done";
    if (stepId === "slots") return "active";
    return "pending";
  }
  if (gate === "slot_confirm") {
    if (idx < 2) return "done";
    if (stepId === "plan") return "active";
    return "pending";
  }
  if (isDrafting) {
    if (idx < 2) return "done";
    if (DRAFTING_STEP_IDS.includes(stepId)) return "active";
    return "pending";
  }
  if (["draft_review", "final_save", "complete"].includes(gate)) {
    if (stepId === "review") return gate === "draft_review" ? "active" : "done";
    return idx < order.length - 1 ? "done" : "pending";
  }
  return "pending";
}

function AgentOrchestrationPanel({ gate, loading, agentTrace, draftingPlan, compact }) {
  const [draftTick, setDraftTick] = useState(0);
  const isDrafting = loading && !["slot_filling", "none"].includes(gate);

  useEffect(() => {
    if (!isDrafting) return undefined;
    const t = setInterval(() => setDraftTick(n => n + 1), 4000);
    return () => clearInterval(t);
  }, [isDrafting]);

  const activeDraftStep = DRAFTING_STEP_IDS[draftTick % DRAFTING_STEP_IDS.length];

  const trace = agentTrace || [];
  const priorities = draftingPlan?.section_priorities
    ?.slice()
    .sort((a, b) => a.priority - b.priority)
    .slice(0, 3) || [];

  if (!gate || gate === "none") return null;

  return (
    <div style={{
      marginBottom: compact ? 12 : 18,
      background: "#0c0c18",
      border: "1px solid #2a2a4e",
      borderRadius: 12,
      overflow: "hidden",
    }}>
      <div style={{
        padding: "10px 14px",
        borderBottom: "1px solid #1e1e30",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        background: "var(--bg-card)",
      }}>
        <span style={{ fontSize: 11, fontWeight: 800, color: "#a5b4fc",
          letterSpacing: "0.08em", textTransform: "uppercase" }}>
          Draft progress
        </span>
        {isDrafting && (
          <span style={{ fontSize: 10, color: "var(--accent)", fontWeight: 700,
            animation: "pulse 1.5s ease-in-out infinite" }}>
            Preparing your application…
          </span>
        )}
      </div>

      <div style={{ padding: compact ? "10px 12px" : "12px 14px" }}>
        {/* Pipeline */}
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {ORCHESTRATION_STEPS.map((step) => {
            let status = stepStatusFromGate(step.id, gate, isDrafting);
            if (isDrafting && DRAFTING_STEP_IDS.includes(step.id)) {
              status = step.id === activeDraftStep ? "active"
                : DRAFTING_STEP_IDS.indexOf(step.id) < DRAFTING_STEP_IDS.indexOf(activeDraftStep)
                  ? "done" : "pending";
            }
            const color = AGENT_COLORS[step.agent] || "var(--accent)";
            const dot = status === "done" ? "✓" : status === "active" ? "●" : "○";
            const dotColor = status === "done" ? "#22c55e"
              : status === "active" ? color : "#333";

            return (
              <div key={step.id} style={{
                display: "flex", alignItems: "flex-start", gap: 8,
                opacity: status === "pending" ? 0.45 : 1,
                transition: "opacity 0.3s",
              }}>
                <span style={{
                  color: dotColor, fontSize: 10, fontWeight: 800,
                  width: 14, flexShrink: 0, marginTop: 2,
                }}>{dot}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <span style={{ fontSize: 10, fontWeight: 700, color }}>{step.agent}</span>
                  <p style={{ margin: "1px 0 0", fontSize: 11, color: "#888", lineHeight: 1.4 }}>
                    {step.label}
                  </p>
                </div>
              </div>
            );
          })}
        </div>

        {/* Planning priorities */}
        {priorities.length > 0 && (
          <div style={{
            marginTop: 12, padding: "10px 12px",
            background: "#111120", borderRadius: 8,
            border: "1px solid #1e1e30",
          }}>
            <p style={{ margin: "0 0 6px", fontSize: 10, fontWeight: 700,
              color: "#a78bfa", textTransform: "uppercase", letterSpacing: "0.06em" }}>
              PlanningAgent priorities
            </p>
            {priorities.map((p) => (
              <p key={p.key} style={{ margin: "4px 0", fontSize: 11, color: "#999", lineHeight: 1.4 }}>
                <span style={{ color: "#ccc", fontWeight: 600 }}>
                  {p.key.replace(/_/g, " ")}
                </span>
                {" "}(p{p.priority})
                {p.evidence_needed?.length > 0 && (
                  <span style={{ color: "#666" }}> — needs {p.evidence_needed.slice(0, 2).join(", ")}</span>
                )}
              </p>
            ))}
          </div>
        )}

        {/* Decision log */}
        {trace.length > 0 && (
          <div style={{
            marginTop: 12, padding: "10px 12px",
            background: "#080810", borderRadius: 8,
            border: "1px solid #1a1a28",
            maxHeight: compact ? 140 : 200, overflowY: "auto",
          }}>
            <p style={{ margin: "0 0 8px", fontSize: 10, fontWeight: 700,
              color: "#555", textTransform: "uppercase", letterSpacing: "0.06em" }}>
              Decision log
            </p>
            {trace.map((entry, i) => (
              <div key={i} style={{
                marginBottom: 6, fontSize: 11, lineHeight: 1.45,
                fontFamily: "ui-monospace, 'Cascadia Code', monospace",
              }}>
                <span style={{
                  color: AGENT_COLORS[entry.agent] || "var(--accent)",
                  fontWeight: 700,
                }}>[{entry.agent}]</span>
                <span style={{ color: "#777" }}> {entry.decision}</span>
              </div>
            ))}
          </div>
        )}

        {isDrafting && (
          <p style={{ margin: "10px 0 0", fontSize: 10, color: "#555", lineHeight: 1.5 }}>
            Drafting your proposal with PlanningAgent → SectionSubgraph (score/route/retry) → CoherenceAgent.
            This usually takes 30–90 seconds.
          </p>
        )}
      </div>

      <style>{`@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.5} }`}</style>
    </div>
  );
}

// Animated typing dots
function TypingDots() {
  return (
    <div style={{ display: "flex", gap: 5, padding: "4px 0" }}>
      {[0,1,2].map(i => (
        <div key={i} style={{
          width: 8, height: 8, borderRadius: "50%",
          background: "var(--accent)", opacity: 0.4,
          animation: `dotPulse 1.2s ease-in-out ${i*0.2}s infinite`,
        }} />
      ))}
      <style>{`
        @keyframes dotPulse {
          0%,100% { opacity: 0.3; transform: translateY(0); }
          50%      { opacity: 1;   transform: translateY(-3px); }
        }
      `}</style>
    </div>
  );
}

// Draft section card — shows section content with approve/revise controls
function DraftCard({ stepKey, title, content, onApprove, onRevise, approved, icon, requirements, applicationSpec }) {
  const [showRevise,  setShowRevise]  = useState(false);
  const [feedback,    setFeedback]    = useState("");
  const [revising,    setRevising]    = useState(false);
  const [editMode,    setEditMode]    = useState(false);
  const [editContent, setEditContent] = useState(content);

  // Keep editContent in sync if parent updates content (e.g. after AI revise)
  const prevContent = useState(content)[0];
  if (content !== prevContent && !editMode) {
    // noop — React way is useEffect, but this avoids stale closure
  }

  const handleRevise = async () => {
    if (!feedback.trim() || !aiPolicyCheck(applicationSpec).ai_drafting_allowed) return;
    setRevising(true);
    try {
      const data = await reviseSection(content, feedback, title, requirements?.key ? requirements : undefined, applicationSpec);
      onRevise(data.content);
      setEditContent(data.content);
      setFeedback("");
      setShowRevise(false);
    } catch(e) {
      console.error(e);
    } finally { setRevising(false); }
  };

  const handleSaveEdit = () => {
    onRevise(editContent);
    setEditMode(false);
  };

  const handleCancelEdit = () => {
    setEditContent(content); // revert
    setEditMode(false);
  };

  return (
    <div style={{
      display: "flex", gap: 10, margin: "12px 0",
    }}>
      <div aria-hidden="true" style={{ width: 30, height: 30, flexShrink: 0, borderRadius: "50%", background: "var(--accent-dim)", display: "grid", placeItems: "center" }}>✦</div>
      <div style={{ flex: 1, minWidth: 0 }}>
      {/* header */}
      <div style={{
        padding: "4px 0 10px", display: "flex", flexWrap: "wrap", gap: 10,
        alignItems: "center", justifyContent: "space-between",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 16 }}>{icon}</span>
          <span style={{ fontWeight: 700, color: approved ? "var(--green)" : "#e0e0f0",
            fontSize: 13 }}>
            {title}
          </span>
          {approved && (
            <span style={{ background: "#166534", color: "var(--green)",
              borderRadius: 20, padding: "2px 9px", fontSize: 10, fontWeight: 700 }}>
              ✓ Approved
            </span>
          )}
          {editMode && (
            <span style={{ background: "#1e1e3a", color: "var(--accent)",
              borderRadius: 20, padding: "2px 9px", fontSize: 10, fontWeight: 700,
              border: "1px solid var(--accent)" }}>
              ✎ Editing
            </span>
          )}
        </div>

        {!approved && !editMode && (
          <div style={{ display: "flex", gap: 8 }}>
            {/* Inline edit button */}
            <button
              onClick={() => { setEditContent(content); setEditMode(true); setShowRevise(false); }}
              title="Edit directly"
              style={{ background: "none", border: "1px solid #2a2a3e",
                color: "#555", padding: "5px 10px", borderRadius: 7,
                fontSize: 13, cursor: "pointer", lineHeight: 1 }}
              onMouseEnter={e => { e.target.style.borderColor = "var(--accent)"; e.target.style.color = "var(--accent)"; }}
              onMouseLeave={e => { e.target.style.borderColor = "#2a2a3e"; e.target.style.color = "#555"; }}
            >
              ✎
            </button>
            <button
              onClick={() => { setShowRevise(v => !v); setEditMode(false); }}
              disabled={!aiPolicyCheck(applicationSpec).ai_drafting_allowed}
              style={{ background: "#1a1a28", border: "1px solid #2a2a3e",
                color: "#888", padding: "5px 12px", borderRadius: 7,
                fontSize: 11, fontWeight: 600, cursor: "pointer" }}
            >
              Revise
            </button>
            <button
              onClick={onApprove}
              disabled={!lengthCheck(content, requirements).within_limits}
              style={{ background: "var(--accent)", border: "none",
                color: "#fff", padding: "5px 14px", borderRadius: 7,
                fontSize: 11, fontWeight: 700, cursor: "pointer" }}
            >
              ✓ Approve
            </button>
          </div>
        )}

        {/* Save / Cancel when in edit mode */}
        {editMode && (
          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={handleCancelEdit}
              style={{ background: "none", border: "1px solid #2a2a3e",
                color: "#666", padding: "5px 12px", borderRadius: 7,
                fontSize: 11, cursor: "pointer" }}
            >
              Cancel
            </button>
            <button
              onClick={handleSaveEdit}
              style={{ background: "var(--accent)", border: "none",
                color: "#fff", padding: "5px 14px", borderRadius: 7,
                fontSize: 11, fontWeight: 700, cursor: "pointer" }}
            >
              ✓ Save
            </button>
          </div>
        )}
      </div>

      {/* Revision box */}
      {showRevise && !approved && !editMode && (
        <div style={{
          padding: "14px 18px",
          borderBottom: "1px solid #1e1e30",
          background: "#0d0d16",
        }}>
          <p style={{ color: "#555", fontSize: 11, margin: "0 0 8px" }}>
            What would you like to change?
          </p>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              value={feedback}
              onChange={e => setFeedback(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter") handleRevise(); }}
              placeholder="e.g. Make it more specific, add our Nairobi data…"
              style={{
                flex: 1, background: "#0a0a0f", border: "1px solid #2a2a3e",
                borderRadius: 8, color: "#e0e0f0", padding: "8px 12px",
                fontSize: 12, outline: "none",
              }}
              autoFocus
            />
            <button
              onClick={handleRevise}
              disabled={revising || !feedback.trim()}
              style={{
                background: revising ? "#1a1a28" : "var(--accent)",
                border: "none", color: "#fff",
                padding: "8px 16px", borderRadius: 8,
                fontSize: 12, fontWeight: 700, cursor: "pointer",
                flexShrink: 0,
              }}
            >
              {revising ? "⟳" : "↑"}
            </button>
          </div>
        </div>
      )}

      {/* content — editable textarea or read-only prose */}
      <div style={{ padding: "4px 0 20px" }}>
        {editMode ? (
          <textarea
            value={editContent}
            onChange={e => setEditContent(e.target.value)}
            autoFocus
            style={{
              width: "100%", minHeight: 200,
              background: "#0a0a14", border: "1px solid #2a2a4e",
              borderRadius: 8, color: "#e0e0f0",
              padding: "12px 14px", fontSize: 13,
              lineHeight: 1.9, fontFamily: "Georgia, serif",
              resize: "vertical", outline: "none",
              boxSizing: "border-box",
            }}
          />
        ) : (
          <p style={{ margin: 0, color: "#bbb", fontSize: 13, lineHeight: 1.9,
            fontFamily: "Georgia, serif", whiteSpace: "pre-wrap" }}>
            {content}
          </p>
        )}
      </div>
      </div>
    </div>
  );
}

// ── main page ─────────────────────────────────────────────────

export default function BuildProposal() {
  const navigate       = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const { profile } = useAuth();
  const { grants }  = useGrants();
  const { saveBuild, updateBuild, builds, loading: workLoading } = useWorkStore();
  const [savedBuildId, setSavedBuildId] = useState(null);
  const savedBuildIdRef = useRef(null);
  const pendingBuildSave = useRef(null);
  const autoSavedSession = useRef(null);
  const restoredBuild = useRef(null);
  const [buildSaveError, setBuildSaveError] = useState(null);
  const [findingGrants, setFindingGrants] = useState(false);

  // The conversation — array of { role: "ai"|"user", type, ...data }
  const [messages,  setMessages]  = useState([]);
  const [input,     setInput]     = useState("");
  const [slotEdits, setSlotEdits] = useState({});
  const [draftInstructions, setDraftInstructions] = useState("");
  const confirmationSession = useRef(null);
  const [pdfLoading,setPdfLoad]   = useState(false);
  const [done,      setDone]      = useState(false);

  // Collected answers: [{ step_key, user_answer }]
  const [answers,   setAnswers]   = useState([]);
  // Drafted sections: { section_key: { title, content, approved } }
  const [sections,  setSections]  = useState({});
  const [coherenceReview, setCoherenceReview] = useState(null);
  const [checkingConsistency, setCheckingConsistency] = useState(false);
  const sectionsRef = useRef(sections);
  sectionsRef.current = sections;
  const [liveSections, updateLiveSections] = useReducer(buildPreviewReducer, {});
  const [secOrder,  setSecOrder]  = useState([]);

  const [selectedGrantId, setSelectedGrant] = useState(searchParams.get("grant") || "");
  const [applicationSpec, setApplicationSpec] = useState(null);
  const [proposalName,   setProposalName]   = useState("");
  const [grantDetails, setGrantDetails] = useState(null);
  const [prefilling, setPrefilling] = useState(false);
  const [prefill, setPrefill] = useState(null);
  const [prefillError, setPrefillError] = useState("");
  const [starting, setStarting] = useState(false);
  const prefillRequest = useRef(0);
  const workspace = location.pathname.endsWith("/write") || Boolean(searchParams.get("session") || searchParams.get("load"));

  const chatEndRef = useRef(null);
  const followChatRef = useRef(true);
  const inputRef   = useRef(null);
  const session = useProposalSession(searchParams.get("session"));
  const selectedGrant = (String(grantDetails?.grant_id) === String(selectedGrantId) ? grantDetails : null)
    || grants.find(g => String(g.grant_id) === String(selectedGrantId)) || (workspace ? session.data.grant : null);

  useEffect(() => {
    if (workspace || !selectedGrantId || session.loading) return undefined;
    const request = ++prefillRequest.current;
    let active = true;
    setPrefilling(true); setPrefill(null); setPrefillError(""); setApplicationSpec(emptyApplicationSpec());
    (async () => {
      try {
        const response = await api.get(`/api/grants/${encodeURIComponent(selectedGrantId)}`);
        const grant = response.data.grant || response.data;
        if (!active || request !== prefillRequest.current) return;
        setGrantDetails(grant);
        const result = grant.application_spec ? { application_spec: grant.application_spec, evidence: [], warnings: ["Review the requirements already recorded for this grant."] }
          : (await api.post(`/api/grants/${encodeURIComponent(selectedGrantId)}/application-requirements`)).data;
        if (!active || request !== prefillRequest.current) return;
        setApplicationSpec({ ...emptyApplicationSpec(), ...result.application_spec });
        setPrefill(result);
      } catch (_) {
        if (active && request === prefillRequest.current) setPrefillError("Could not prefill this grant's requirements. You can enter them manually below.");
      } finally { if (active && request === prefillRequest.current) setPrefilling(false); }
    })();
    return () => { active = false; };
    // Only selecting a grant starts prefill; editing the form does not refetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedGrantId, workspace]);

  useEffect(() => {
    if (session.data.grant?.build_context?.proposal_name) setProposalName(previous => previous || session.data.grant.build_context.proposal_name);
  }, [session.data.grant]);
  useEffect(() => {
    if (session.data.application_spec) setApplicationSpec(session.data.application_spec);
  }, [session.data.application_spec]);
  useEffect(() => {
    if (session.data.coherence_review !== undefined) setCoherenceReview(previous => {
      const incoming = session.data.coherence_review;
      // A manual recheck can be newer than the graph's original drafting check.
      if (incoming?.status === "stale" && previous?.content_fingerprint && previous.content_fingerprint !== incoming.content_fingerprint && ["passed", "issues_found"].includes(previous.status)) return previous;
      return incoming;
    });
  }, [session.data.coherence_review]);

  const buildSnapshot = useCallback((source, reviewOverride = coherenceReview || session.data.coherence_review || null) => {
    const previous = builds.find(item => item.id === savedBuildIdRef.current) || {};
    const cleanSections = Object.fromEntries(Object.entries(source || {}).map(([key, section]) => [key, {
      title: section.title || key, content: section.content || "",
    }]));
    const payload = {
      title: proposalName.trim() || previous.title || selectedGrant?.title || profile?.org_name || "Built Proposal",
      org_name: profile?.org_name || previous.org_name || "", grant_title: selectedGrant?.title || previous.grant_title || "",
      grant_id: selectedGrant?.grant_id ? String(selectedGrant.grant_id) : previous.grant_id || "",
      sections: cleanSections, section_order: Object.keys(cleanSections), answers: answers.length ? answers : previous.answers || [],
      session_id: session.sessionId || previous.session_id,
      application_spec: applicationSpec || session.data.application_spec || previous.application_spec || null,
      coherence_review: reviewOverride,
      status: Object.values(source || {}).every(section => section.approved) ? "approved" : "draft",
    };
    if (!applicationCheck(payload.application_spec, source).can_finalize_text || aiPolicyCheck(payload.application_spec).disclosure_pending) payload.status = "draft";
    payload.proposal_context = proposalContext({ ...payload, proposal_context: previous.proposal_context }, profile || {});
    return payload;
  }, [proposalName, selectedGrant, profile, answers, session.sessionId, session.data.application_spec, session.data.coherence_review, applicationSpec, coherenceReview, builds]);

  const persistBuild = useCallback(async (source, reviewOverride) => {
    if (pendingBuildSave.current) await pendingBuildSave.current;
    const payload = buildSnapshot(source, reviewOverride);
    const id = savedBuildIdRef.current;
    const operation = id ? updateBuild(id, payload.sections, null, payload) : saveBuild(payload);
    const pending = operation.then(saved => {
      if (!saved) throw new Error("Could not save this proposal. Please try again.");
      savedBuildIdRef.current = saved.id;
      setSavedBuildId(saved.id);
      return saved;
    });
    pendingBuildSave.current = pending;
    try { return await pending; }
    finally { if (pendingBuildSave.current === pending) pendingBuildSave.current = null; }
  }, [buildSnapshot, updateBuild, saveBuild]);

  const saveApplicationChecklist = async nextSpec => {
    const savedBuild = builds.find(item => item.id === savedBuildIdRef.current);
    const id = session.sessionId || savedBuild?.session_id;
    if (id) await saveSessionChecklist(id, nextSpec);
    return persistBuild(sections);
  };

  const handleCheckConsistency = async () => {
    if (checkingConsistency || !aiPolicyCheck(applicationSpec || selectedGrant?.application_spec).ai_drafting_allowed) return;
    setCheckingConsistency(true);
    const source = sectionsRef.current;
    const contentKey = value => JSON.stringify(Object.entries(value).map(([key, item]) => [key, item.content || ""]).sort(([left], [right]) => left.localeCompare(right)));
    try {
      const review = await checkProposalConsistency(source, applicationSpec || selectedGrant?.application_spec);
      const current = sectionsRef.current;
      const next = contentKey(current) === contentKey(source) ? review : { ...review, status: "stale", reason: "Text changed while the check was running. Check the updated proposal again." };
      setCoherenceReview(next);
      try { await persistBuild(current, next); }
      catch (error) { setBuildSaveError(error.message || "Could not save consistency results. Please retry saving."); }
    } catch (error) {
      const next = { status: "unavailable", issues: [], reason: "The consistency check could not be completed. No pass was issued; review manually or retry." };
      setCoherenceReview(next);
      setBuildSaveError(typeof error.response?.data?.detail === "string" ? error.response.data.detail : error.message || "Could not check consistency.");
      try { await persistBuild(sectionsRef.current, next); }
      catch (saveError) { setBuildSaveError(saveError.message || "Could not save consistency results."); }
    } finally { setCheckingConsistency(false); }
  };

  useEffect(() => {
    if (workLoading || searchParams.get("load") || session.gate !== "draft_review" || !session.sessionId || !Object.keys(session.data.sections || {}).length || autoSavedSession.current === session.sessionId) return;
    autoSavedSession.current = session.sessionId;
    const existing = builds.find(item => item.session_id === session.sessionId);
    if (existing) {
      savedBuildIdRef.current = existing.id;
      setSavedBuildId(existing.id);
    }
    persistBuild(session.data.sections).catch(error => {
      setBuildSaveError(error.message);
    });
  }, [workLoading, builds, session.gate, session.sessionId, session.data.sections, searchParams, persistBuild]);

  const handleFindGrants = async () => {
    if (findingGrants) return;
    setFindingGrants(true);
    setBuildSaveError(null);
    try {
      const saved = await persistBuild(sections);
      navigate(stageProposalMatch({ ...saved, _type: "build" }, profile || {}));
    } catch (error) { setBuildSaveError(error.message); }
    finally { setFindingGrants(false); }
  };

  // Keep the checkpoint ID in the URL so a refresh can recover a long draft.
  useEffect(() => {
    if (!workspace || !session.sessionId || searchParams.get("session") === session.sessionId) return;
    setSearchParams(previous => {
      const next = new URLSearchParams(previous);
      next.set("session", session.sessionId);
      return next;
    }, { replace: true });
  }, [workspace, session.sessionId, searchParams, setSearchParams]);

  // Scroll to bottom on new messages
  useEffect(() => {
    if (followChatRef.current) {
      chatEndRef.current?.scrollIntoView({ behavior: session.loading ? "auto" : "smooth" });
    }
  }, [messages, session.loading, liveSections, sections]);

  // Sync session data to local UI state for backwards compatibility with existing render logic
  useEffect(() => {
    if (session.gate === "draft_review" || session.gate === "final_save" || session.gate === "complete") {
      if (session.data.sections) {
        setSections(prev => {
          let hasChanges = Object.keys(session.data.sections).length !== Object.keys(prev).length;
          const restored = {};
          Object.entries(session.data.sections).forEach(([k, v]) => {
            const prevApproved = prev[k]?.approved || false;
            restored[k] = { ...v, approved: prevApproved };
            // Check if content or title changed
            if (prev[k]?.content !== v.content || prev[k]?.title !== v.title) {
              hasChanges = true;
            }
          });
          if (hasChanges) setSecOrder(Object.keys(restored));
          return hasChanges ? restored : prev;
        });
      }
      if (session.gate === "complete") setDone(true);
    }

    // Identify next question if in slot_filling
    if (session.gate === "slot_filling" && session.data.question) {
      const nextSlotKey = session.data.slot_key;
      const question = session.data.question;
      const filled = session.data.slots_filled || 0;
      const total = session.data.slots_total || 7;

      setMessages(prev => {
        const last = prev[prev.length - 1];
        if (last?.type === "question" && last.key === nextSlotKey) return prev;
        return [...prev, {
          role: "ai",
          type: "question",
          key: nextSlotKey,
          text: question,
          step: filled + 1,
          total: total
        }];
      });
    }

    if (session.gate === "slot_confirm") {
        if (confirmationSession.current !== session.sessionId) {
            confirmationSession.current = session.sessionId;
            setSlotEdits({});
            setDraftInstructions("");
        }
        setMessages(prev => {
            if (prev.some(message => message.type === "slot_confirm")) return prev;
            return [...prev, { role: "ai", type: "slot_confirm", text: "Review and edit your answers below. Add any extra details or instructions, then confirm to start drafting." }];
        });
    }

    if (session.gate === "draft_review" && !done) {
        setMessages(prev => {
            if (prev[prev.length-1]?.type === "draft_ready") return prev;
            return [...prev, { role: "ai", type: "draft_ready", text: "✨ All sections drafted! Review each section, then click Confirm Draft & Continue to advance the session." }];
        });
    }

    if (session.gate === "final_save" && !done) {
        setMessages(prev => {
            if (prev[prev.length-1]?.type === "final_save") return prev;
            return [...prev, { role: "ai", type: "final_save", text: "Draft confirmed. Click Complete Session to finish, then download your PDF." }];
        });
    }
  }, [session.gate, session.data, session.sessionId, done]);

  // Log agent routing decisions to browser console (portfolio demo)
  useEffect(() => {
    const trace = session.data.agent_trace;
    if (!trace?.length) return;
    console.group("[ImpactLink Agent Trace]");
    trace.forEach((entry) => {
      console.log(`[${entry.agent}] ${entry.decision}`);
    });
    console.groupEnd();
  }, [session.data.agent_trace]);

  // ── Start / advance the build flow ──────────────────────────

  const handleStart = async () => {
    if (starting || prefilling || session.loading || session.data.running || !aiPolicyCheck(applicationSpec || selectedGrant?.application_spec).ai_drafting_allowed) return;
    setStarting(true);
    try {
      if (pendingBuildSave.current) await pendingBuildSave.current.catch(() => {});
      savedBuildIdRef.current = null; autoSavedSession.current = null; restoredBuild.current = null;
      confirmationSession.current = null; setSlotEdits({}); setDraftInstructions("");
      setSavedBuildId(null); setDone(false); setAnswers([]); setSections({}); setSecOrder([]); setCoherenceReview(null); setBuildSaveError(null);
      updateLiveSections({ type: "reset" });
      session.reset();
      setMessages([{ role: "ai", type: "intro", text: "Let's build your proposal. I'll ask for the information we need, then draft the sections for your review." }]);
      navigate("/build/write");
      await session.start("scratch", {
        ...(selectedGrant || { title: "New Project" }),
        application_spec: applicationSpec || emptyApplicationSpec(),
        build_context: { proposal_name: proposalName.trim() },
      }, profile || { org_name: "Your Organization" });
    } catch (err) {
      console.error("Start error:", err);
      setMessages([]);
    } finally { setStarting(false); }
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text || session.loading || done) return;
    setInput("");

    // If we are in slot_filling, we send an answer
    if (session.gate === "slot_filling") {
        const lastQuestion = [...messages].reverse().find(m => m.type === "question");
        if (!lastQuestion) return;

        setMessages(prev => [...prev, { role: "user", type: "answer", text, stepKey: lastQuestion.key }]);
        setAnswers(prev => [...prev, { step_key: lastQuestion.key, user_answer: text }]);
        
        try {
          await session.advance({ answer: text, slot_key: lastQuestion.key });
        } catch (_) {
          // The session hook exposes the failure in the recovery panel below.
        }
    }
  };

  const handleConfirmSlots = async () => {
      if (session.loading || session.data.running || session.error || session.gate !== "slot_confirm") return;
      const confirmedSlots = Object.fromEntries(Object.entries(session.data.slots || {}).map(([key, slot]) => [key, slotEdits[key] ?? slot.value ?? ""]));
      setAnswers(Object.entries(confirmedSlots).map(([step_key, user_answer]) => ({ step_key, user_answer })));
      setMessages(prev => [...prev, { role: "user", type: "answer", text: "Confirmed. Please proceed to drafting." }]);
      updateLiveSections({ type: "reset" });
      try {
        await session.advanceStream(
          { confirmed: true, slots: confirmedSlots, draft_instructions: draftInstructions.trim() },
          (sectionKey, content) => updateLiveSections({ type: "token", section_key: sectionKey, content }),
          updateLiveSections,
        );
      } catch (_) {
        // Keep the current session available for status recovery.
      }
  };

  // ── Approve / revise section ──────────────────────────────

  const handleApprove = async (sectionKey) => {
    const updatedSections = {
      ...sections,
      [sectionKey]: { ...sections[sectionKey], approved: true },
    };
    setSections(updatedSections);

    // Check if this was the last section to approve
    const allNowApproved = secOrder.length > 0 &&
      secOrder.every(k => updatedSections[k]?.approved);

    if (allNowApproved) {
      try {
        const saved = await persistBuild(updatedSections);
        sessionStorage.setItem("proposal", JSON.stringify(saved.proposal_context));
      } catch (error) { setBuildSaveError(error.message); }
    }
  };

  const handleRevise = (sectionKey, newContent) => {
    if (sections[sectionKey]?.content !== newContent) setCoherenceReview(previous => previous ? { ...previous, status: "stale", reason: "Text changed after the consistency check. Check the updated proposal again or review it manually." } : null);
    setSections(prev => ({
      ...prev,
      [sectionKey]: { ...prev[sectionKey], content: newContent, approved: false },
    }));
  };

  const handleConfirmDraftReview = async () => {
    const payload = {};
    secOrder.forEach((k) => {
      payload[k] = sections[k]?.content ?? "";
    });
    try {
      await session.advance({ sections: payload, ...applicationChecklistInput(applicationSpec) });
    } catch (e) {
      console.error("Confirm draft error:", e);
    }
  };

  const handleCompleteSession = async () => {
    try {
      if (aiPolicyCheck(applicationSpec).disclosure_pending) return;
      await persistBuild(sections);
      await session.advance(applicationChecklistInput(applicationSpec));
      setDone(true);
    } catch (e) {
      console.error("Complete session error:", e);
    }
  };

  // ── PDF download ──────────────────────────────────────────

  const handlePDF = async () => {
    if (!secOrder.length) return;
    setPdfLoad(true);
    try {
      await loadJsPDF();
      const { jsPDF } = window.jspdf;
      const doc = createProposalPdf(jsPDF, {
        title: proposalName.trim() || selectedGrant?.title || "Grant Proposal",
        agency: selectedGrant?.agency || "",
        organization: profile?.org_name || "Your Organization",
        sections,
        sectionOrder: secOrder,
      });

      const slug = (proposalName.trim() || profile?.org_name || "proposal").replace(/\s+/g,"_").toLowerCase();
      doc.save(`${slug}_built_proposal.pdf`);
    } catch(e) { console.error(e); } finally { setPdfLoad(false); }
  };

  // Reload a saved build — from ?load=<id> param (Dashboard) or sessionStorage (legacy)
  const loadId = searchParams.get("load");
  useEffect(() => {
    // Try ?load=id from work store first
    if (loadId && builds.length > 0 && restoredBuild.current !== loadId) {
      const saved = builds.find(b => b.id === loadId);
      if (saved) {
        restoredBuild.current = loadId;
        savedBuildIdRef.current = saved.id;
        setProposalName(saved.title || "");
        setApplicationSpec(saved.application_spec || saved.proposal_context?.application_spec || null);
        setCoherenceReview(saved.coherence_review || null);
        if (saved.grant_id) setSelectedGrant(saved.grant_id);
        const savedSecs  = saved.sections      || {};
        const savedOrder = saved.section_order || Object.keys(savedSecs);
        const restored   = {};
        savedOrder.forEach(k => {
          if (savedSecs[k]) restored[k] = { ...savedSecs[k], approved: saved.status === "approved" || Boolean(savedSecs[k].approved) };
        });
        setSections(restored);
        setSecOrder(savedOrder);
        setAnswers(saved.answers || []);
        setSavedBuildId(saved.id);
        setDone(true);
        setMessages([{
          role: "ai", type: "complete",
          text: "✨ Restored your saved proposal. Review and approve each section, then download.",
        }]);
        return;
      }
    }

    // Fallback: legacy sessionStorage path
    const raw = sessionStorage.getItem("saved_build");
    if (raw) {
      try {
        const { sections: savedSecs, section_order: savedOrder, answers: savedAnswers, application_spec: savedSpec, coherence_review: savedReview } = JSON.parse(raw);
        if (savedSecs && savedOrder) {
          const restored = {};
          savedOrder.forEach(k => {
            if (savedSecs[k]) restored[k] = { ...savedSecs[k], approved: false };
          });
          setSections(restored);
          setSecOrder(savedOrder);
          setAnswers(savedAnswers || []);
          if (savedSpec) setApplicationSpec(savedSpec);
          setCoherenceReview(savedReview || null);
          setDone(true);
          setMessages([{
            role: "ai", type: "complete",
            text: "✨ Restored your saved proposal. Review and approve each section, then download.",
          }]);
        }
      } catch (_) {}
      sessionStorage.removeItem("saved_build");
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadId, builds]);

  // ── derived ───────────────────────────────────────────────

  const approvedCount  = Object.values(sections).filter(s => s.approved).length;
  const totalSections  = secOrder.length;
  const applicationReport = applicationCheck(applicationSpec, sections);
  const allApproved    = totalSections > 0 && approvedCount === totalSections && applicationReport.can_finalize_text && !aiPolicyCheck(applicationSpec).disclosure_pending;
  const hasStarted     = messages.length > 0;
  const loading        = session.loading || Boolean(session.data.running);
  const showOrchestration = hasStarted && session.gate !== "none";
  const agentTrace = session.data.agent_trace || [];
  const draftingPlan = session.data.drafting_plan;
  const showRightPanel = showOrchestration;
  const ORCHESTRATION_PANEL_WIDTH = "28%";
  const HEADER_HEIGHT = 112; // Nav (64px) + app bar (48px)

  // ── render ────────────────────────────────────────────────

  if (!workspace) return <div className="draft-workspace"><Nav />
    <main className="draft-setup il-form">
      <header><p className="draft-eyebrow">BUILD PROPOSAL</p><h1>Set up your new proposal</h1><p>Choose the application structure first. Then the assistant will ask questions and draft your proposal in the conversation.</p></header>
      <section className="draft-card draft-selection" aria-label="Proposal setup">
        <label>Proposal name<input aria-label="Proposal name" value={proposalName} onChange={event => setProposalName(event.target.value)} maxLength={400} placeholder={`${profile?.org_name || "Your organization"} - Grant Proposal`} /></label>
        <label>Target grant (optional)<select aria-label="Target grant" value={selectedGrantId} disabled={starting || session.loading} onChange={event => {
          prefillRequest.current += 1;
          setSelectedGrant(event.target.value); setGrantDetails(null); setApplicationSpec(null); setPrefill(null); setPrefillError(""); setPrefilling(false);
        }}>
          <option value="">No target grant - general proposal</option>
          {grants.map(grant => <option key={grant.grant_id} value={grant.grant_id}>{grant.title}</option>)}
          {selectedGrantId && !grants.some(grant => String(grant.grant_id) === String(selectedGrantId)) && <option value={selectedGrantId}>{selectedGrant?.title || "Selected grant"}</option>}
        </select></label>
      </section>
      <section className="draft-card" aria-label="Automatic grant prefill"><h2>{prefilling ? "Reading the selected grant..." : "Application information"}</h2>
        <p>{selectedGrantId ? "We prefill only instructions present in the stored grant text. Review the excerpts and add any missing portal questions, limits, attachments or policies below." : "Choose a grant to prefill its available instructions, or leave it blank and use a general starter."}</p>
        {prefilling && <button type="button" onClick={() => { prefillRequest.current += 1; setPrefilling(false); }}>Enter requirements manually</button>}
        {prefill && <p role="status">Prefilled {prefill.application_spec?.sections?.length || 0} questions and {prefill.application_spec?.attachments?.length || 0} attachment entries. Missing information remains for you to confirm.</p>}
        {(prefill?.evidence || []).map((item, index) => <blockquote key={index}><strong>{item.field}</strong><p>{item.quote}</p></blockquote>)}
        {(prefill?.warnings || []).map((warning, index) => <p key={index}>{warning}</p>)}
        {prefillError && <p role="alert">{prefillError}</p>}
      </section>
      <ApplicationRequirementsEditor grant={selectedGrant} value={applicationSpec || emptyApplicationSpec()} onChange={setApplicationSpec} disabled={prefilling || starting || session.loading} collapsible={false} showPrefill={false} />
      <section className="draft-card"><h2>What happens next</h2><p>The assistant asks about your project or the funder's questions. You review your answers before drafting starts. The right-hand steps panel stays visible while the proposal is being written.</p></section>
      <div className="draft-start"><button type="button" className="il-primary" onClick={handleStart} disabled={prefilling || starting || session.loading || Boolean(session.data.running) || !aiPolicyCheck(applicationSpec).ai_drafting_allowed}>{starting ? "Starting..." : "Start building"}</button></div>
      {session.error && <p role="alert">{session.error}</p>}
      <AiPrivacyNotice />
    </main>
  </div>;

  return (
    <div style={{ height: "100vh", background: "var(--bg)",
      display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <Nav />

      {/* App bar */}
      <div style={{
        background: "#13131f", borderBottom: "1px solid #1e1e30",
        padding: "0 24px", height: 48,
        display: "flex", alignItems: "center", justifyContent: "space-between",
        gap: 12, flexShrink: 0,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <button onClick={() => navigate(-1)}
            style={{ background:"none",border:"none",color:"#555",
              fontSize:13,cursor:"pointer",padding:0 }}>←</button>
          {hasStarted ? (
            <input
              value={proposalName}
              onChange={e => setProposalName(e.target.value)}
              placeholder="Proposal name…"
              style={{
                background: "none", border: "none",
                borderBottom: "1px solid #2a2a4e",
                color: "#fff", fontWeight: 700, fontSize: 13,
                outline: "none", padding: "0 0 1px",
                minWidth: 120, maxWidth: 260,
              }}
              onFocus={e => e.target.style.borderBottomColor = "var(--accent)"}
              onBlur={e => e.target.style.borderBottomColor = "#2a2a4e"}
            />
          ) : (
            <span style={{ color:"#fff",fontWeight:700,fontSize:13 }}>
              {proposalName.trim() || "Build a Proposal"}
            </span>
          )}
          {totalSections > 0 && (
            <span style={{
              background: allApproved ? "#0d2e1a" : "#1a1a28",
              color: allApproved ? "var(--green)" : "#555",
              border: `1px solid ${allApproved ? "#166534" : "#2a2a3e"}`,
              borderRadius: 5, padding: "2px 9px", fontSize: 10, fontWeight: 700,
            }}>
              {approvedCount}/{totalSections} approved
            </span>
          )}
        </div>

        <div style={{ display:"flex", gap:8, alignItems:"center" }}>
          <span style={{ color: "#999", fontSize: 12 }}>{selectedGrant?.title || "General proposal"}</span>

          {(allApproved || (done && totalSections > 0)) && (
            <button onClick={handlePDF} disabled={pdfLoading || !applicationReport.can_finalize_text} style={{
              background: pdfLoading ? "#1a1a28" : "#e63946",
              border:"none", color:"#fff",
              padding:"6px 14px", borderRadius:7,
              fontSize:12, fontWeight:700, cursor:"pointer",
            }}>
              {pdfLoading ? "⟳ Generating…" : "↓ Download PDF"}
            </button>
          )}
        </div>
      </div>

      {/* Body — main content + fixed orchestration strip */}
      <div style={{
        flex: 1, minHeight: 0, display: "flex", overflow: "hidden",
        marginRight: showRightPanel ? ORCHESTRATION_PANEL_WIDTH : 0,
      }}>

        {/* ── Main panel: chat + sections ─────────────────── */}
        <div style={{
          flex: 1,
          width: showRightPanel ? undefined : "100%",
          minWidth: 0,
          minHeight: 0,
          display: "flex", flexDirection: "column",
          overflow: "hidden",
        }}>

          {/* Chat messages and proposal replies share one scroll area. */}
          <div data-testid="build-conversation" onScroll={event => {
            const node = event.currentTarget;
            followChatRef.current = node.scrollHeight - node.scrollTop - node.clientHeight < 100;
          }} style={{
            flex: 1,
            overflowY: "auto",
            padding: "24px 28px 16px",
            minHeight: 0,
          }}>

            {totalSections > 0 && <ApplicationReview spec={applicationSpec} sections={sections} onChange={setApplicationSpec} disabled={session.loading} onSave={saveApplicationChecklist} />}
            {totalSections > 0 && <ConsistencyReview review={coherenceReview} onCheck={handleCheckConsistency} checking={checkingConsistency} disabled={session.loading || !aiPolicyCheck(applicationSpec || selectedGrant?.application_spec).ai_drafting_allowed} />}

            {!hasStarted && !loading && !starting && !session.sessionId && !searchParams.get("session") && !searchParams.get("load") && <section className="draft-card"><p>No active build is selected.</p><button type="button" onClick={() => navigate("/build")}>Back to setup</button></section>}

            {/* Messages */}
            {messages.map((msg, i) => {
              if (msg.role === "ai") {
                const isDraft    = msg.type === "draft";
                const isComplete = msg.type === "complete";
                const isError    = msg.type === "error";

                return (
                  <div key={i} style={{ display:"flex", gap:10, marginBottom:18,
                    alignItems:"flex-start" }}>
                    <div style={{
                      width:30, height:30, borderRadius:"50%", flexShrink:0,
                      background:"var(--accent-dim)",
                      display:"flex", alignItems:"center", justifyContent:"center",
                      fontSize:13, fontWeight:800, color:"#fff", marginTop:2,
                    }}>✦</div>

                    <div style={{ flex:1, minWidth:0 }}>
                      {isDraft ? (
                        /* Instead of showing a chat bubble for drafts,
                           they appear in the right panel. Just show a compact notice. */
                        <div style={{
                          background:"#0d2e1a", border:"1px solid #166534",
                          borderRadius:8, padding:"8px 14px",
                          display:"flex", alignItems:"center", gap:8,
                        }}>
                          <span style={{ fontSize:14 }}>
                            {STEP_ICONS[msg.step-1] || "✦"}
                          </span>
                          <p style={{ margin:0, color:"var(--green)",
                            fontSize:12, fontWeight:600 }}>
                            {msg.title} drafted — ready to review in this conversation
                          </p>
                        </div>
                      ) : (
                        <div style={{
                          background: isComplete ? "#0d1a2e" :
                                      isError    ? "#2d0f0f" : "var(--bg-card)",
                          border: `1px solid ${
                            isComplete ? "#1e3a5f" :
                            isError    ? "#7f1d1d" : "var(--border)"
                          }`,
                          borderRadius:"4px 14px 14px 14px",
                          padding:"12px 16px",
                        }}>
                          {msg.type === "question" && (
                            <div style={{ display:"flex", alignItems:"center",
                              gap:6, marginBottom:8 }}>
                              <span style={{ fontSize:13 }}>
                                {STEP_ICONS[msg.step-1]}
                              </span>
                              <span style={{ color:"var(--accent)", fontSize:11,
                                fontWeight:700, textTransform:"uppercase",
                                letterSpacing:"0.06em" }}>
                                Step {msg.step} of {msg.total} — {msg.title}
                              </span>
                            </div>
                          )}
                          <p style={{
                            margin:0, color: isError ? "var(--red)" : "#d0d0e8",
                            fontSize:13, lineHeight:1.8, whiteSpace:"pre-wrap",
                          }}>
                            {msg.text}
                          </p>

                          {msg.type === "slot_confirm" && (
                            <div style={{ marginTop: 12, borderTop: "1px solid #1e3a5f", paddingTop: 12 }}>
                              <fieldset disabled={loading || Boolean(session.error) || session.gate !== "slot_confirm"} style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
                                {Object.entries(session.data.slots || {}).map(([k, s]) => (
                                  <label key={k} style={{ display: "block", marginBottom: 14, fontSize: 12, color: "#ddd" }}>
                                    {s.question || k.replace(/_/g, " ")}
                                    {!s.filled && <span style={{ display: "block", color: "#fbbf24", marginTop: 4 }}>Please add any missing details you have.</span>}
                                    <textarea rows={3} maxLength={20000} value={slotEdits[k] ?? s.value ?? ""}
                                      onChange={event => setSlotEdits(prev => ({ ...prev, [k]: event.target.value }))}
                                      style={{ display: "block", boxSizing: "border-box", width: "100%", marginTop: 6, padding: 10, borderRadius: 8, border: "1px solid var(--border)", background: "var(--bg-card)", color: "var(--text-primary)", font: "inherit", resize: "vertical" }} />
                                  </label>
                                ))}
                                <label style={{ display: "block", fontSize: 12, color: "#ddd" }}>
                                  Extra details or drafting instructions (optional)
                                  <textarea rows={3} maxLength={2000} value={draftInstructions}
                                    onChange={event => setDraftInstructions(event.target.value)}
                                    placeholder="Add context, corrections, or preferences for the draft."
                                    style={{ display: "block", boxSizing: "border-box", width: "100%", marginTop: 6, padding: 10, borderRadius: 8, border: "1px solid var(--border)", background: "var(--bg-card)", color: "var(--text-primary)", font: "inherit", resize: "vertical" }} />
                                </label>
                              </fieldset>
                              <button 
                                onClick={handleConfirmSlots}
                                disabled={loading || Boolean(session.error) || session.gate !== "slot_confirm"}
                                style={{ 
                                  marginTop: 14, background: "var(--accent)", border: "none", 
                                  color: "#fff", padding: "8px 16px", borderRadius: 8, 
                                  fontSize: 12, fontWeight: 700, cursor: "pointer", width: "100%" 
                                }}
                              >
                                Confirm & Start Drafting
                              </button>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              }

              // User message
              return (
                <div key={i} style={{
                  display:"flex", justifyContent:"flex-end",
                  marginBottom:18,
                }}>
                  <div style={{
                    maxWidth:"75%",
                    background:"var(--accent)",
                    borderRadius:"14px 4px 14px 14px",
                    padding:"10px 16px",
                  }}>
                    <p style={{ margin:0, color:"#fff", fontSize:13, lineHeight:1.7 }}>
                      {msg.text}
                    </p>
                  </div>
                </div>
              );
            })}

          {/* Proposal sections (main area) */}
          {Object.keys(liveSections).length > 0 && !["draft_review", "final_save", "complete"].includes(session.gate) && (
            <BuildDraftPreview sections={liveSections} interrupted={Boolean(session.error)} />
          )}
          {totalSections > 0 && (
            <div style={{
              marginTop: 24,
            }}>
              <div style={{ display:"flex", alignItems:"center",
                justifyContent:"space-between", marginBottom:16 }}>
                <p style={{ margin:0, fontWeight:700, color:"#fff", fontSize:14 }}>
                  {savedBuildId ? "Your Saved Proposal" : "Your Proposal Sections"}
                </p>
                <button onClick={handleFindGrants} disabled={findingGrants} style={{ background: "var(--accent)", color: "#fff", border: "none", padding: "8px 14px", borderRadius: 8, cursor: "pointer" }}>
                  {findingGrants ? "Preparing proposal..." : "Find grants"}
                </button>
                <p style={{ margin:0, color: allApproved ? "var(--green)" : "#555",
                  fontSize:12, fontWeight:600 }}>
                  {approvedCount}/{totalSections} approved
                </p>
              </div>

              <div style={{ height:4, background:"#1e1e30", borderRadius:2,
                marginBottom:20, overflow:"hidden" }}>
                <div style={{
                  height:"100%",
                  width: `${(approvedCount/totalSections)*100}%`,
                  background:"var(--accent)",
                  borderRadius:2,
                  transition:"width 0.4s",
                }} />
              </div>

              {session.gate === "draft_review" && !done && (
                <div style={{
                  marginBottom: 16, padding: "14px 16px",
                  background: "#1a1a2e", border: "1px solid var(--accent)",
                  borderRadius: 10, display: "flex",
                  alignItems: "center", justifyContent: "space-between", gap: 12,
                }}>
                  <p style={{ margin: 0, color: "#aaa", fontSize: 12, lineHeight: 1.5 }}>
                    Review the sections below, then confirm to continue.
                  </p>
                  <button
                    onClick={handleConfirmDraftReview}
                    disabled={session.loading || !applicationReport.can_finalize_text}
                    style={{
                      background: "var(--accent)", border: "none", color: "#fff",
                      padding: "8px 16px", borderRadius: 8, fontSize: 12,
                      fontWeight: 700, cursor: "pointer", whiteSpace: "nowrap",
                      opacity: session.loading ? 0.6 : 1,
                    }}
                  >
                    {session.loading ? "⟳ Saving…" : "Confirm Draft & Continue"}
                  </button>
                </div>
              )}

              {session.gate === "final_save" && !done && (
                <div style={{
                  marginBottom: 16, padding: "14px 16px",
                  background: "#0d2e1a", border: "1px solid #166534",
                  borderRadius: 10, display: "flex",
                  alignItems: "center", justifyContent: "space-between", gap: 12,
                }}>
                  <p style={{ margin: 0, color: "#2d5a3d", fontSize: 12, lineHeight: 1.5 }}>
                    Draft saved to session. Complete to reach the final graph node.
                  </p>
                  <button
                    onClick={handleCompleteSession}
                    disabled={session.loading || !applicationReport.can_finalize_text || aiPolicyCheck(applicationSpec).disclosure_pending}
                    style={{
                      background: "#166534", border: "none", color: "#fff",
                      padding: "8px 16px", borderRadius: 8, fontSize: 12,
                      fontWeight: 700, cursor: "pointer", whiteSpace: "nowrap",
                      opacity: session.loading ? 0.6 : 1,
                    }}
                  >
                    {session.loading ? "⟳ Finishing…" : "Complete Session"}
                  </button>
                </div>
              )}

              <div style={{ display:"flex", flexDirection:"column", gap:14 }}>
                {secOrder.map((key, idx) => {
                  const sec = sections[key];
                  if (!sec) return null;
                  return (
                    <DraftCard
                      key={key}
                      stepKey={key}
                      title={sec.title}
                      content={sec.content}
                      approved={sec.approved}
                      icon={STEP_ICONS[idx] || "✦"}
                      requirements={sectionRequirements(applicationSpec, key)}
                      applicationSpec={applicationSpec || selectedGrant?.application_spec}
                      onApprove={() => handleApprove(key)}
                      onRevise={(newContent) => handleRevise(key, newContent)}
                    />
                  );
                })}
              </div>

              {allApproved && (
                <div style={{
                  marginTop:20, background:"#0d2e1a",
                  border:"1px solid #166534", borderRadius:12,
                  padding:"20px 24px",
                  display:"flex", alignItems:"center", justifyContent:"space-between",
                }}>
                  <div>
                    <p style={{ margin:"0 0 3px", fontWeight:700,
                      color:"var(--green)", fontSize:15 }}>
                      ✓ All sections approved
                    </p>
                    <p style={{ margin:0, color:"#2d5a3d", fontSize:12 }}>
                      Your proposal is ready to download
                    </p>
                  </div>
                  <div style={{ display: "flex", gap: 12 }}>
                    <button onClick={handleFindGrants} disabled={findingGrants} style={{
                      background: "none",
                      border:"1px solid #2d5a3d", color:"var(--green)",
                      padding:"11px 22px", borderRadius:9,
                      fontSize:13, fontWeight:700, cursor:"pointer",
                    }}>
                      Find Grants →
                    </button>
                    <button onClick={handlePDF} disabled={pdfLoading} style={{
                      background: pdfLoading ? "#1a1a28" : "#e63946",
                      border:"none", color:"#fff",
                      padding:"11px 22px", borderRadius:9,
                      fontSize:13, fontWeight:700, cursor:"pointer",
                    }}>
                      {pdfLoading ? "⟳ Generating…" : "↓ Download PDF"}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}


            {/* Loading dots */}
            {loading && (
              <div style={{ display:"flex", gap:10, marginBottom:18,
                alignItems:"flex-start" }}>
                <div style={{
                  width:30, height:30, borderRadius:"50%", flexShrink:0,
                  background:"var(--accent-dim)",
                  display:"flex", alignItems:"center", justifyContent:"center",
                  fontSize:13, fontWeight:800, color:"#fff",
                }}>✦</div>
                <div style={{
                  background:"var(--bg-card)", border:"1px solid var(--border)",
                  borderRadius:"4px 14px 14px 14px", padding:"12px 16px",
                }}>
                  <TypingDots />
                  {session.progress && <p role="status" style={{ margin: "8px 0 0", fontSize: 12 }}>{session.progress}</p>}
                </div>
              </div>
            )}

            {buildSaveError && <p role="alert" style={{ color: "#ef4444" }}>{buildSaveError}</p>}
            {session.error && (
              <div role="alert" style={{ padding: 16, marginBottom: 16, border: "1px solid #ef4444", borderRadius: 10 }}>
                <p style={{ margin: "0 0 10px" }}>{session.error}</p>
                <button type="button" disabled={session.loading} onClick={session.sessionId ? session.refresh : () => navigate("/build")}>
                  Check saved session status
                </button>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          {/* Input bar */}
          {hasStarted && !done && (
            <div style={{
              padding:"12px 20px", borderTop:"1px solid var(--border)",
              display:"flex", gap:8, alignItems:"flex-end",
              background:"#0d0d16", flexShrink: 0,
            }}>
              <textarea
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => {
                  if (e.key==="Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
                }}
                placeholder={
                  session.gate === "slot_filling"
                    ? "Type your answer…"
                    : session.gate === "slot_confirm"
                    ? "Carefully review the extracted data above"
                    : session.loading
                    ? "Processing..."
                    : "Waiting…"
                }
                disabled={session.loading || session.gate !== "slot_filling"}
                rows={2}
                style={{
                  flex:1, background: "#111120",
                  border: "1px solid var(--border)", borderRadius: 10,
                  color: "#e0e0f0", padding: "10px 14px",
                  fontSize: 13, resize: "none", outline: "none",
                  fontFamily: "DM Sans, sans-serif",
                  opacity: session.loading || session.gate !== "slot_filling" ? 0.5 : 1,
                }}
              />
              <button
                onClick={handleSend}
                disabled={!input.trim() || session.loading || session.gate !== "slot_filling"}
                style={{
                  width:40, height:40, borderRadius:10, border:"none",
                  background: input.trim() && !session.loading && session.gate === "slot_filling"
                    ? "var(--accent)" : "#1e1e30",
                  color:"#fff", fontSize:18, cursor:"pointer",
                  display:"flex", alignItems:"center", justifyContent:"center",
                  flexShrink:0,
                }}
              >↑</button>
            </div>
          )}
        </div>
      </div>

      {/* ── Fixed right strip: stays visible while chat scrolls ── */}
      <div style={{ padding: "0 28px", flexShrink: 0, maxHeight: "35vh", overflowY: "auto", marginRight: showRightPanel ? ORCHESTRATION_PANEL_WIDTH : 0 }}><AiPrivacyNotice /></div>
      {showRightPanel && (
        <aside aria-label="Proposal building steps" style={{
          position: "fixed",
          right: 0,
          top: HEADER_HEIGHT,
          bottom: 0,
          width: ORCHESTRATION_PANEL_WIDTH,
          overflowY: "auto",
          padding: "16px 12px 24px",
          background: "#0c0c14",
          borderLeft: "1px solid #1a1a28",
          zIndex: 80,
        }}>
          <AgentOrchestrationPanel
            compact
            gate={session.gate}
            loading={loading}
            agentTrace={agentTrace}
            draftingPlan={draftingPlan}
          />
        </aside>
      )}
    </div>
  );
}
