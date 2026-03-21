import { useState, useRef, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Nav } from "../components";
import useGrants from "../hooks/useGrants";
import { useAuth } from "../context/AuthContext";
import api from "../services/api";
import { auth } from "../firebase";
import useWorkStore from "../hooks/useWorkStore";

const API_BASE = process.env.REACT_APP_API_URL || "http://localhost:8000";

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
function DraftCard({ stepKey, title, content, onApprove, onRevise, approved, icon }) {
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
    if (!feedback.trim()) return;
    setRevising(true);
    try {
      const user = auth.currentUser;
      const token = user ? await user.getIdToken() : null;

      const res = await fetch(`${API_BASE}/api/build/revise`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { "Authorization": `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ current_draft: content, feedback }),
      });
      const data = await res.json();
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
      background: approved ? "#0d2e1a" : "var(--bg-card)",
      border: `1px solid ${approved ? "#166534" : editMode ? "var(--accent)" : "var(--border)"}`,
      borderRadius: 12, overflow: "hidden",
      transition: "all 0.25s",
    }}>
      {/* header */}
      <div style={{
        padding: "12px 18px", display: "flex",
        alignItems: "center", justifyContent: "space-between",
        borderBottom: `1px solid ${approved ? "#166534" : "var(--border)"}`,
        background: approved ? "#0a2318" : "#111120",
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
              style={{ background: "#1a1a28", border: "1px solid #2a2a3e",
                color: "#888", padding: "5px 12px", borderRadius: 7,
                fontSize: 11, fontWeight: 600, cursor: "pointer" }}
            >
              AI Revise
            </button>
            <button
              onClick={onApprove}
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

      {/* content — editable textarea or read-only prose */}
      <div style={{ padding: "16px 18px" }}>
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

      {/* AI revision box */}
      {showRevise && !approved && !editMode && (
        <div style={{
          padding: "0 18px 16px",
          borderTop: "1px solid #1e1e30",
          paddingTop: 14,
        }}>
          <p style={{ color: "#555", fontSize: 11, margin: "0 0 8px" }}>
            Tell the AI what to change:
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
    </div>
  );
}

// ── main page ─────────────────────────────────────────────────

export default function BuildProposal() {
  const navigate       = useNavigate();
  const [searchParams] = useSearchParams();
  const { profile } = useAuth();
  const { grants }  = useGrants();
  const { saveBuild, builds } = useWorkStore();
  const [savedBuildId, setSavedBuildId] = useState(null);

  // The conversation — array of { role: "ai"|"user", type, ...data }
  const [messages,  setMessages]  = useState([]);
  const [input,     setInput]     = useState("");
  const [loading,   setLoading]   = useState(false);
  const [pdfLoading,setPdfLoad]   = useState(false);
  const [done,      setDone]      = useState(false);

  // Collected answers: [{ step_key, user_answer }]
  const [answers,   setAnswers]   = useState([]);
  // Drafted sections: { section_key: { title, content, approved } }
  const [sections,  setSections]  = useState({});
  const [secOrder,  setSecOrder]  = useState([]);

  const [selectedGrantId, setSelectedGrant] = useState("");
  const [proposalName,   setProposalName]   = useState("");

  const chatEndRef = useRef(null);
  const inputRef   = useRef(null);
  const selectedGrant = grants.find(g => String(g.grant_id) === String(selectedGrantId));

  // Scroll to bottom on new messages
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // ── Start / advance the build flow ──────────────────────────

  const callBuild = async (allAnswers) => {
    setLoading(true);
    try {
      const user = auth.currentUser;
      const token = user ? await user.getIdToken() : null;

      const res = await fetch(`${API_BASE}/api/build/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { "Authorization": `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          answers:  allAnswers,
          profile:  profile || { org_name: "Your Organization" },
          grant:    selectedGrant || null,
        }),
      });

      if (!res.ok) throw new Error(`Server ${res.status}`);

      const reader  = res.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { value, done: streamDone } = await reader.read();
        if (streamDone) break;

        const lines = decoder.decode(value).split("\n").filter(Boolean);
        for (const line of lines) {
          try {
            const chunk = JSON.parse(line);

            if (chunk.type === "question") {
              // AI asks the next question
              setMessages(prev => [...prev, { role: "ai", type: "question", ...chunk }]);
              setTimeout(() => inputRef.current?.focus(), 100);

            } else if (chunk.type === "draft") {
              // AI shows a drafted section
              setSections(prev => ({
                ...prev,
                [chunk.section_key]: { title: chunk.title, content: chunk.content, approved: false },
              }));
              setSecOrder(prev =>
                prev.includes(chunk.section_key) ? prev : [...prev, chunk.section_key]
              );
              setMessages(prev => [...prev, {
                role: "ai", type: "draft",
                step: chunk.step, total: chunk.total,
                key: chunk.key, section_key: chunk.section_key,
                title: chunk.title, content: chunk.content,
              }]);

            } else if (chunk.type === "complete") {
              setDone(true);
              const finalSections = {};
              Object.entries(chunk.sections).forEach(([k, v]) => {
                finalSections[k] = { ...v, approved: false };
              });
              setSections(prev => ({ ...prev, ...finalSections }));
              setSecOrder(chunk.section_order);
              setMessages(prev => [...prev, {
                role: "ai", type: "complete",
                text: "✨ All sections drafted! Review and approve each one, then download your complete proposal.",
              }]);
              // Auto-save initial build to work store (sections not yet approved)
              if (profile) {
                const selectedG = grants.find(g => String(g.grant_id) === String(selectedGrantId));
                saveBuild({
                  title:         proposalName.trim() || selectedG?.title || profile?.org_name || "Built Proposal",
                  org_name:      profile?.org_name || "",
                  grant_title:   selectedG?.title || "",
                  sections:      chunk.sections,
                  section_order: chunk.section_order,
                  answers,
                }).then(saved => { if (saved) setSavedBuildId(saved.id); });
              }
            }
          } catch (_) {}
        }
      }
    } catch (err) {
      setMessages(prev => [...prev, {
        role: "ai", type: "error",
        text: `Something went wrong: ${err.message}`,
      }]);
    } finally {
      setLoading(false);
    }
  };

  // ── Start the builder ─────────────────────────────────────

  const handleStart = () => {
    const welcomeMsg = {
      role: "ai", type: "intro",
      text: `Welcome${profile ? `, ${profile.org_name}` : ""}! I'm going to guide you through building a complete grant proposal from scratch. I'll ask you 7 questions, then draft each section as a professional proposal for you to review and approve.\n\nLet's begin.`,
    };
    setMessages([welcomeMsg]);
    setTimeout(() => callBuild([]), 600);
  };

  // ── User sends an answer ──────────────────────────────────

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading || done) return;
    setInput("");

    // Find the last question message to get its step key
    const lastQuestion = [...messages].reverse().find(m => m.type === "question");
    if (!lastQuestion) return;

    const userMsg = { role: "user", type: "answer", text, stepKey: lastQuestion.key };
    setMessages(prev => [...prev, userMsg]);

    const newAnswers = [...answers, { step_key: lastQuestion.key, user_answer: text }];
    setAnswers(newAnswers);

    // Small delay so the message appears before loading
    setTimeout(() => callBuild(newAnswers), 200);
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

    if (allNowApproved && profile) {
      // Save final approved build
      const selectedG = grants.find(g => String(g.grant_id) === String(selectedGrantId));
      const cleanSections = {};
      secOrder.forEach(k => {
        cleanSections[k] = {
          title:   updatedSections[k].title,
          content: updatedSections[k].content,
        };
      });

      try {
        if (savedBuildId) {
          // Update existing saved build with final approved content
          await api.patch("/api/work/builds", {
            build_id: savedBuildId,
            sections: cleanSections,
          }).catch(() => {}); // non-fatal if patch endpoint not wired
        }
        await saveBuild({
          title:         proposalName.trim() || selectedG?.title || profile?.org_name || "Built Proposal",
          org_name:      profile?.org_name || "",
          grant_title:   selectedG?.title || "",
          sections:      cleanSections,
          section_order: secOrder,
          answers,
        });
      } catch (e) {
        console.error("Final save error:", e);
      }

      // Store proposal context in sessionStorage so grants page can use it
      const proposalCtx = {
        organization_name: profile.org_name,
        mission:           profile.mission,
        cause_area:        profile.cause_area,
        sdgs:              profile.sdgs,
        key_activities:    profile.key_activities,
        geographic_focus:  profile.geographic_focus,
        project_title:     selectedG?.title || "",
      };
      sessionStorage.setItem("proposal", JSON.stringify(proposalCtx));

      // Short delay so user sees "All Approved" state before redirect
      setTimeout(() => navigate("/grants"), 1200);
    }
  };

  const handleRevise = (sectionKey, newContent) => {
    setSections(prev => ({
      ...prev,
      [sectionKey]: { ...prev[sectionKey], content: newContent },
    }));
  };

  // ── PDF download ──────────────────────────────────────────

  const handlePDF = async () => {
    if (!secOrder.length) return;
    setPdfLoad(true);
    try {
      await loadJsPDF();
      const { jsPDF } = window.jspdf;
      const doc   = new jsPDF({ unit: "pt", format: "letter" });
      const mL    = 72, mR = 72;
      const pW    = doc.internal.pageSize.getWidth();
      const pH    = doc.internal.pageSize.getHeight();
      const cW    = pW - mL - mR;
      let y = 80;

      const checkY = (n = 20) => { if (y + n > pH - 60) { doc.addPage(); y = 72; } };

      // Header bar
      doc.setFillColor(18, 18, 32);
      doc.rect(0, 0, pW, 56, "F");
      doc.setTextColor(124, 111, 239); doc.setFontSize(10); doc.setFont("helvetica","bold");
      doc.text("IMPACTLINK AI  —  GRANT PROPOSAL (AI-BUILT)", mL, 34);
      doc.setTextColor(100,100,120);
      doc.text(new Date().toLocaleDateString("en-US",{year:"numeric",month:"long",day:"numeric"}), pW-mR, 34, {align:"right"});
      y = 100;

      // Title block
      doc.setTextColor(20,20,35); doc.setFontSize(22); doc.setFont("helvetica","bold");
      const titleText = selectedGrant?.title || "Grant Proposal";
      const titleLines = doc.splitTextToSize(titleText, cW);
      doc.text(titleLines, mL, y);
      y += titleLines.length * 28 + 8;

      doc.setFontSize(11); doc.setFont("helvetica","normal"); doc.setTextColor(100,100,120);
      doc.text(`${selectedGrant?.agency || ""}  ·  ${proposalName.trim() || profile?.org_name || "Your Organization"}`, mL, y);
      y += 12;
      doc.setDrawColor(200,200,220); doc.setLineWidth(0.5); doc.line(mL, y, pW-mR, y);
      y += 28;

      // Sections
      const ICONS_TEXT = ["01","02","03","04","05","06","07"];
      secOrder.forEach((key, idx) => {
        const sec = sections[key];
        if (!sec) return;
        checkY(60);

        doc.setFillColor(240,240,255);
        doc.roundedRect(mL, y-12, cW, 22, 4, 4, "F");
        doc.setFontSize(9); doc.setFont("helvetica","bold"); doc.setTextColor(100,90,200);
        doc.text(`${ICONS_TEXT[idx] || "—"}  ${sec.title.toUpperCase()}`, mL+10, y+3);
        y += 28;

        doc.setFontSize(10.5); doc.setFont("helvetica","normal"); doc.setTextColor(40,40,60);
        const clean = (sec.content || "").replace(/\*\*(.*?)\*\*/g,"$1");
        const paras = clean.split(/\n{2,}/);
        for (const para of paras) {
          if (!para.trim()) continue;
          const lines = doc.splitTextToSize(para.trim(), cW);
          checkY(lines.length * 14 + 8);
          doc.text(lines, mL, y);
          y += lines.length * 14 + 10;
        }
        y += 16;
        checkY(10);
        doc.setDrawColor(230,230,245); doc.setLineWidth(0.3);
        doc.line(mL, y, pW-mR, y);
        y += 20;
      });

      // Page footers
      const total = doc.internal.getNumberOfPages();
      for (let i = 1; i <= total; i++) {
        doc.setPage(i);
        doc.setFillColor(18,18,32); doc.rect(0, pH-36, pW, 36, "F");
        doc.setFontSize(8); doc.setTextColor(80,80,100); doc.setFont("helvetica","normal");
        doc.text("Generated by ImpactLink AI — Build Proposal", mL, pH-16);
        doc.text(`Page ${i} of ${total}`, pW-mR, pH-16, {align:"right"});
      }

      const slug = (proposalName.trim() || profile?.org_name || "proposal").replace(/\s+/g,"_").toLowerCase();
      doc.save(`${slug}_built_proposal.pdf`);
    } catch(e) { console.error(e); } finally { setPdfLoad(false); }
  };

  // Reload a saved build — from ?load=<id> param (Dashboard) or sessionStorage (legacy)
  const loadId = searchParams.get("load");
  useEffect(() => {
    // Try ?load=id from work store first
    if (loadId && builds.length > 0) {
      const saved = builds.find(b => b.id === loadId);
      if (saved) {
        const savedSecs  = saved.sections      || {};
        const savedOrder = saved.section_order || Object.keys(savedSecs);
        const restored   = {};
        savedOrder.forEach(k => {
          if (savedSecs[k]) restored[k] = { ...savedSecs[k], approved: false };
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
        const { sections: savedSecs, section_order: savedOrder, answers: savedAnswers } = JSON.parse(raw);
        if (savedSecs && savedOrder) {
          const restored = {};
          savedOrder.forEach(k => {
            if (savedSecs[k]) restored[k] = { ...savedSecs[k], approved: false };
          });
          setSections(restored);
          setSecOrder(savedOrder);
          setAnswers(savedAnswers || []);
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
  const allApproved    = totalSections > 0 && approvedCount === totalSections;
  const lastIsQuestion = messages.length > 0 && messages[messages.length-1]?.type === "question";
  const hasStarted     = messages.length > 0;

  // ── render ────────────────────────────────────────────────

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)",
      display: "flex", flexDirection: "column" }}>
      <Nav />

      {/* App bar */}
      <div style={{
        background: "#13131f", borderBottom: "1px solid #1e1e30",
        padding: "0 24px", height: 48,
        display: "flex", alignItems: "center", justifyContent: "space-between",
        gap: 12, position: "sticky", top: 64, zIndex: 90,
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
          {/* Grant selector */}
          <select
            value={selectedGrantId}
            onChange={e => setSelectedGrant(e.target.value)}
            disabled={hasStarted}
            style={{
              background:"#111120", border:"1px solid #1e1e30",
              color: selectedGrantId ? "#ddd" : "#444",
              padding:"5px 10px", borderRadius:7,
              fontSize:11, cursor:"pointer", outline:"none",
              opacity: hasStarted ? 0.5 : 1,
            }}
          >
            <option value="">No target grant</option>
            {grants.map(g => (
              <option key={g.grant_id} value={g.grant_id}>
                {g.title.length > 40 ? g.title.slice(0,40)+"…" : g.title}
              </option>
            ))}
          </select>

          {(allApproved || (done && totalSections > 0)) && (
            <button onClick={handlePDF} disabled={pdfLoading} style={{
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

      {/* Body — two-column: chat left, sections right */}
      <div style={{ flex:1, display:"flex", overflow:"hidden" }}>

        {/* ── Chat panel (left) ─────────────────── */}
        <div style={{
          width: totalSections > 0 ? "45%" : "100%",
          flexShrink: 0,
          display: "flex", flexDirection: "column",
          borderRight: totalSections > 0 ? "1px solid var(--border)" : "none",
          transition: "width 0.3s",
        }}>

          {/* Chat messages */}
          <div style={{ flex:1, overflowY:"auto", padding:"24px 28px 16px" }}>

            {/* Empty / start state */}
            {!hasStarted && (
              <div style={{ maxWidth: 540, margin: "0 auto", paddingTop: 40 }}>
                {/* Hero */}
                <div style={{
                  background: "var(--bg-card)", border: "1px solid var(--border)",
                  borderRadius: 16, padding: "32px 32px 28px", marginBottom: 20,
                  textAlign: "center",
                }}>
                  <div style={{
                    width: 64, height: 64, borderRadius: 16, margin: "0 auto 16px",
                    background: "linear-gradient(135deg, var(--accent), #4f46e5)",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 28,
                  }}>✍</div>
                  <h2 style={{ margin:"0 0 10px", fontWeight:800, color:"#fff",
                    fontSize:22, letterSpacing:"-0.02em" }}>
                    Build a Proposal
                  </h2>
                  <p style={{ margin:"0 0 20px", color:"#555", fontSize:14,
                    lineHeight:1.7, maxWidth:380, marginLeft:"auto", marginRight:"auto" }}>
                    I'll guide you through 7 questions and draft each section of your
                    grant proposal in real time. No blank page required.
                  </p>

                  {/* Step preview */}
                  <div style={{ display:"flex", justifyContent:"center",
                    gap:6, flexWrap:"wrap", marginBottom: 24 }}>
                    {["Project Vision","Activities","Beneficiaries","Org Capacity",
                      "Goals & KPIs","Budget","Sustainability"].map((s, i) => (
                      <span key={s} style={{
                        background:"#111120", border:"1px solid #1e1e30",
                        borderRadius:20, padding:"5px 11px",
                        color:"#444", fontSize:11,
                        display:"flex", alignItems:"center", gap:5,
                      }}>
                        <span style={{ fontSize:12 }}>{STEP_ICONS[i]}</span> {s}
                      </span>
                    ))}
                  </div>

                  {/* Proposal name input */}
                  <div style={{ marginBottom: 14, textAlign: "left" }}>
                    <label style={{ color: "#555", fontSize: 11, fontWeight: 700,
                      textTransform: "uppercase", letterSpacing: "0.06em",
                      display: "block", marginBottom: 6 }}>
                      Proposal Name <span style={{ color: "#333355", fontWeight: 400 }}>(optional)</span>
                    </label>
                    <input
                      value={proposalName}
                      onChange={e => setProposalName(e.target.value)}
                      placeholder={`${profile?.org_name || "Your Org"} — ${new Date().getFullYear()} Grant Proposal`}
                      style={{
                        width: "100%", background: "#111120",
                        border: "1px solid #2a2a4e",
                        borderRadius: 9, padding: "10px 14px",
                        color: "#e0e0f0", fontSize: 13,
                        outline: "none", boxSizing: "border-box",
                        transition: "border-color 0.15s",
                      }}
                      onFocus={e => e.target.style.borderColor = "var(--accent)"}
                      onBlur={e => e.target.style.borderColor = "#2a2a4e"}
                    />
                    <p style={{ color: "#333355", fontSize: 10, margin: "4px 0 0" }}>
                      This name will appear in your Dashboard and on the PDF cover.
                    </p>
                  </div>

                  <button
                    onClick={handleStart}
                    style={{
                      background:"var(--accent)", border:"none", color:"#fff",
                      padding:"13px 32px", borderRadius:10,
                      fontSize:15, fontWeight:700, cursor:"pointer",
                      width:"100%",
                    }}
                  >
                    Start Building →
                  </button>
                </div>

                {!profile && (
                  <div style={{
                    background:"#0d1a2e", border:"1px solid #1e3a5f",
                    borderRadius:10, padding:"12px 16px",
                    display:"flex", alignItems:"center", gap:10,
                  }}>
                    <span style={{ color:"#7cb9f5", fontSize:14 }}>💡</span>
                    <p style={{ margin:0, color:"#7cb9f5", fontSize:12, lineHeight:1.6 }}>
                      <span
                        onClick={() => navigate("/login")}
                        style={{ fontWeight:700, cursor:"pointer",
                          textDecoration:"underline" }}
                      >Sign in</span>
                      {" "}to save your org profile — it makes proposals much more specific.
                    </p>
                  </div>
                )}
              </div>
            )}

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
                      background:"linear-gradient(135deg,var(--accent),#4f46e5)",
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
                            {msg.title} drafted — see the panel on the right to review
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

            {/* Loading dots */}
            {loading && (
              <div style={{ display:"flex", gap:10, marginBottom:18,
                alignItems:"flex-start" }}>
                <div style={{
                  width:30, height:30, borderRadius:"50%", flexShrink:0,
                  background:"linear-gradient(135deg,var(--accent),#4f46e5)",
                  display:"flex", alignItems:"center", justifyContent:"center",
                  fontSize:13, fontWeight:800, color:"#fff",
                }}>✦</div>
                <div style={{
                  background:"var(--bg-card)", border:"1px solid var(--border)",
                  borderRadius:"4px 14px 14px 14px", padding:"12px 16px",
                }}>
                  <TypingDots />
                </div>
              </div>
            )}

            <div ref={chatEndRef} />
          </div>

          {/* Input bar */}
          {hasStarted && !done && (
            <div style={{
              padding:"12px 20px", borderTop:"1px solid var(--border)",
              display:"flex", gap:8, alignItems:"flex-end",
              background:"#0d0d16",
            }}>
              <textarea
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => {
                  if (e.key==="Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
                }}
                placeholder={
                  lastIsQuestion
                    ? "Type your answer…"
                    : loading
                    ? "Drafting section…"
                    : "Waiting…"
                }
                disabled={loading || !lastIsQuestion}
                rows={2}
                style={{
                  flex:1, background:"#111120",
                  border:"1px solid var(--border)", borderRadius:10,
                  color:"#e0e0f0", padding:"10px 14px",
                  fontSize:13, resize:"none", outline:"none",
                  fontFamily:"DM Sans, sans-serif",
                  opacity: loading || !lastIsQuestion ? 0.5 : 1,
                }}
              />
              <button
                onClick={handleSend}
                disabled={!input.trim() || loading || !lastIsQuestion}
                style={{
                  width:40, height:40, borderRadius:10, border:"none",
                  background: input.trim() && !loading && lastIsQuestion
                    ? "var(--accent)" : "#1e1e30",
                  color:"#fff", fontSize:18, cursor:"pointer",
                  display:"flex", alignItems:"center", justifyContent:"center",
                  flexShrink:0,
                }}
              >↑</button>
            </div>
          )}
        </div>

        {/* ── Sections panel (right) ────────────── */}
        {totalSections > 0 && (
          <div style={{
            flex:1, overflowY:"auto",
            padding:"24px 28px 80px",
            background:"#0f0f18",
          }}>
            <div style={{ display:"flex", alignItems:"center",
              justifyContent:"space-between", marginBottom:16 }}>
              <p style={{ margin:0, fontWeight:700, color:"#fff", fontSize:14 }}>
                Your Proposal Sections
              </p>
              <p style={{ margin:0, color: allApproved ? "var(--green)" : "#555",
                fontSize:12, fontWeight:600 }}>
                {approvedCount}/{totalSections} approved
              </p>
            </div>

            {/* Progress bar */}
            <div style={{ height:4, background:"#1e1e30", borderRadius:2,
              marginBottom:20, overflow:"hidden" }}>
              <div style={{
                height:"100%",
                width: `${totalSections > 0 ? (approvedCount/totalSections)*100 : 0}%`,
                background:"var(--accent)",
                borderRadius:2,
                transition:"width 0.4s",
              }} />
            </div>

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
                    onApprove={() => handleApprove(key)}
                    onRevise={(newContent) => handleRevise(key, newContent)}
                  />
                );
              })}
            </div>

            {/* All approved banner */}
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
                <button onClick={handlePDF} disabled={pdfLoading} style={{
                  background: pdfLoading ? "#1a1a28" : "#e63946",
                  border:"none", color:"#fff",
                  padding:"11px 22px", borderRadius:9,
                  fontSize:13, fontWeight:700, cursor:"pointer",
                }}>
                  {pdfLoading ? "⟳ Generating…" : "↓ Download PDF"}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}