const asArray = value => Array.isArray(value) ? value : value ? [value] : [];

export function proposalContext(item, profile = {}) {
  const base = item.proposal_context || {};
  const source = Object.keys(item.sections || {}).length ? item.sections : base.sections || {};
  const sections = Object.fromEntries(Object.entries(source).map(([key, value]) => [key,
    typeof value === "string" ? { title: key.replace(/_/g, " "), content: value } : { title: value.title || key, content: value.content || "" },
  ]));
  return {
    ...base,
    organization_name: base.organization_name || item.org_name || profile.org_name || "",
    project_title: item.title || base.project_title || "Grant Proposal",
    primary_mission: base.primary_mission || base.mission || profile.mission || "",
    cause_area: base.cause_area || profile.cause_area || "",
    geographic_focus: asArray(base.geographic_focus || profile.geographic_focus || profile.location),
    key_activities: asArray(base.key_activities || profile.key_activities),
    sdg_alignment: asArray(base.sdg_alignment || base.sdgs || profile.sdgs),
    sections,
    raw_text: Object.keys(sections).length
      ? Object.values(sections).map(section => `${section.title}\n${section.content}`).join("\n\n")
      : base.raw_text || "",
  };
}

export function stageProposalMatch(item, profile = {}) {
  const context = proposalContext(item, profile);
  sessionStorage.setItem("proposal", JSON.stringify(context));
  sessionStorage.setItem("grant_match_request", JSON.stringify({
    id: item.id || null, title: item.title || context.project_title,
    _type: item._type || "build", proposal_context: context, sections: context.sections,
  }));
  if (item.id) sessionStorage.setItem("upload_draft_id", item.id);
  else sessionStorage.removeItem("upload_draft_id");
  sessionStorage.setItem("grants_searchMode", "filter");
  return item.id ? `/grants?proposal=${encodeURIComponent(item.id)}` : "/grants";
}

export function workItemPath(item) {
  const id = encodeURIComponent(item.id);
  switch (item._type || item.type) {
    case "build": return `/build?load=${id}`;
    case "budget": return `/budget?load=${id}`;
    case "grant": return `/grants/${encodeURIComponent(item.grant_id || item.id)}`;
    default: return `/draft?load=${id}${item.grant_id ? `&grant=${encodeURIComponent(item.grant_id)}` : ""}`;
  }
}
