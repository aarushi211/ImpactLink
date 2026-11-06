export default function ConsistencyReview({ review, onCheck, disabled, checking }) {
  const labels = { passed: "AI check found no inconsistencies", issues_found: "Inconsistencies need review", incomplete: "Consistency check incomplete", unavailable: "Consistency check unavailable", stale: "Text changed since the consistency check" };
  return <section aria-label="Proposal consistency review" style={{ margin: "12px 0", padding: 14, border: "1px solid var(--border)", borderRadius: 9, color: "#bbb", background: "var(--bg-card)", fontSize: 12 }}>
    <strong>{labels[review?.status] || "No recorded consistency check"}</strong>
    <p>This AI review checks agreement between sections. It does not verify facts, eligibility or submission readiness.</p>
    {review?.reason && <p>{review.reason}</p>}
    {review?.characters_reviewed > 0 && <p>Last full-text check: {review.section_count} sections, {review.characters_reviewed.toLocaleString()} characters including headings.</p>}
    {review?.fixes_attempted > 0 && <p>{review.fixes_attempted} automatic consistency edit(s) attempted, followed by another check. Review those edits; earlier section scores predate them.</p>}
    {(review?.issues || []).length > 0 && <ul>{review.issues.map((issue, index) => <li key={index}><strong>{issue.section.replace(/_/g, " ")} ({issue.severity})</strong>: {issue.issue}<br />Suggested action: {issue.fix}</li>)}</ul>}
    {review?.status === "stale" && <p>Listed findings refer to earlier text. Check the updated proposal again or review it manually.</p>}
    {onCheck && <button onClick={onCheck} disabled={disabled || checking}>{checking ? "Checking consistency…" : "Check full proposal consistency"}</button>}
  </section>;
}
