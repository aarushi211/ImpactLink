import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Nav } from "../components";
import { useAuth } from "../context/AuthContext.js";
import AiPrivacyNotice from "../components/AiPrivacyNotice";
import OrganizationFields, { OrganizationSection } from "../components/OrganizationFields";
import { organizationForm, organizationUpdates, profileChecklist } from "../utils/organization";
import "./Organization.css";

const sections = [
  ["basics", "Organization", "Your public identity and the mission behind your work."],
  ["programs", "Programs & communities", "Give grant searches and proposal drafting a useful starting point."],
  ["eligibility", "Grant eligibility", "Set defaults for future searches. You can adjust them for each project."],
  ["collaboration", "Collaboration preferences", "Choose whether to make your profile available to potential partners."],
];

function ProfileEditor({ profile }) {
  const navigate = useNavigate();
  const { logout, updateProfile } = useAuth();
  const [form, setForm] = useState(() => organizationForm(profile));
  const [baseline, setBaseline] = useState(() => organizationForm(profile));
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const dirty = JSON.stringify(form) !== JSON.stringify(baseline);
  const checklist = profileChecklist(form);
  const count = checklist.filter(item => item.done).length;
  const change = next => { setForm(next); setSaved(false); setError(""); };
  const handleSave = async event => {
    event.preventDefault();
    if (saving) return;
    setSaving(true); setSaved(false); setError("");
    try {
      const updates = organizationUpdates(form);
      const result = await updateProfile(updates);
      const next = organizationForm(result || updates);
      setForm(next); setBaseline(next); setSaved(true);
    } catch (err) { setError(err?.response?.data?.detail || err.message || "Could not save your changes. Please try again."); }
    finally { setSaving(false); }
  };
  return <div className="org-page"><Nav /><main className="org-shell">
    <p className="org-eyebrow">Organization profile</p>
    <header className="org-hero"><div className="org-identity"><div className="org-avatar" aria-hidden="true">{(profile.org_name || "?").split(/\s+/).slice(0, 2).map(word => word[0]).join("").toUpperCase()}</div><div><h1>{profile.org_name}</h1><p>{profile.email}</p></div></div><div className="org-actions"><button type="button" onClick={() => navigate("/dashboard")}>Back to dashboard</button><button type="button" onClick={logout}>Sign Out</button></div></header>
    <div className="org-layout"><aside className="org-sidebar" aria-label="Profile overview">
      <section className="org-card org-summary"><h2>Your profile at a glance</h2><p className="org-hint"><strong>{count} of {checklist.length}</strong> useful details added</p><progress value={count} max={checklist.length} aria-label="Profile details completed" /><ul>{checklist.map(item => <li key={item.label} data-done={item.done}>{item.done ? "✓" : "○"} {item.label}</li>)}</ul><p className="org-hint">Based on the form below. Save to apply changes.</p></section>
      <nav aria-label="Profile sections">{sections.map(([id, title]) => <a key={id} href={`#${id}`}>{title}</a>)}<a href="#privacy">AI privacy settings</a></nav><p className="org-hint">Keep project-specific budgets, outcomes and timelines in your proposals. This profile describes your organization.</p>
    </aside><form onSubmit={handleSave}><fieldset className="org-form-fieldset" disabled={saving}>
      {sections.map(([id, title, description]) => <OrganizationSection key={id} id={id} title={title} description={description}><OrganizationFields section={id} value={form} onChange={change} /></OrganizationSection>)}
      <OrganizationSection id="privacy" title="AI privacy settings" description="Add names or identifying phrases you want masked before content is sent to AI services."><div className="org-field"><label><span>Names and phrases to mask</span><textarea rows={4} maxLength={20100} value={form.privacy_redaction_terms} onChange={e => change({ ...form, privacy_redaction_terms: e.target.value })} placeholder="One name or identifying phrase per line" /></label><p className="org-hint">2–200 characters per entry, up to 100 entries. Matching ignores case and flexible spacing. Include alternate spellings. These terms are private and excluded from collaborator listings.</p></div></OrganizationSection>
    </fieldset><div className="org-savebar"><div aria-live="polite">{error ? <p role="alert" className="org-error">{error}</p> : saved ? <p role="status" className="org-success">Profile saved.</p> : <p>{dirty ? "You have unsaved changes." : "Your organization details are up to date."}</p>}</div><div className="org-actions"><button type="button" disabled={!dirty || saving} onClick={() => { setForm(baseline); setSaved(false); setError(""); }}>Discard changes</button><button type="submit" className="org-primary" disabled={saving}>{saving ? "Saving…" : "Save Changes"}</button></div></div></form></div>
    <AiPrivacyNotice preview protectedTerms={form.privacy_redaction_terms.split("\n").map(value => value.trim()).filter(Boolean)} />
  </main></div>;
}

export default function Profile() {
  const { profile } = useAuth();
  const navigate = useNavigate();
  if (!profile) return <div className="org-page"><Nav /><main className="org-shell"><h1>Sign in to manage your organization</h1><button onClick={() => navigate("/login")}>Sign In</button></main></div>;
  return <ProfileEditor key={profile.id || profile.email} profile={profile} />;
}
