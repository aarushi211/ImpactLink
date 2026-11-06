export const emptyAiPolicy = () => ({ status: "unknown", source_reference: "", notes: "", disclosure_ready: false });
export const emptyApplicationSpec = (stage = "full_proposal") => ({ stage, source_reference: "", process_notes: "", sections: [], attachments: [], ai_policy: emptyAiPolicy() });
export function aiPolicyCheck(spec) {
  const policy = { ...emptyAiPolicy(), ...spec?.ai_policy };
  return { ...policy, ai_drafting_allowed: policy.status !== "prohibited", disclosure_pending: policy.status === "disclosure_required" && !policy.disclosure_ready };
}
export const applicationChecklistInput = spec => spec ? { attachment_statuses: attachmentStatuses(spec), ai_disclosure_ready: Boolean(spec.ai_policy?.disclosure_ready) } : {};
export const starterSections = {
  full_proposal: ["executive_summary", "problem_statement", "goals_and_objectives", "proposed_solution", "target_beneficiaries", "organizational_capacity", "evaluation_plan", "budget_narrative", "sustainability", "equity_statement"],
  loi: ["loi_summary", "loi_capacity", "loi_outcomes"],
  reporting: ["report_progress", "report_outcomes", "report_financial", "report_changes"],
};
export const sectionRequirements = (spec, key) => spec?.sections?.find(section => section.key === key) || {};
export function lengthCheck(content, requirement = {}) {
  const text = String(content || "").replace(/\r\n?/g, "\n");
  const words = (text.match(/\S+/g) || []).length;
  const characters = Array.from(text).length;
  return { words, characters, within_limits: (requirement.max_words == null || words <= requirement.max_words) && (requirement.max_characters == null || characters <= requirement.max_characters) };
}
export function applicationCheck(spec, sections = {}) {
  const expected = spec ? (spec.sections.length ? spec.sections : spec.stage !== "full_proposal" ? (starterSections[spec.stage] || []).map(key => ({ key, required: true })) : []) : [];
  const content = key => typeof sections[key] === "string" ? sections[key] : sections[key]?.content || "";
  const missing = expected.filter(section => section.required !== false && !content(section.key).trim()).map(section => section.key);
  const over = Object.keys(sections).filter(key => !lengthCheck(content(key), sectionRequirements(spec, key)).within_limits);
  return { can_finalize_text: !missing.length && !over.length, missing, over };
}
export const attachmentStatuses = spec => Object.fromEntries((spec?.attachments || []).map(item => [item.id, item.status]));
