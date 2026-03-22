import { useEffect, useState, useRef } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { Nav } from "../components";
import useGrants from "../hooks/useGrants";
import useDraft from "../hooks/useDraft";
import { useAuth } from "../context/AuthContext";
import useWorkStore from "../hooks/useWorkStore";
import api from "../services/api";

// Loads jsPDF from CDN once via a script tag
function loadJsPDF() {
  return new Promise((resolve, reject) => {
    if (window.jspdf) return resolve();
    const script = document.createElement("script");
    script.src = "https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js";
    script.onload = resolve;
    script.onerror = reject;
    document.head.appendChild(script);
  });
}

const SECTION_ICONS = {
  executive_summary:       "01",
  problem_statement:       "02",
  proposed_solution:       "03",
  target_beneficiaries:    "04",
  organizational_capacity: "05",
  evaluation_plan:         "06",
  budget_narrative:        "07",
  sustainability:          "08",
};

// ── Formatting toolbar actions ─────────────────────────
function applyFormat(textarea, format) {
  if (!textarea) return null;
  const start = textarea.selectionStart;
  const end   = textarea.selectionEnd;
  const sel   = textarea.value.slice(start, end);
  const pre   = textarea.value.slice(0, start);
  const post  = textarea.value.slice(end);

  let newText = textarea.value;
  let newCursorStart = start;
  let newCursorEnd   = end;

  if (format === "bold") {
    newText = pre + `**${sel}**` + post;
    newCursorEnd = end + 4;
  } else if (format === "bullet") {
    const lines = sel.split("\n").map(l => `• ${l}`).join("\n");
    newText = pre + lines + post;
    newCursorEnd = start + lines.length;
  } else if (format === "h2") {
    newText = pre + `\n## ${sel}\n` + post;
    newCursorEnd = start + sel.length + 5;
  }
  return { newText, newCursorStart, newCursorEnd };
}

export default function Draft() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const grantId = searchParams.get("grant");

  const { profile } = useAuth();
  const { grants, proposal } = useGrants();
  const { draft, load, sections, sectionOrder, activeSection, loading, done, error, reset } = useDraft();
  const { saveDraft, updateDraft, drafts, proposals } = useWorkStore();
  const [savedDraftId, setSavedDraftId] = useState(null);
  const [saveStatus,   setSaveStatus]   = useState(null); // "saved" | "error" | null

  const [selectedGrantId,   setSelectedGrantId]   = useState(grantId || "");
  const [selectedProposalId, setSelectedProposalId] = useState("");
  const [activeTab,       setActiveTab]       = useState(null);
  const [editedContent,   setEditedContent]   = useState({});
  const [wordCounts,      setWordCounts]      = useState({});
  const [pdfLoading,      setPdfLoading]      = useState(false);
  const [draftScore,      setDraftScore]      = useState(null);   // rescored after draft completes
  const [rescoring,       setRescoring]       = useState(false);  // spinner while scoring

  const textareaRef = useRef(null);
  const selectedGrant    = grants.find(g => String(g.grant_id) === String(selectedGrantId));
  // Active saved proposal (uploaded or built) — provides proposal_context for drafting
  const activeProposal   = proposals.find(p => p.id === selectedProposalId);
  // Resolved proposal: prefer saved proposal_context, fall back to sessionStorage proposal
  const resolvedProposal = activeProposal?.proposal_context
    || proposal
    || null;

  // Auto-select most recent proposal if none selected
  useEffect(() => {
    if (!selectedProposalId && proposals.length > 0) {
      const storedId = sessionStorage.getItem("upload_draft_id");
      if (storedId && proposals.find(p => p.id === storedId)) {
        setSelectedProposalId(storedId);
      } else {
        setSelectedProposalId(proposals[0].id);
      }
    }
  }, [proposals, selectedProposalId]);

  useEffect(() => { if (grantId) setSelectedGrantId(grantId); }, [grantId]);



  // Load saved draft if ?load=<id> is in URL
  const loadId = searchParams.get("load");
  useEffect(() => {
    if (!loadId || !drafts.length) return;
    const saved = drafts.find(d => d.id === loadId);
    if (!saved) return;
    const restoredSections = saved.sections || {};
    const restoredOrder    = saved.section_order || Object.keys(restoredSections);
    // Restore grant + save ID
    if (saved.grant_id) setSelectedGrantId(saved.grant_id);
    setSavedDraftId(saved.id);
    // Populate useDraft state so editor panels render immediately (done=true)
    load(restoredSections, restoredOrder);
    // Also seed editedContent so edits work from the start
    const ec = {};
    const wc = {};
    restoredOrder.forEach(key => {
      if (restoredSections[key]) {
        ec[key] = restoredSections[key].content || "";
        wc[key] = (restoredSections[key].content || "").trim().split(/\s+/).filter(Boolean).length;
      }
    });
    setEditedContent(ec);
    setWordCounts(wc);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadId, drafts]);

  useEffect(() => {
    if (sectionOrder.length > 0 && !activeTab) setActiveTab(sectionOrder[0]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sectionOrder]);

  useEffect(() => {
    if (activeSection) setActiveTab(activeSection);
  }, [activeSection]);

  // Auto-save draft when streaming finishes
  useEffect(() => {
    if (done && sectionOrder.length > 0) {
      if (profile) handleSave();
      // Rescore the draft against the specific grant
      if (selectedGrant && sections && Object.keys(sections).length > 0) {
        runRescore(sections, selectedGrant);
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [done]);

  useEffect(() => {
    sectionOrder.forEach(key => {
      if (!editedContent[key] && sections[key]) {
        setEditedContent(prev => ({ ...prev, [key]: sections[key].content }));
        setWordCounts(prev => ({ ...prev, [key]: sections[key].content.trim().split(/\s+/).length }));
      }
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sectionOrder, sections]);

  const handleEdit = (key, value) => {
    setEditedContent(prev => ({ ...prev, [key]: value }));
    setWordCounts(prev => ({ ...prev, [key]: value.trim().split(/\s+/).filter(Boolean).length }));
  };

  const handleFormat = (format) => {
    const ta = textareaRef.current;
    if (!ta || !activeTab) return;
    const result = applyFormat(ta, format);
    if (!result) return;
    handleEdit(activeTab, result.newText);
    setTimeout(() => {
      ta.selectionStart = result.newCursorStart;
      ta.selectionEnd   = result.newCursorEnd;
      ta.focus();
    }, 0);
  };


  // ── Rescore after draft completes ──────────────────────────────────────
  // The draft was written specifically for selectedGrant, so we score the
  // drafted text *against* that grant to reflect tailoring, not just the
  // raw proposal.
  const runRescore = async (draftedSections, grant) => {
    if (!grant || !draftedSections || Object.keys(draftedSections).length === 0) return;
    setRescoring(true);
    try {
      // Build a combined proposal object merging original context + drafted text
      const draftText = Object.values(draftedSections)
        .map(s => s.content || "").join("\n\n");
      const scoringPayload = {
        ...resolvedProposal,
        drafted_text:    draftText,
        target_grant:    grant.title,
        target_agency:   grant.agency,
        grant_focus:     grant.focus_areas || "",
        grant_ceiling:   grant.award_ceiling || 0,
        application_tip: grant.application_tip || "",
      };
      const res = await api.post("/api/score", { proposal: scoringPayload });
      const s = res.data?.scoring || res.data;
      setDraftScore({
        overall:         s.overall_score      || 0,
        clarity:         s.clarity_score      || 0,
        impact:          s.impact_score       || 0,
        budget:          s.budget_score       || 0,
        locality:        s.locality_alignment || 0,
        funder_readiness: s.funder_readiness  || "moderate",
        strengths:       s.strengths          || [],
        weaknesses:      s.weaknesses         || [],
        recommendations: s.recommendations    || [],
      });
    } catch (e) {
      console.error("Rescore failed:", e);
    } finally {
      setRescoring(false);
    }
  };

  const handleDraft = () => {
    if (!resolvedProposal || !selectedGrant) return;
    setEditedContent({});
    setActiveTab(null);
    setSavedDraftId(null);
    setSaveStatus(null);
    setDraftScore(null);
    reset();
    draft(resolvedProposal, selectedGrant);
  };

  // Save current draft to store
  const handleSave = async (currentSections) => {
    if (!profile || !selectedGrant) return;
    try {
      const secToSave = {};
      sectionOrder.forEach(key => {
        secToSave[key] = {
          title:   sections[key]?.title   || key,
          content: currentSections?.[key] ?? editedContent[key] ?? sections[key]?.content ?? "",
        };
      });
      if (savedDraftId) {
        await updateDraft(savedDraftId, secToSave);
      } else {
        const matchIds = (activeProposal?.matches_id || []);
        const saved = await saveDraft({
          title:            selectedGrant.title,
          grant_title:      selectedGrant.title,
          grant_id:         String(selectedGrant.grant_id),
          agency:           selectedGrant.agency || "",
          proposal_context: resolvedProposal || {},
          matches_id:       matchIds,
          sections:         secToSave,
          section_order:    sectionOrder,
        });
        if (saved) setSavedDraftId(saved.id);
      }
      setSaveStatus("saved");
      setTimeout(() => setSaveStatus(null), 2500);
    } catch (e) {
      setSaveStatus("error");
    }
  };

  const handleDownloadPDF = async () => {
    if (!sectionOrder.length) return;
    setPdfLoading(true);
    try {
      // Dynamically load jsPDF
      // Load jsPDF via script tag (CRA doesn't support dynamic CDN ES module imports)
      await loadJsPDF();
      const { jsPDF } = window.jspdf;
      const doc = new jsPDF({ unit: "pt", format: "letter" });

      const marginLeft  = 72;
      const marginRight = 72;
      const pageWidth   = doc.internal.pageSize.getWidth();
      const pageHeight  = doc.internal.pageSize.getHeight();
      const contentW    = pageWidth - marginLeft - marginRight;
      let y = 80;

      const addPage = () => { doc.addPage(); y = 72; };

      const checkY = (needed = 20) => { if (y + needed > pageHeight - 60) addPage(); };

      // Cover header
      doc.setFillColor(18, 18, 32);
      doc.rect(0, 0, pageWidth, 56, "F");
      doc.setTextColor(124, 111, 239);
      doc.setFontSize(10);
      doc.setFont("helvetica", "bold");
      doc.text("IMPACTLINK AI  —  GRANT PROPOSAL", marginLeft, 34);
      doc.setTextColor(136, 136, 136);
      doc.text(new Date().toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" }), pageWidth - marginRight, 34, { align: "right" });

      y = 100;

      // Title block
      doc.setTextColor(20, 20, 35);
      doc.setFontSize(22);
      doc.setFont("helvetica", "bold");
      const titleLines = doc.splitTextToSize(selectedGrant?.title || "Grant Proposal", contentW);
      doc.text(titleLines, marginLeft, y);
      y += titleLines.length * 28 + 8;

      doc.setFontSize(11);
      doc.setFont("helvetica", "normal");
      doc.setTextColor(100, 100, 120);
      doc.text(`${selectedGrant?.agency || ""}  ·  ${proposal?.organization_name || ""}`, marginLeft, y);
      y += 12;

      // Divider
      doc.setDrawColor(200, 200, 220);
      doc.setLineWidth(0.5);
      doc.line(marginLeft, y, pageWidth - marginRight, y);
      y += 28;

      // Sections
      for (const key of sectionOrder) {
        const sec     = sections[key];
        const content = editedContent[key] || sec?.content || "";
        if (!sec) continue;

        checkY(60);

        // Section label pill
        doc.setFillColor(240, 240, 255);
        doc.roundedRect(marginLeft, y - 12, contentW, 22, 4, 4, "F");
        doc.setFontSize(9);
        doc.setFont("helvetica", "bold");
        doc.setTextColor(100, 90, 200);
        doc.text(`${SECTION_ICONS[key]}  ${sec.title.toUpperCase()}`, marginLeft + 10, y + 3);
        y += 28;

        // Body text
        doc.setFontSize(10.5);
        doc.setFont("helvetica", "normal");
        doc.setTextColor(40, 40, 60);

        // Strip markdown bold markers for clean PDF
        const cleanContent = content.replace(/\*\*(.*?)\*\*/g, "$1").replace(/^## (.+)$/gm, "$1");
        const paragraphs = cleanContent.split(/\n{2,}/);

        for (const para of paragraphs) {
          if (!para.trim()) continue;
          const lines = doc.splitTextToSize(para.trim(), contentW);
          checkY(lines.length * 14 + 8);
          doc.text(lines, marginLeft, y);
          y += lines.length * 14 + 10;
        }

        y += 16;

        // Section divider
        checkY(10);
        doc.setDrawColor(230, 230, 245);
        doc.setLineWidth(0.3);
        doc.line(marginLeft, y, pageWidth - marginRight, y);
        y += 20;
      }

      // Footer on every page
      const totalPages = doc.internal.getNumberOfPages();
      for (let i = 1; i <= totalPages; i++) {
        doc.setPage(i);
        doc.setFillColor(18, 18, 32);
        doc.rect(0, pageHeight - 36, pageWidth, 36, "F");
        doc.setFontSize(8);
        doc.setTextColor(80, 80, 100);
        doc.setFont("helvetica", "normal");
        doc.text("Generated by ImpactLink AI", marginLeft, pageHeight - 16);
        doc.text(`Page ${i} of ${totalPages}`, pageWidth - marginRight, pageHeight - 16, { align: "right" });
      }

      const orgSlug = (proposal?.organization_name || "proposal").replace(/\s+/g, "_").toLowerCase();
      doc.save(`${orgSlug}_grant_proposal.pdf`);
    } catch (err) {
      console.error("PDF error:", err);
      alert("PDF generation failed. Check console for details.");
    } finally {
      setPdfLoading(false);
    }
  };

  const totalWords  = Object.values(wordCounts).reduce((a, b) => a + b, 0);
  const hasSections = sectionOrder.length > 0;
  const activeContentValue = activeTab ? (editedContent[activeTab] ?? sections[activeTab]?.content ?? "") : "";
  const currentIndex = sectionOrder.indexOf(activeTab);

  return (
    <div style={{ minHeight: "100vh", background: "#1e1e2e", display: "flex", flexDirection: "column" }}>
      <Nav />

      {/* ── App Bar ─────────────────────────────────────── */}
      <div style={{
        background: "#13131f", borderBottom: "1px solid #2a2a3e",
        padding: "0 20px", height: 48,
        display: "flex", alignItems: "center", justifyContent: "space-between",
        position: "sticky", top: 64, zIndex: 90, gap: 12,
      }}>
        {/* Left: title */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
          <button onClick={() => navigate(-1)} style={{ background: "none", border: "none", color: "#555", fontSize: 13, cursor: "pointer", padding: 0, flexShrink: 0 }}>←</button>
          <span style={{ color: "#fff", fontWeight: 700, fontSize: 13, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 320 }}>
            {selectedGrant ? selectedGrant.title : "New Proposal"}
          </span>
          {selectedGrant && (
            <span style={{ background: "#1e1e30",
              color: draftScore ? (draftScore.overall >= 70 ? "var(--green)" : draftScore.overall >= 45 ? "var(--accent)" : "var(--red)") : "var(--accent)",
              border: "1px solid #2e2e4e", borderRadius: 5, padding: "2px 8px", fontSize: 10, fontWeight: 700, flexShrink: 0,
              transition: "color 0.3s",
            }}>
              {rescoring ? "Scoring…" : draftScore ? `${draftScore.overall}% draft score` : `${selectedGrant.similarity_score}% match`}
            </span>
          )}
        </div>

        {/* Right: actions */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
          {hasSections && (
            <span style={{ color: "#444", fontSize: 11, marginRight: 4 }}>
              {totalWords.toLocaleString()} words
            </span>
          )}
          {savedDraftId && !done && (
            <span style={{ color: "#444", fontSize: 11, fontWeight: 600,
              background: "#1a1a28", border: "1px solid #2a2a3e",
              borderRadius: 5, padding: "2px 8px" }}>
              ✎ Editing saved
            </span>
          )}
          {done && (
            <>
              {saveStatus === "saved" && (
                <span style={{ color: "var(--green)", fontSize: 11, fontWeight: 600 }}>✓ Saved</span>
              )}
              {saveStatus === "error" && (
                <span style={{ color: "var(--red)", fontSize: 11 }}>Save failed</span>
              )}
              <button
                onClick={() => handleSave()}
                style={{
                  background: "#1a1a28", border: "1px solid #2a2a3e",
                  color: "#888", padding: "6px 13px", borderRadius: 7,
                  fontSize: 12, fontWeight: 600, cursor: "pointer",
                }}
              >
                💾 Save
              </button>
              <button
                onClick={handleDownloadPDF}
                disabled={pdfLoading}
                style={{
                  background: pdfLoading ? "#1a1a2e" : "#e63946",
                  border: "none", color: "#fff",
                  padding: "6px 14px", borderRadius: 7,
                  fontSize: 12, fontWeight: 700, cursor: pdfLoading ? "wait" : "pointer",
                  display: "flex", alignItems: "center", gap: 6,
                }}
              >
                {pdfLoading ? "⟳ Generating..." : "↓ Download PDF"}
              </button>
            </>
          )}
          <button
            onClick={handleDraft}
            disabled={!selectedGrant || !resolvedProposal || loading}
            style={{
              background: selectedGrant && resolvedProposal && !loading ? "var(--accent)" : "#1a1a2e",
              border: "none",
              color: selectedGrant && resolvedProposal && !loading ? "#fff" : "#444",
              padding: "6px 14px", borderRadius: 7,
              fontSize: 12, fontWeight: 700,
              cursor: selectedGrant && resolvedProposal && !loading ? "pointer" : "not-allowed",
            }}
          >
            {loading ? "Writing…" : hasSections ? "↺ Redraft" : "✦ Draft"}
          </button>
        </div>
      </div>

      {/* ── Body ────────────────────────────────────────── */}
      <div style={{ display: "flex", flex: 1 }}>

        {/* Left panel — sections list */}
        <div style={{
          width: 210, flexShrink: 0, background: "#0f0f1a",
          borderRight: "1px solid #1e1e2e",
          display: "flex", flexDirection: "column",
          position: "sticky", top: 112, height: "calc(100vh - 112px)", overflowY: "auto",
        }}>
          {/* Saved Proposal selector */}
          <div style={{ padding: "14px 14px 10px", borderBottom: "1px solid #1e1e2e" }}>
            <p style={{ color: "#333", fontSize: 9, fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.1em", margin: "0 0 7px" }}>Proposal</p>
            <select
              value={selectedProposalId}
              onChange={e => {
                setSelectedProposalId(e.target.value);
                sessionStorage.setItem("upload_draft_id", e.target.value);
              }}
              style={{
                width: "100%", background: "#1a1a28", border: "1px solid #2a2a3e",
                color: selectedProposalId ? "#ddd" : "#444",
                padding: "7px 8px", borderRadius: 6,
                fontSize: 11, cursor: "pointer", outline: "none",
              }}
            >
              <option value="">From sessionStorage…</option>
              {proposals.map(p => (
                <option key={p.id} value={p.id}>
                  {p._type === "build" ? "✦ " : "✍ "}
                  {p.title.length > 30 ? p.title.slice(0, 30) + "…" : p.title}
                </option>
              ))}
            </select>
            {activeProposal && (
              <p style={{ color: "#444", fontSize: 9, margin: "4px 0 0", lineHeight: 1.5 }}>
                {activeProposal.proposal_context?.organization_name || ""}
                {activeProposal.matches_id?.length
                  ? ` · ${activeProposal.matches_id.length} matches`
                  : ""}
              </p>
            )}
          </div>

          {/* Grant picker */}
          <div style={{ padding: "14px 14px 10px", borderBottom: "1px solid #1e1e2e" }}>
            <p style={{ color: "#333", fontSize: 9, fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.1em", margin: "0 0 7px" }}>Grant</p>
            <select
              value={selectedGrantId}
              onChange={e => { setSelectedGrantId(e.target.value); reset(); setEditedContent({}); setActiveTab(null); }}
              style={{
                width: "100%", background: "#1a1a28", border: "1px solid #2a2a3e",
                color: selectedGrantId ? "#ddd" : "#444",
                padding: "7px 8px", borderRadius: 6,
                fontSize: 11, cursor: "pointer", outline: "none",
              }}
            >
              <option value="">Choose grant…</option>
              {grants.map(g => (
                <option key={g.grant_id} value={g.grant_id}>
                  {g.title.length > 36 ? g.title.slice(0, 36) + "…" : g.title}
                </option>
              ))}
            </select>
          </div>

          {/* Section list */}
          <div style={{ padding: "10px 8px", flex: 1 }}>
            {!hasSections && !loading && (
              <p style={{ color: "#2a2a3e", fontSize: 11, padding: "16px 8px", lineHeight: 1.6 }}>
                {selectedGrant && proposal ? 'Click "Draft" to begin' : "Select a grant above"}
              </p>
            )}
            {loading && !hasSections && (
              <p style={{ color: "var(--accent)", fontSize: 11, padding: "16px 8px" }}>⟳ Writing…</p>
            )}
            {sectionOrder.map(key => (
              <div
                key={key}
                onClick={() => setActiveTab(key)}
                style={{
                  display: "flex", alignItems: "center", gap: 9,
                  padding: "8px 10px", borderRadius: 7, cursor: "pointer",
                  background: activeTab === key ? "#1e1e30" : "transparent",
                  borderLeft: activeTab === key ? "2px solid var(--accent)" : "2px solid transparent",
                  marginBottom: 1, transition: "all 0.12s",
                }}
              >
                <span style={{ fontSize: 9, fontWeight: 800, color: activeTab === key ? "var(--accent)" : "#333", fontFamily: "monospace", flexShrink: 0 }}>
                  {activeSection === key ? "⟳" : SECTION_ICONS[key]}
                </span>
                <div style={{ minWidth: 0 }}>
                  <p style={{ fontSize: 11, fontWeight: activeTab === key ? 700 : 400, color: activeTab === key ? "#e0e0f0" : "#555", margin: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {sections[key]?.title}
                  </p>
                  {wordCounts[key] && <p style={{ fontSize: 9, color: "#333", margin: 0 }}>{wordCounts[key]}w</p>}
                </div>
              </div>
            ))}
            {loading && hasSections && (
              <div style={{ display: "flex", alignItems: "center", gap: 9, padding: "8px 10px" }}>
                <span style={{ fontSize: 9, color: "var(--accent)" }}>⟳</span>
                <p style={{ fontSize: 11, color: "var(--accent)", margin: 0 }}>Writing…</p>
              </div>
            )}
          </div>

          {done && (
            <div style={{ padding: "10px 14px", borderTop: "1px solid #1e1e2e" }}>
              <div style={{ background: "#0d2e1a", borderRadius: 7, padding: "8px 10px" }}>
                <p style={{ color: "var(--green)", fontSize: 10, fontWeight: 700, margin: "0 0 1px" }}>✓ Complete</p>
                <p style={{ color: "#2d5a3d", fontSize: 10, margin: 0 }}>{totalWords.toLocaleString()} words</p>
              </div>
            </div>
          )}
        </div>

        {/* Center — Word-like editor */}
        <div style={{ flex: 1, background: "#2a2a3a", overflowY: "auto", display: "flex", flexDirection: "column", alignItems: "center", padding: "32px 0 80px" }}>

          {/* Formatting toolbar */}
          {activeTab && sections[activeTab] && (
            <div style={{
              width: 760, marginBottom: 8,
              background: "#13131f", border: "1px solid #2a2a3e",
              borderRadius: 8, padding: "6px 12px",
              display: "flex", alignItems: "center", gap: 2,
            }}>
              {[
                { label: "B", title: "Bold",   fmt: "bold",   style: { fontWeight: 900 } },
                { label: "H2", title: "Heading", fmt: "h2",   style: { fontSize: 10 } },
                { label: "• List", title: "Bullet list", fmt: "bullet", style: {} },
              ].map(btn => (
                <button
                  key={btn.fmt}
                  title={btn.title}
                  onMouseDown={e => { e.preventDefault(); handleFormat(btn.fmt); }}
                  style={{
                    background: "none", border: "none",
                    color: "#888", padding: "4px 10px", borderRadius: 5,
                    fontSize: 12, cursor: "pointer", fontFamily: "monospace",
                    ...btn.style,
                  }}
                  onMouseEnter={e => e.target.style.background = "#1e1e2e"}
                  onMouseLeave={e => e.target.style.background = "none"}
                >
                  {btn.label}
                </button>
              ))}
              <div style={{ width: 1, height: 16, background: "#2a2a3e", margin: "0 4px" }} />
              <button
                onClick={() => navigator.clipboard.writeText(activeContentValue)}
                style={{ background: "none", border: "none", color: "#555", padding: "4px 10px", borderRadius: 5, fontSize: 11, cursor: "pointer" }}
                onMouseEnter={e => e.target.style.background = "#1e1e2e"}
                onMouseLeave={e => e.target.style.background = "none"}
              >
                Copy section
              </button>
              <span style={{ marginLeft: "auto", color: "#333", fontSize: 10 }}>
                {wordCounts[activeTab] || 0} words
              </span>
            </div>
          )}

          {/* Empty state */}
          {!hasSections && !loading && (
            <div style={{ width: 760, background: "#fff", borderRadius: 2, padding: "100px 80px", textAlign: "center", boxShadow: "0 4px 32px rgba(0,0,0,0.4)" }}>
              <p style={{ fontSize: 40, marginBottom: 16 }}>✍</p>
              <p style={{ fontWeight: 800, color: "#1a1a2e", fontSize: 22, marginBottom: 8 }}>
                {!resolvedProposal ? "Upload or select a saved proposal" : !selectedGrant ? "Select a grant to begin" : "Ready to draft"}
              </p>
              <p style={{ color: "#888", fontSize: 14, maxWidth: 340, margin: "0 auto 24px" }}>
                {!resolvedProposal ? "Go to Upload to parse your proposal, or pick a saved one below." : "Choose a target grant from the left panel and click Draft."}
              </p>
              {!proposal && (
                <button onClick={() => navigate("/upload")} style={{ background: "#7c6fef", border: "none", color: "#fff", padding: "12px 28px", borderRadius: 8, fontSize: 14, fontWeight: 700, cursor: "pointer" }}>
                  Upload Proposal
                </button>
              )}
            </div>
          )}

          {loading && !hasSections && (
            <div style={{ width: 760, background: "#fff", borderRadius: 2, padding: "80px", textAlign: "center", boxShadow: "0 4px 32px rgba(0,0,0,0.4)" }}>
              <p style={{ color: "#7c6fef", fontSize: 16, fontWeight: 700 }}>⟳ Drafting your proposal…</p>
              <p style={{ color: "#bbb", fontSize: 13, marginTop: 8 }}>Sections will appear as they're written</p>
            </div>
          )}

          {/* The Document — white page */}
          {hasSections && activeTab && sections[activeTab] && (
            <div style={{
              width: 760,
              background: "#ffffff",
              borderRadius: 2,
              boxShadow: "0 4px 40px rgba(0,0,0,0.5)",
              overflow: "hidden",
            }}>
              {/* Document header strip */}
              <div style={{ background: "#13131f", padding: "14px 56px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div>
                  <p style={{ color: "#7c6fef", fontSize: 10, fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.1em", margin: "0 0 3px" }}>Grant Proposal</p>
                  <p style={{ color: "#fff", fontWeight: 700, fontSize: 14, margin: 0 }}>{selectedGrant?.title || "Proposal"}</p>
                </div>
                <div style={{ textAlign: "right" }}>
                  <p style={{ color: "#555", fontSize: 10, margin: "0 0 2px" }}>{selectedGrant?.agency}</p>
                  <p style={{ color: "#333", fontSize: 10, margin: 0 }}>{new Date().toLocaleDateString()}</p>
                </div>
              </div>

              {/* Section header */}
              <div style={{ padding: "32px 56px 0" }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 14, marginBottom: 20 }}>
                  <span style={{ fontSize: 11, fontWeight: 900, color: "#c8c5f8", fontFamily: "monospace", letterSpacing: "0.05em" }}>
                    {SECTION_ICONS[activeTab]}
                  </span>
                  <h2 style={{ fontSize: 18, fontWeight: 800, color: "#1a1a2e", margin: 0, letterSpacing: "-0.02em", fontFamily: "Georgia, serif" }}>
                    {sections[activeTab].title}
                  </h2>
                </div>
                <div style={{ height: 1, background: "#e8e8f4", marginBottom: 28 }} />
              </div>

              {/* Editable content */}
              <div style={{ padding: "0 56px 48px" }}>
                <textarea
                  ref={textareaRef}
                  value={activeContentValue}
                  onChange={e => handleEdit(activeTab, e.target.value)}
                  spellCheck
                  style={{
                    width: "100%", minHeight: 420,
                    border: "none", outline: "none",
                    resize: "none", background: "transparent",
                    fontFamily: "Georgia, 'Times New Roman', serif",
                    fontSize: 14, lineHeight: 2,
                    color: "#1a1a2e",
                    caretColor: "#7c6fef",
                    boxSizing: "border-box",
                  }}
                  placeholder="Content will appear here once drafted…"
                />
              </div>

              {/* Page footer */}
              <div style={{ background: "#f8f8fc", borderTop: "1px solid #eeeef8", padding: "10px 56px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <button
                  disabled={currentIndex <= 0}
                  onClick={() => setActiveTab(sectionOrder[currentIndex - 1])}
                  style={{ background: "none", border: "none", color: currentIndex > 0 ? "#7c6fef" : "#ccc", fontSize: 12, cursor: currentIndex > 0 ? "pointer" : "default", fontWeight: 600, padding: 0 }}
                >
                  ← {currentIndex > 0 ? sections[sectionOrder[currentIndex - 1]]?.title : ""}
                </button>
                <span style={{ color: "#bbb", fontSize: 11 }}>
                  {currentIndex + 1} / {sectionOrder.length}
                </span>
                <button
                  disabled={currentIndex >= sectionOrder.length - 1}
                  onClick={() => setActiveTab(sectionOrder[currentIndex + 1])}
                  style={{ background: "none", border: "none", color: currentIndex < sectionOrder.length - 1 ? "#7c6fef" : "#ccc", fontSize: 12, cursor: currentIndex < sectionOrder.length - 1 ? "pointer" : "default", fontWeight: 600, padding: 0 }}
                >
                  {currentIndex < sectionOrder.length - 1 ? sections[sectionOrder[currentIndex + 1]]?.title : ""} →
                </button>
              </div>
            </div>
          )}

          {/* Writing next section indicator */}
          {loading && hasSections && (
            <div style={{ width: 760, marginTop: 12, background: "#13131f", border: "1px dashed #2a2a4e", borderRadius: 8, padding: "16px 24px", display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ color: "var(--accent)", fontSize: 16 }}>⟳</span>
              <p style={{ color: "var(--accent)", fontSize: 13, margin: 0, fontWeight: 600 }}>Writing next section…</p>
            </div>
          )}

          {/* Done banner */}
          {done && (
            <div style={{
              width: 760, marginTop: 16,
              background: "#0d2e1a", border: "1px solid #166534",
              borderRadius: 8, padding: "16px 24px",
              display: "flex", alignItems: "center", justifyContent: "space-between",
            }}>
              <div>
                <p style={{ fontWeight: 700, color: "var(--green)", fontSize: 14, margin: "0 0 2px" }}>✓ All {sectionOrder.length} sections complete</p>
                <p style={{ color: "#2d5a3d", fontSize: 12, margin: 0 }}>Tailored for {selectedGrant?.agency} · {totalWords.toLocaleString()} words</p>
              </div>
              <button
                onClick={handleDownloadPDF}
                disabled={pdfLoading}
                style={{ background: "#e63946", border: "none", color: "#fff", padding: "10px 20px", borderRadius: 8, fontSize: 13, fontWeight: 700, cursor: "pointer" }}
              >
                {pdfLoading ? "⟳ Generating…" : "↓ Download PDF"}
              </button>
            </div>
          )}

          {error && (
            <div style={{ width: 760, marginTop: 12, background: "#2d0f0f", border: "1px solid #7f1d1d", borderRadius: 8, padding: "14px 20px", color: "var(--red)", fontSize: 13 }}>
              ⚠ {error}
            </div>
          )}
        </div>

        {/* Right panel — funder context */}
        {selectedGrant && (
          <div style={{
            width: 200, flexShrink: 0, background: "#0f0f1a",
            borderLeft: "1px solid #1e1e2e", padding: "16px 14px",
            position: "sticky", top: 112, height: "calc(100vh - 112px)", overflowY: "auto",
          }}>
            <p style={{ color: "#2a2a3e", fontSize: 9, fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.1em", margin: "0 0 10px" }}>Funder</p>
            <p style={{ color: "var(--accent)", fontWeight: 700, fontSize: 12, margin: "0 0 3px" }}>{selectedGrant.agency}</p>
            <p style={{ color: "#444", fontSize: 11, margin: "0 0 10px", lineHeight: 1.5 }}>
              {selectedGrant.title.slice(0, 70)}{selectedGrant.title.length > 70 ? "…" : ""}
            </p>

            <div style={{ background: "#1a1a28", borderRadius: 6, padding: "8px 10px", marginBottom: 12 }}>
              <p style={{ color: "#444", fontSize: 9, fontWeight: 700, textTransform: "uppercase", margin: "0 0 3px" }}>
                {draftScore ? "Draft Score" : "Match"}
              </p>
              {rescoring ? (
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <div style={{ width: 14, height: 14, border: "2px solid #2a2a4e",
                    borderTop: "2px solid var(--accent)", borderRadius: "50%",
                    animation: "spin 0.8s linear infinite" }} />
                  <span style={{ color: "#555", fontSize: 11 }}>Scoring…</span>
                  <style>{"@keyframes spin{to{transform:rotate(360deg)}}"}</style>
                </div>
              ) : draftScore ? (
                <>
                  <p style={{ color: draftScore.overall >= 70 ? "var(--green)" : draftScore.overall >= 45 ? "var(--accent)" : "var(--red)",
                    fontWeight: 800, fontSize: 22, margin: "0 0 4px", letterSpacing: "-0.02em" }}>
                    {draftScore.overall}<span style={{ fontSize: 12, fontWeight: 400 }}>%</span>
                  </p>
                  <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                    {[
                      ["Clarity",  draftScore.clarity],
                      ["Impact",   draftScore.impact],
                      ["Budget",   draftScore.budget],
                      ["Locality", draftScore.locality],
                    ].map(([label, val]) => (
                      <div key={label} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                        <span style={{ color: "#333355", fontSize: 9, width: 42 }}>{label}</span>
                        <div style={{ flex: 1, height: 3, background: "#2a2a4e", borderRadius: 99 }}>
                          <div style={{ width: `${val}%`, height: "100%", borderRadius: 99,
                            background: val >= 70 ? "var(--green)" : val >= 45 ? "var(--accent)" : "var(--red)",
                            transition: "width 0.6s ease" }} />
                        </div>
                        <span style={{ color: "#444", fontSize: 9, width: 22, textAlign: "right" }}>{val}</span>
                      </div>
                    ))}
                  </div>
                  <p style={{ margin: "6px 0 0", fontSize: 9, fontWeight: 700, textTransform: "uppercase",
                    color: draftScore.funder_readiness === "strong" ? "var(--green)" : draftScore.funder_readiness === "moderate" ? "var(--accent)" : "var(--red)" }}>
                    {draftScore.funder_readiness}
                  </p>
                </>
              ) : (
                <p style={{ color: "var(--accent)", fontWeight: 800, fontSize: 18, margin: 0 }}>{selectedGrant.similarity_score}%</p>
              )}
            </div>

            {/* Draft score insights */}
            {draftScore && draftScore.strengths?.length > 0 && (
              <div style={{ marginBottom: 12 }}>
                <p style={{ color: "#2a2a3e", fontSize: 9, fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.1em", margin: "0 0 5px" }}>Strengths</p>
                {draftScore.strengths.slice(0,2).map((s, i) => (
                  <p key={i} style={{ color: "#22c55e", fontSize: 10, margin: "0 0 3px", lineHeight: 1.4 }}>✓ {s}</p>
                ))}
              </div>
            )}
            {draftScore && draftScore.weaknesses?.length > 0 && (
              <div style={{ marginBottom: 12 }}>
                <p style={{ color: "#2a2a3e", fontSize: 9, fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.1em", margin: "0 0 5px" }}>To Improve</p>
                {draftScore.weaknesses.slice(0,2).map((w, i) => (
                  <p key={i} style={{ color: "#f59e0b", fontSize: 10, margin: "0 0 3px", lineHeight: 1.4 }}>⚠ {w}</p>
                ))}
              </div>
            )}

            {selectedGrant.close_date && (
              <p style={{ color: "var(--red)", fontSize: 10, fontWeight: 700, marginBottom: 12 }}>⏰ Due {selectedGrant.close_date}</p>
            )}

            <div style={{ borderTop: "1px solid #1e1e2e", paddingTop: 12, marginBottom: 12 }}>
              <p style={{ color: "#2a2a3e", fontSize: 9, fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.1em", margin: "0 0 7px" }}>Focus Areas</p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
                {(Array.isArray(selectedGrant.focus_areas)
                  ? selectedGrant.focus_areas
                  : (selectedGrant.focus_areas || "").split(",").map(f => f.trim()).filter(Boolean)
                ).slice(0, 5).map(f => (
                  <span key={f} style={{ background: "#1e1e2e", color: "#555", border: "1px solid #2a2a3e", borderRadius: 3, padding: "1px 5px", fontSize: 9 }}>{f}</span>
                ))}
              </div>
            </div>

            {selectedGrant.application_tip && (
              <div style={{ background: "#1a1a28", borderRadius: 6, padding: "10px" }}>
                <p style={{ color: "#2a2a3e", fontSize: 9, fontWeight: 800, textTransform: "uppercase", margin: "0 0 5px" }}>💡 Tip</p>
                <p style={{ color: "#555", fontSize: 10, lineHeight: 1.6, margin: 0 }}>{selectedGrant.application_tip}</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}