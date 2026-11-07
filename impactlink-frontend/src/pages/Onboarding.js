import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import OrganizationFields, { OrganizationSection } from "../components/OrganizationFields";
import { organizationForm, organizationUpdates } from "../utils/organization";
import "./Organization.css";
import Brand from "../components/Brand";

const STEPS = [
  { key: "basics", label: "Organization", title: "First, introduce your organization", description: "Check your organization name, then add a little background. All other details are optional." },
  { key: "programs", label: "Your work", title: "Tell us about the work you do", description: "Add programs, communities and service areas. You can refine these later." },
  { key: "eligibility", label: "Grant preferences", title: "Set a starting point for grant searches", description: "Choose the applicant type and project states you know. Leave anything uncertain unspecified." },
];

export default function Onboarding() {
  const { profile, updateProfile } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState(() => organizationForm(profile || {}));
  const [step, setStep] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const heading = useRef(null);
  const current = STEPS[step];
  const save = async (later = false) => {
    if (saving) return;
    setSaving(true); setError("");
    try {
      const updates = organizationUpdates(form);
      await updateProfile({ ...updates, onboarding_completed: !later && step === STEPS.length - 1 });
      if (later || step === STEPS.length - 1) navigate("/dashboard");
      else { setStep(value => value + 1); heading.current?.focus(); }
    } catch (err) { setError(err?.response?.data?.detail || err.message || "Could not save your setup. Please try again."); }
    finally { setSaving(false); }
  };
  return <div className="org-page"><main className="org-onboarding"><Brand className="org-brand" />
    <header className="org-hero"><div><p className="org-eyebrow">Your organization workspace</p><h1>Let's get to know your mission.</h1><p>A few useful details now. A better starting point for every application.</p></div><p className="org-hint">Signed in as {profile?.email}</p></header>
    <ol className="org-steps" aria-label="Setup progress">{STEPS.map((item, index) => <li key={item.key} aria-current={index === step ? "step" : undefined} data-done={index < step}>{index < step ? "✓" : index + 1} · {item.label}</li>)}</ol>
    <div className="org-layout"><aside className="org-welcome"><p className="org-eyebrow">Step {step + 1} of {STEPS.length}</p><h2>Build a foundation you can reuse.</h2><p>Your profile provides background for matching and writing. Each proposal can still have its own goals, location and budget.</p><ol><li>Introduce your organization</li><li>Describe your programs</li><li>Set grant search defaults</li></ol><p>Progress is saved when you continue. You can update everything from your profile.</p></aside>
      <form onSubmit={e => { e.preventDefault(); save(); }}>
        <fieldset className="org-form-fieldset" disabled={saving}><OrganizationSection titleRef={heading} title={current.title} description={current.description}><OrganizationFields section={current.key} value={form} onChange={next => { setForm(next); setError(""); }} /></OrganizationSection></fieldset>
        {error && <p role="alert" className="org-error">{error}</p>}
        <div className="org-savebar"><button type="button" disabled={saving} onClick={() => save(true)}>Save & finish later</button><div className="org-actions">{step > 0 && <button type="button" disabled={saving} onClick={() => { setStep(value => value - 1); setError(""); }}>Back</button>}<button type="submit" className="org-primary" disabled={saving}>{saving ? "Saving…" : step === STEPS.length - 1 ? "Finish setup" : "Save & continue"}</button></div></div>
        <p className="org-hint">Only your organization name is required. Leave unknown details blank; you can add them later.</p>
      </form>
    </div>
  </main></div>;
}
