import { emptyApplicationSpec, applicationCheck, lengthCheck, sectionRequirements } from "../utils/application";

let sequence = 0;
const identifier = prefix => `${prefix}_${Date.now()}_${++sequence}`;
const inputStyle = { width: "100%", boxSizing: "border-box", padding: 8, background: "#161625", color: "#ddd", border: "1px solid var(--border)", borderRadius: 5 };
const panel = { border: "1px solid var(--border)", borderRadius: 9, padding: 14, margin: "12px 0", fontSize: 12, color: "#bbb", background: "var(--bg-card)" };

export function ApplicationRequirementsEditor({ value, onChange, disabled, existingSections = [] }) {
  const spec = value || emptyApplicationSpec();
  const update = (field, next) => onChange({ ...spec, [field]: next });
  const sectionUpdate = (key, field, next) => update("sections", spec.sections.map(item => item.key === key ? { ...item, [field]: next } : item));
  const addSection = (title = "", instructions = "") => update("sections", [...spec.sections, { key: identifier("question"), title, instructions, max_words: null, max_characters: null, required: true }]);
  const addAttachment = title => update("attachments", [...spec.attachments, { id: identifier("attachment"), title, stage: spec.stage, required: true, status: "not_started", notes: "" }]);
  return <details style={panel}>
    <summary style={{ cursor: "pointer", color: "#ddd", fontWeight: 700 }}>Application structure and requirements</summary>
    <fieldset disabled={disabled} style={{ border: 0, padding: 0 }}>
      <p>Record the funder's exact questions, limits and documents. With no custom questions, the writer uses a general starter for the selected stage. Adding questions replaces that starter structure.</p>
      <label>Application stage<select aria-label="Application stage" style={inputStyle} value={spec.stage} onChange={event => onChange({ ...spec, stage: event.target.value, sections: [] })}><option value="full_proposal">Full proposal</option><option value="loi">Letter of inquiry (LOI)</option><option value="reporting">Post-award report</option></select></label>
      <label>Funder source / instructions reference<input aria-label="Funder requirements source" style={inputStyle} placeholder="RFP URL, form name or document page" value={spec.source_reference} onChange={event => update("source_reference", event.target.value)} /></label>
      <label>Application process notes<textarea aria-label="Application process notes" style={inputStyle} value={spec.process_notes} onChange={event => update("process_notes", event.target.value)} placeholder="LOI first, invitation, portal, reporting schedule or other confirmed steps" /></label>
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
  </details>;
}

export function ApplicationReview({ spec, sections, onChange, onSave, disabled }) {
  if (!spec) return null;
  const check = applicationCheck(spec, sections);
  return <section aria-label="Application requirements review" style={panel}>
    <strong>Application review · {spec.stage.replace(/_/g, " ")}</strong>
    <p>Requirements recorded from: {spec.source_reference || "source not supplied"}. Submission readiness is not verified.</p>
    {spec.process_notes && <p>{spec.process_notes}</p>}
    {!check.can_finalize_text && <p role="alert" style={{ color: "#f87171" }}>Fix missing or over-limit answers before confirming: {[...check.missing, ...check.over].map(key => sectionRequirements(spec, key).title || key.replace(/_/g, " ")).join(", ")}</p>}
    {Object.entries(sections).map(([key, section]) => {
      const req = sectionRequirements(spec, key);
      if (req.max_words == null && req.max_characters == null) return null;
      const count = lengthCheck(typeof section === "string" ? section : section.content, req);
      return <p key={key} style={{ color: count.within_limits ? "#aaa" : "#f87171" }}>{req.title || key}: {count.words}{req.max_words != null ? ` / ${req.max_words}` : ""} words · {count.characters}{req.max_characters != null ? ` / ${req.max_characters}` : ""} characters</p>;
    })}
    <p>Characters include spaces and line breaks. Final counts should be checked in the funder's portal.</p>
    {spec.attachments.filter(item => item.stage === spec.stage).map(item => <label key={item.id} style={{ display: "block", marginBottom: 10 }}>{item.title}{item.required ? " (required)" : " (optional)"}<select aria-label={`Checklist status: ${item.title}`} style={inputStyle} disabled={disabled} value={item.status} onChange={event => onChange({ ...spec, attachments: spec.attachments.map(row => row.id === item.id ? { ...row, status: event.target.value } : row) })}><option value="not_started">Not started</option><option value="in_progress">In progress</option><option value="ready">Ready (self-reported)</option><option value="not_applicable">Not applicable — confirm with funder</option></select>{item.required && item.status !== "ready" && <span style={{ color: "#facc15" }}>Required item still needs review.</span>}</label>)}
    {onSave && <button disabled={disabled} onClick={onSave}>Save application checklist</button>}
  </section>;
}
