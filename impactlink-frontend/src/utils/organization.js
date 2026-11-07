export const CAUSE_AREAS = ["Education & Youth", "Health & Wellbeing", "Economic Empowerment", "Environment & Climate", "Women & Gender", "Food Security", "Humanitarian Aid", "Human Rights", "Community Development", "Arts & Culture", "Technology & Innovation"];
export const SDGS = ["No Poverty", "Zero Hunger", "Good Health", "Quality Education", "Gender Equality", "Clean Water", "Clean Energy", "Decent Work", "Industry, Innovation and Infrastructure", "Reduced Inequalities", "Sustainable Cities", "Responsible Consumption and Production", "Climate Action", "Life Below Water", "Life on Land", "Peace, Justice and Strong Institutions", "Partnerships"].map((name, i) => `SDG ${i + 1}: ${name}`);
export const APPLICANT_TYPES = { nonprofit: "Nonprofit", public_agency: "Public agency", tribal_government: "Tribal government", business: "Business", individual: "Individual", other_legal_entity: "Other legal entity" };
const lines = value => [...new Set(value.split("\n").map(item => item.trim()).filter(Boolean))];

export function organizationForm(profile = {}) {
  return {
    org_name: profile.org_name || "", mission: profile.mission || "", location: profile.location || "",
    website: profile.website || "", founding_year: profile.founding_year ?? "", team_size: profile.team_size || "",
    cause_area: profile.cause_area || "", geographic_focus: (profile.geographic_focus || []).join("\n"),
    key_activities: (profile.key_activities || []).join("\n"), target_beneficiaries: (profile.target_beneficiaries || []).join("\n"),
    applicant_type: profile.applicant_type || "", project_states: (profile.project_states || []).join(", "),
    sdgs: profile.sdgs || [], collab_open: profile.collab_open ?? false,
    collab_interests: (profile.collab_interests || []).join(", "),
    privacy_redaction_terms: (profile.privacy_redaction_terms || []).join("\n"),
  };
}

export function organizationUpdates(form) {
  if (!form.org_name.trim()) throw new Error("Enter your organization name.");
  const year = form.founding_year === "" ? null : Number(form.founding_year);
  if (year !== null && (!Number.isInteger(year) || year < 1800 || year > new Date().getFullYear())) throw new Error("Enter a valid founding year, or leave it blank.");
  let website = form.website.trim();
  if (website) {
    if (!/^[a-z][a-z\d+.-]*:/i.test(website)) website = `https://${website}`;
    let url;
    try { url = new URL(website); } catch (_) { throw new Error("Enter a valid website, such as https://yourorg.org."); }
    if (!["http:", "https:"].includes(url.protocol) || !url.hostname.includes(".") || url.username || url.password) throw new Error("Enter a public HTTP or HTTPS website without login credentials.");
  }
  return {
    org_name: form.org_name.trim(), mission: form.mission.trim(), location: form.location.trim(), website,
    founding_year: year, team_size: form.team_size, cause_area: form.cause_area,
    geographic_focus: lines(form.geographic_focus), key_activities: lines(form.key_activities),
    target_beneficiaries: lines(form.target_beneficiaries), applicant_type: form.applicant_type,
    project_states: [...new Set(form.project_states.split(/[,;|]/).map(item => item.trim()).filter(Boolean))],
    sdgs: form.sdgs, collab_open: form.collab_open,
    collab_interests: [...new Set(form.collab_interests.split(",").map(item => item.trim()).filter(Boolean))],
    privacy_redaction_terms: lines(form.privacy_redaction_terms),
  };
}

export function profileChecklist(form) {
  return [
    { label: "Organization name", done: Boolean(form.org_name.trim()) },
    { label: "Mission statement", done: Boolean(form.mission.trim()) },
    { label: "Focus area", done: Boolean(form.cause_area) },
    { label: "Programs and activities", done: Boolean(form.key_activities.trim()) },
    { label: "Communities served", done: Boolean(form.target_beneficiaries.trim()) },
    { label: "Service areas", done: Boolean(form.geographic_focus.trim() || form.project_states) },
    { label: "Applicant type", done: Boolean(form.applicant_type) },
  ];
}
