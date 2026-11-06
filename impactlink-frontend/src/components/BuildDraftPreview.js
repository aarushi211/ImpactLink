export function buildPreviewReducer(state, event) {
  if (event.type === "reset") return {};
  const key = event.section_key;
  if (!key) return state;
  const previous = state[key] || { title: key.replaceAll("_", " "), content: "", phase: "writing" };
  if (event.type === "section_start") {
    return { ...state, [key]: { title: event.title || previous.title, content: "", phase: "writing" } };
  }
  if (event.type === "token") {
    return { ...state, [key]: { ...previous, content: previous.content + event.content } };
  }
  if (event.type === "section_status") {
    return { ...state, [key]: { ...previous, phase: event.phase } };
  }
  if (event.type === "section_complete") {
    return { ...state, [key]: { ...previous, ...event.section, phase: "reviewed" } };
  }
  return state;
}

const labels = { writing: "Writing...", reviewing: "Reviewing...", revising: "Revising...", reviewed: "Reviewed — checking overall consistency" };

export default function BuildDraftPreview({ sections, interrupted = false }) {
  return (
    <section aria-label="Live proposal draft" style={{ marginTop: 20 }}>
      <p style={{ color: "#aaa", fontSize: 12 }}>
        {interrupted ? "Connection interrupted. This preview may be incomplete; check the saved session status." : "Your sections appear as they are written. Editing and approval open after the final review."}
      </p>
      {Object.entries(sections).map(([key, section]) => (
        <article key={key} aria-label={section.title} style={{ display: "flex", gap: 10, margin: "24px 0" }}>
          <div aria-hidden="true" style={{ width: 30, height: 30, flexShrink: 0, borderRadius: "50%", background: "var(--accent-dim)", display: "grid", placeItems: "center" }}>✦</div>
          <div style={{ flex: 1, minWidth: 0 }}>
          <h4 style={{ margin: "4px 0 6px" }}>{section.title}</h4>
          <span style={{ color: "var(--accent)", fontSize: 12 }}>{labels[section.phase] || "Working..."}</span>
          <p style={{ whiteSpace: "pre-wrap", lineHeight: 1.8, fontFamily: "Georgia, serif", color: "#bbb" }}>{section.content || "Waiting for the first words..."}</p>
          </div>
        </article>
      ))}
    </section>
  );
}
