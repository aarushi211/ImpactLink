import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.js";
import Brand from "../components/Brand";
import "./Organization.css";

export default function Login() {
  const navigate = useNavigate();
  const { login, register, loginWithGoogle } = useAuth();
  const [tab, setTab] = useState("login");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [orgName, setOrgName] = useState("");
  const destination = profile => profile?.onboarding_completed === false ? "/onboarding" : "/dashboard";
  const handleSubmit = async event => {
    event.preventDefault();
    if (loading) return;
    setLoading(true); setError("");
    try {
      if (tab === "register") {
        if (!orgName.trim()) throw new Error("Enter your organization name.");
        await register(email.trim(), password, orgName.trim());
        navigate("/onboarding");
      } else navigate(destination(await login(email.trim(), password)));
    } catch (err) { setError(err?.response?.data?.detail || err.message || "Sign-in failed. Please try again."); }
    finally { setLoading(false); }
  };
  const handleGoogle = async () => {
    if (loading) return;
    setLoading(true); setError("");
    try {
      const result = await loginWithGoogle();
      navigate(result.isNewUser ? "/onboarding" : destination(result.profile));
    } catch (err) { setError(err?.response?.data?.detail || err.message || "Google sign-in failed. Please try again."); }
    finally { setLoading(false); }
  };
  return <main className="org-auth"><div className="org-auth-layout">
    <section className="org-auth-intro"><Brand className="org-brand" /><p className="org-eyebrow">Make room for your mission</p><h1>From an idea to a stronger grant proposal.</h1><p>Find funding opportunities, build your narrative, and plan a budget in one workspace.</p></section>
    <section className="org-auth-card" aria-label="Account access"><div className="org-auth-tabs">{["login", "register"].map(item => <button type="button" key={item} aria-pressed={tab === item} disabled={loading} onClick={() => { setTab(item); setError(""); setPassword(""); }}>{item === "login" ? "Sign in" : "Create account"}</button>)}</div>
      <div className="org-mobile-brand"><Brand /></div>
      <h2>{tab === "login" ? "Welcome back" : "Create your workspace"}</h2><p>{tab === "login" ? "Sign in to pick up where you left off." : "Start with your account. We'll set up your organization next."}</p>
      <button className="org-wide org-google" type="button" disabled={loading} onClick={handleGoogle}>
        <svg width="20" height="20" viewBox="0 0 48 48" aria-hidden="true" focusable="false">
          <path fill="#4285F4" d="M43.61 24.46c0-1.36-.12-2.66-.35-3.92H24.4v7.42h10.77a9.2 9.2 0 0 1-4 6.04v5.02h6.48c3.79-3.49 5.96-8.64 5.96-14.56Z"/>
          <path fill="#34A853" d="M24.4 44c5.4 0 9.92-1.79 13.23-4.98L31.15 34c-1.8 1.21-4.1 1.94-6.75 1.94-5.2 0-9.6-3.51-11.18-8.23H6.54v5.18A20 20 0 0 0 24.4 44Z"/>
          <path fill="#FBBC05" d="M13.22 27.71A12 12 0 0 1 12.6 24c0-1.29.22-2.54.62-3.71v-5.18H6.54A20 20 0 0 0 4.4 24c0 3.23.77 6.29 2.14 8.89l6.68-5.18Z"/>
          <path fill="#EA4335" d="M24.4 12.06c2.94 0 5.57 1.01 7.65 2.99l5.74-5.74A19.24 19.24 0 0 0 24.4 4 20 20 0 0 0 6.54 15.11l6.68 5.18c1.58-4.72 5.98-8.23 11.18-8.23Z"/>
        </svg>
        Continue with Google
      </button><div className="org-divider">or use email</div>
      <form onSubmit={handleSubmit}><fieldset className="org-form-fieldset" disabled={loading}>
        {tab === "register" && <div className="org-field"><label><span>Organization name</span><input required maxLength={200} autoComplete="organization" value={orgName} onChange={e => setOrgName(e.target.value)} placeholder="Your organization's public name" /></label></div>}
        <div className="org-field"><label><span>Work email</span><input type="email" required autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@yourorg.org" /></label></div>
        <div className="org-field"><label><span>Password</span><input type="password" required minLength={tab === "register" ? 6 : undefined} autoComplete={tab === "register" ? "new-password" : "current-password"} value={password} onChange={e => setPassword(e.target.value)} /></label>{tab === "register" && <p className="org-hint">Use at least 6 characters.</p>}</div>
      </fieldset>{error && <p role="alert" className="org-error">{error}</p>}<button type="submit" className="org-primary org-wide" disabled={loading}>{loading ? "Please wait…" : tab === "login" ? "Sign in to ImpactLink" : "Create account & continue"}</button></form>
      <p className="org-hint">{tab === "register" ? "You can add organization details now or return to them later." : "Your proposals and organization settings will be here when you sign in."}</p>
    </section>
  </div></main>;
}
