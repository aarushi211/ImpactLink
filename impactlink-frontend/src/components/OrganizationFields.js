import StateSelect from "./StateSelect";
import { APPLICANT_TYPES, CAUSE_AREAS, SDGS } from "../utils/organization";

function Field({ label, hint, children }) {
  return <div className="org-field"><label><span>{label}</span>{children}</label>{hint && <p className="org-hint">{hint}</p>}</div>;
}

export function OrganizationSection({ id, title, description, children, titleRef }) {
  return <section id={id} className="org-card"><header><h2 ref={titleRef} tabIndex={titleRef ? -1 : undefined}>{title}</h2>{description && <p>{description}</p>}</header>{children}</section>;
}

export default function OrganizationFields({ section, value, onChange }) {
  const change = (key, next) => onChange({ ...value, [key]: next });
  const input = (key, props = {}) => <input value={value[key]} onChange={e => change(key, e.target.value)} {...props} />;
  const text = (key, props = {}) => <textarea rows={3} maxLength={5000} value={value[key]} onChange={e => change(key, e.target.value)} {...props} />;
  if (section === "basics") return <>
    <Field label="Organization name">{input("org_name", { required: true, maxLength: 200, autoComplete: "organization", placeholder: "Your organization's public name" })}</Field>
    <Field label="Mission statement" hint="Describe the change you work toward and who benefits. This gives proposal drafting useful context.">{text("mission", { placeholder: "We help rural communities restore local watersheds through education and hands-on conservation." })}</Field>
    <div className="org-grid">
      <Field label="Headquarters / location">{input("location", { maxLength: 200, placeholder: "City, state / region, country" })}</Field>
      <Field label="Website (optional)">{input("website", { maxLength: 500, autoComplete: "url", placeholder: "https://yourorg.org" })}</Field>
      <Field label="Year founded (optional)">{input("founding_year", { type: "number", min: 1800, max: new Date().getFullYear(), placeholder: "2018" })}</Field>
      <Field label="Team size (optional)"><select value={value.team_size} onChange={e => change("team_size", e.target.value)}><option value="">Not specified</option>{[...new Set(["1–5", "6–15", "16–50", "51–200", "200+", value.team_size].filter(Boolean))].map(size => <option key={size} value={size}>{size} people</option>)}</select></Field>
    </div>
  </>;
  if (section === "programs") return <>
    <Field label="Primary focus area"><select value={value.cause_area} onChange={e => change("cause_area", e.target.value)}><option value="">Not specified</option>{[...new Set([...CAUSE_AREAS, value.cause_area].filter(Boolean))].map(area => <option key={area}>{area}</option>)}</select></Field>
    <Field label="Key programs and activities" hint="One program or activity per line. Be specific about what your organization does.">{text("key_activities", { placeholder: "After-school science clubs\nWetland restoration and volunteer training" })}</Field>
    <Field label="Communities served" hint="One group per line. Use general descriptions; avoid individual participant names.">{text("target_beneficiaries", { placeholder: "Students in underserved public schools\nFamilies in rural communities" })}</Field>
    <Field label="Service areas" hint="One city, region or country per line. Keep every area where you operate.">{text("geographic_focus", { placeholder: "Northern California\nOregon" })}</Field>
    <fieldset className="org-options"><legend>SDG alignment (optional)</legend><p className="org-hint">Select the goals relevant to your work.</p><div className="org-sdgs">{[...new Set([...SDGS, ...value.sdgs])].map(sdg => <label key={sdg}><input type="checkbox" checked={value.sdgs.includes(sdg)} onChange={e => change("sdgs", e.target.checked ? [...value.sdgs, sdg] : value.sdgs.filter(item => item !== sdg))} /><span>{sdg}</span></label>)}</div></fieldset>
  </>;
  if (section === "eligibility") return <>
    <Field label="Applicant type" hint="Select the entity that will apply. This is self-reported and does not verify legal or tax status."><select aria-label="Applicant type" value={value.applicant_type} onChange={e => change("applicant_type", e.target.value)}><option value="">Not specified / unsure</option>{Object.entries(APPLICANT_TYPES).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></Field>
    <div className="org-field"><span className="org-label">Default project U.S. states</span><StateSelect value={value.project_states} onChange={next => change("project_states", next)} /><p className="org-hint">Where funded work will take place. Leave blank for work outside the U.S. or if unknown. You can change these filters for each grant search.</p></div>
    <div className="org-callout">These defaults help filter grants. Each funder's complete eligibility rules still need to be reviewed for your application.</div>
  </>;
  if (section === "collaboration") return <>
    <label className="org-check"><input type="checkbox" checked={value.collab_open} onChange={e => change("collab_open", e.target.checked)} /><span>Open to collaboration with other organizations</span></label>
    <p className="org-hint">Enabling this makes your organization profile available through collaborator listings. Private masking terms are excluded.</p>
    <Field label="Collaboration interests" hint="Separate interests with commas.">{input("collab_interests", { disabled: !value.collab_open, maxLength: 1000, placeholder: "Joint proposals, program delivery, evaluation" })}</Field>
  </>;
  return null;
}
