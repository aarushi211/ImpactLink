import { emptyApplicationSpec, applicationCheck, lengthCheck, sectionRequirements, aiPolicyCheck } from "../utils/application";
import { useEffect, useRef, useState } from "react";
import api from "../services/api";
import "./FormControls.css";

let sequence = 0;
const identifier = prefix => `${prefix}_${Date.now()}_${++sequence}`;
const inputStyle = { width: "100%", boxSizing: "border-box", padding: "9px 12px", background: "#111120", color: "#ddd", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 };
const panel = { border: "1px solid var(--border)", borderRadius: 9, padding: 14, margin: "12px 0", fontSize: 12, color: "#bbb", background: "var(--bg-card)" };

export function FunderAiPolicyNotice({ spec }) {
  const policy = aiPolicyCheck(spec);
  const messages = {
    unknown: "Funder AI policy unknown. Check the current application instructions or ask the funder before using AI-assisted text. This app has not verified permission.",
    permitted: "AI use recorded as permitted. Follow any conditions below and verify the current funder instructions before submission.",
    disclosure_required: "This funder requires disclosure of AI assistance. Complete the disclosure in the funder's required format and location; this app does not submit it for you.",
    prohibited: "Recorded funder policy prohibits AI use. AI drafting and revision are disabled. Saved text remains available for manual editing; confirm whether existing AI-assisted content can be used.",
  };
  return <div role="status" style={{ ...panel, borderColor: policy.status === "prohibited" ? "#b45309" : "var(--border)" }}>
    <strong>Funder AI-use policy</strong>
    <p>{messages[policy.status] || messages.unknown}</p>
    {policy.source_reference && <p>Policy source (user-recorded): {policy.source_reference}</p>}
    {policy.notes && <p style={{ whiteSpace: "pre-wrap" }}>{policy.notes}</p>}
    {policy.status === "disclosure_required" && <p>{policy.disclosure_ready ? "Disclosure marked ready by you; compliance is not independently verified." : "Disclosure still needs review before completing this session. You can save a draft in the meantime."}</p>}
  </div>;
}

export function ApplicationRequirementsEditor({ value, onChange, disabled, existingSections = [], grant, collapsible = true, showPrefill = true }) {
  const [extracting, setExtracting] = useState(false);
  const [candidate, setCandidate] = useState(null);
  const [error, setError] = useState("");
  const request = useRef(0);
  useEffect(() => { request.current += 1; setCandidate(null); setError(""); setExtracting(false); }, [grant?.grant_id]);
  const prefill = async () => {
    const sequence = ++request.current;
    setExtracting(true); setError(""); setCandidate(null);
    try {
      const response = grant?.application_spec ? { data: { application_spec: grant.application_spec, evidence: [], warnings: ["Review the requirements already recorded for this grant before applying."] } } : await api.post(`/api/grants/${encodeURIComponent(grant.grant_id)}/application-requirements`);
      if (sequence === request.current) setCandidate(response.data);
    } catch (err) {
      if (sequence === request.current) setError(typeof err.response?.data?.detail === "string" ? err.response.data.detail : "Could not prefill requirements. Enter them manually or retry.");
    } finally { if (sequence === request.current) setExtracting(false); }
  };
  const spec = { ...emptyApplicationSpec(), ...value };
  const policy = aiPolicyCheck(spec);
  const updatePolicy = updates => update("ai_policy", { status: policy.status, source_reference: policy.source_reference, notes: policy.notes, disclosure_ready: policy.disclosure_ready, ...updates });
  const update = (field, next) => onChange({ ...spec, [field]: next });
  const sectionUpdate = (key, field, next) => update("sections", spec.sections.map(item => item.key === key ? { ...item, [field]: next } : item));
  const addSection = (title = "", instructions = "") => update("sections", [...spec.sections, { key: identifier("question"), title, instructions, max_words: null, max_characters: null, required: true }]);
  const addAttachment = title => update("attachments", [...spec.attachments, { id: identifier("attachment"), title, stage: spec.stage, required: true, status: "not_started", notes: "" }]);
  const Container = collapsible ? "details" : "section";
  return <div className="il-form"><Container {...(collapsible ? { open: true } : {})} style={{ ...panel, borderRadius: 12, padding: "18px 20px" }}>
    {collapsible ? <summary style={{ cursor: "pointer", color: "#ddd", fontWeight: 700 }}>Application structure and requirements</summary> : <h2 style={{ color: "#eee", fontSize: 17, margin: "0 0 12px" }}>Application structure and requirements</h2>}
    <fieldset disabled={disabled} style={{ border: 0, padding: 0 }}>
      <p>Record the funder's exact questions, limits and documents. With no custom questions, the writer uses a general starter for the selected stage. Adding questions replaces that starter structure.</p>
      {showPrefill && <>
      <button type="button" className="il-primary" disabled={!grant?.grant_id || extracting} onClick={prefill}>{extracting ? "Reading grant requirements..." : "Prefill from selected grant"}</button>
      <p>Prefill reads the grant text stored in the database. Review the source excerpts before applying; missing portal questions or PDF instructions still need to be added.</p>
      {error && <p role="alert" style={{ color: "var(--red)" }}>{error}</p>}
      {candidate && <section aria-label="Extracted requirements preview" style={{ background: "#111120", border: "1px solid var(--border)", borderRadius: 8, padding: 12, marginBottom: 14 }}>
        <strong>Review suggested setup before replacing this form</strong>
        <p>{candidate.application_spec.sections.length} questions, {candidate.application_spec.attachments.length} attachments; stage: {candidate.application_spec.stage.replace(/_/g, " ")}; AI policy: {candidate.application_spec.ai_policy?.status?.replace(/_/g, " ") || "unknown"}.</p>
        {(candidate.evidence || []).map((item, index) => <p key={index}><strong>{item.field}</strong><br /><q>{item.quote}</q></p>)}
        {(candidate.warnings || []).map((warning, index) => <p key={index}>{warning}</p>)}
        <button type="button" className="il-primary" onClick={() => { onChange(candidate.application_spec); setCandidate(null); }}>Use extracted setup</button>{" "}
        <button type="button" onClick={() => setCandidate(null)}>Keep current setup</button>
      </section>}
      </>}
      <label>Application stage<select aria-label="Application stage" style={inputStyle} value={spec.stage} onChange={event => onChange({ ...spec, stage: event.target.value, sections: [] })}><option value="full_proposal">Full proposal</option><option value="loi">Letter of inquiry (LOI)</option><option value="reporting">Post-award report</option></select></label>
      <label>Funder source / instructions reference<input aria-label="Funder requirements source" style={inputStyle} placeholder="RFP URL, form name or document page" value={spec.source_reference} onChange={event => update("source_reference", event.target.value)} /></label>
      <label>Application process notes<textarea aria-label="Application process notes" style={inputStyle} value={spec.process_notes} onChange={event => update("process_notes", event.target.value)} placeholder="LOI first, invitation, portal, reporting schedule or other confirmed steps" /></label>
      <h4>Funder rules on AI use</h4>
      <p>Record the actual policy for this application stage. Redaction does not make prohibited AI use permissible. If the policy has narrower conditions, record them below and confirm that your intended use is allowed.</p>
      <label>AI-use policy<select aria-label="Funder AI-use policy" style={inputStyle} value={policy.status} onChange={event => updatePolicy({ status: event.target.value, disclosure_ready: false })}><option value="unknown">Unknown / not checked</option><option value="permitted">AI use permitted (check conditions)</option><option value="disclosure_required">AI use permitted with disclosure</option><option value="prohibited">AI use prohibited</option></select></label>
      <label>AI policy source<input aria-label="AI policy source" maxLength={2000} style={inputStyle} value={policy.source_reference} onChange={event => updatePolicy({ source_reference: event.target.value })} placeholder="Policy URL, document page or funder correspondence" /></label>
      <label>AI policy conditions / disclosure instructions<textarea aria-label="AI policy conditions" maxLength={6000} style={inputStyle} value={policy.notes} onChange={event => updatePolicy({ notes: event.target.value })} placeholder="Permitted uses, disclosure wording and where it must be supplied" /></label>
      <h4 style={{ marginBottom: 6 }}>Questions in funder order</h4>
      {spec.sections.map((item, index) => <div key={item.key} style={{ borderTop: "1px solid var(--border)", paddingTop: 10, marginBottom: 12 }}>
        <label>Question title<input aria-label={`Question title ${index + 1}`} style={inputStyle} value={item.title} onChange={event => sectionUpdate(item.key, "title", event.target.value)} /></label>
        <label>Question / instructions<textarea aria-label={`Question instructions ${index + 1}`} style={inputStyle} value={item.instructions} onChange={event => sectionUpdate(item.key, "instructions", event.target.value)} /></label>
        <div style={{ display: "flex", gap: 8 }}>
          <label>Maximum words<input aria-label={`Maximum words ${index + 1}`} type="number" min="1" step="1" style={inputStyle} value={item.max_words ?? ""} onChange={event => sectionUpdate(item.key, "max_words", event.target.value === "" ? null : Number(event.target.value))} /></label>
          <label>Maximum characters<input aria-label={`Maximum characters ${index + 1}`} type="number" min="1" step="1" style={inputStyle} value={item.max_characters ?? ""} onChange={event => sectionUpdate(item.key, "max_characters", event.target.value === "" ? null : Number(event.target.value))} /></label>
        </div>
        <label><input type="checkbox" checked={item.required} onChange={event => sectionUpdate(item.key, "required", event.target.checked)} />Required answer</label>
        <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
          <button disabled={index === 0} onClick={() => { const next = [...spec.sections]; [next[index - 1], next[index]] = [next[index], next[index - 1]]; update("sections", next); }}>Move question {index + 1} up</button>
          <button disabled={index === spec.sections.length - 1} onClick={() => { const next = [...spec.sections]; [next[index + 1], next[index]] = [next[index], next[index + 1]]; update("sections", next); }}>Move question {index + 1} down</button>
          <button onClick={() => update("sections", spec.sections.filter(section => section.key !== item.key))}>Remove question {index + 1}</button>
        </div>
      </div>)}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <button onClick={() => addSection()}>Add application question</button>
        <button onClick={() => addSection("Logic model / theory of change", "Explain how inputs and activities lead to outputs and measurable outcomes. State assumptions and evidence; mark unknowns.")}>Add logic model</button>
        <button onClick={() => addSection("Work plan and timeline", "Describe activities, milestones, responsible roles and timing. Use confirmed dates or label proposed dates.")}>Add work plan</button>
        {existingSections.length > 0 && <button onClick={() => update("sections", existingSections.map(item => ({ key: item.key, title: item.title, instructions: "", max_words: null, max_characters: null, required: true })))}>Use current proposal headings</button>}
        {spec.sections.length > 0 && <button onClick={() => update("sections", [])}>Use general starter instead</button>}
      </div>
      <h4>Attachments and prerequisites</h4>
      <p>Add only items the funder requires. Checklist entries are not uploaded documents.</p>
      {spec.attachments.map((item, index) => <div key={item.id} style={{ marginBottom: 10 }}>
        <input aria-label={`Attachment title ${index + 1}`} style={inputStyle} value={item.title} onChange={event => update("attachments", spec.attachments.map(row => row.id === item.id ? { ...row, title: event.target.value } : row))} />
        <label><input type="checkbox" checked={item.required} onChange={event => update("attachments", spec.attachments.map(row => row.id === item.id ? { ...row, required: event.target.checked } : row))} />Required</label>
        <select aria-label={`Attachment stage ${index + 1}`} value={item.stage} onChange={event => update("attachments", spec.attachments.map(row => row.id === item.id ? { ...row, stage: event.target.value } : row))}><option value="full_proposal">Full proposal</option><option value="loi">LOI</option><option value="reporting">Reporting</option></select>
        <button onClick={() => update("attachments", spec.attachments.filter(row => row.id !== item.id))}>Remove attachment {index + 1}</button>
      </div>)}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>{["IRS determination letter", "Board list", "Audited financials", "Letters of support", "UEI / SAM registration", "Other required document"].map(title => <button key={title} onClick={() => addAttachment(title)}>Add {title}</button>)}</div>
    </fieldset>
    {disabled && <p>Structure is locked for this session. Start a new session to change questions or limits.</p>}
  </Container><FunderAiPolicyNotice spec={spec} /></div>;
}

export function ApplicationReview({ spec, sections, onChange, onSave, disabled }) {
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState("");
  const checklistKey = JSON.stringify(spec);
  const latestKey = useRef(checklistKey);
  latestKey.current = checklistKey;
  useEffect(() => { setSaved(false); setSaveError(""); }, [checklistKey]);
  const save = async () => {
    if (saving || disabled) return;
    setSaving(true); setSaved(false); setSaveError("");
    const key = checklistKey;
    try {
      const result = await onSave(spec);
      if (result === null || result === false) throw new Error("No proposal was saved. Please retry.");
      if (latestKey.current === key) setSaved(true);
    } catch (error) {
      if (latestKey.current === key) setSaveError(typeof error.response?.data?.detail === "string" ? error.response.data.detail : error.message || "Could not save the checklist. Please retry.");
    } finally { setSaving(false); }
  };
  if (!spec) return null;
  const check = applicationCheck(spec, sections);
  return <section aria-label="Application requirements review" style={panel}>
    <strong>Application review · {spec.stage.replace(/_/g, " ")}</strong>
    <p>Requirements recorded from: {spec.source_reference || "source not supplied"}. Submission readiness is not verified.</p>
    {spec.process_notes && <p>{spec.process_notes}</p>}
    <FunderAiPolicyNotice spec={spec} />
    {aiPolicyCheck(spec).status === "disclosure_required" && <label style={{ display: "block", marginBottom: 12 }}><input type="checkbox" aria-label="Required AI disclosure is ready" disabled={disabled || saving} checked={Boolean(spec.ai_policy?.disclosure_ready)} onChange={event => onChange({ ...spec, ai_policy: { ...spec.ai_policy, disclosure_ready: event.target.checked } })} />I have prepared the required AI disclosure using the funder's instructions (self-reported).</label>}
    {!check.can_finalize_text && <p role="alert" style={{ color: "#f87171" }}>Fix missing or over-limit answers before confirming: {[...check.missing, ...check.over].map(key => sectionRequirements(spec, key).title || key.replace(/_/g, " ")).join(", ")}</p>}
    {Object.entries(sections).map(([key, section]) => {
      const req = sectionRequirements(spec, key);
      if (req.max_words == null && req.max_characters == null) return null;
      const count = lengthCheck(typeof section === "string" ? section : section.content, req);
      return <p key={key} style={{ color: count.within_limits ? "#aaa" : "#f87171" }}>{req.title || key}: {count.words}{req.max_words != null ? ` / ${req.max_words}` : ""} words · {count.characters}{req.max_characters != null ? ` / ${req.max_characters}` : ""} characters</p>;
    })}
    <p>Characters include spaces and line breaks. Final counts should be checked in the funder's portal.</p>
    {spec.attachments.filter(item => item.stage === spec.stage).map(item => <label key={item.id} style={{ display: "block", marginBottom: 10 }}>{item.title}{item.required ? " (required)" : " (optional)"}<select aria-label={`Checklist status: ${item.title}`} style={inputStyle} disabled={disabled || saving} value={item.status} onChange={event => onChange({ ...spec, attachments: spec.attachments.map(row => row.id === item.id ? { ...row, status: event.target.value } : row) })}><option value="not_started">Not started</option><option value="in_progress">In progress</option><option value="ready">Ready (self-reported)</option><option value="not_applicable">Not applicable — confirm with funder</option></select>{item.required && item.status !== "ready" && <span style={{ color: "#facc15" }}>Required item still needs review.</span>}</label>)}
    {onSave && <button type="button" disabled={disabled || saving} onClick={save}>{saving ? "Saving checklist..." : "Save application checklist"}</button>}
    {saved && <p role="status" style={{ color: "var(--green)" }}>Checklist saved.</p>}
    {saveError && <p role="alert" style={{ color: "var(--red)" }}>{saveError}</p>}
  </section>;
}
