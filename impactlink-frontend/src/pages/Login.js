// src/pages/Login.js
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.js";

const SDG_OPTIONS = [
  "SDG 1: No Poverty", "SDG 2: Zero Hunger", "SDG 3: Good Health",
  "SDG 4: Quality Education", "SDG 5: Gender Equality", "SDG 6: Clean Water",
  "SDG 7: Clean Energy", "SDG 8: Decent Work", "SDG 10: Reduced Inequalities",
  "SDG 11: Sustainable Cities", "SDG 13: Climate Action", "SDG 17: Partnerships",
];

const CAUSE_AREAS = [
  "Education & Youth", "Health & Wellbeing", "Economic Empowerment",
  "Environment & Climate", "Women & Gender", "Food Security",
  "Humanitarian Aid", "Human Rights", "Community Development",
  "Arts & Culture", "Technology & Innovation",
];

// ── small reusable field ──────────────────────────────────────
function Field({ label, children, hint }) {
  return (
    <div style={{ marginBottom: 18 }}>
      <label style={{
        display: "block", color: "#888", fontSize: 11,
        fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em",
        marginBottom: 6
      }}>
        {label}
        {hint && <span style={{
          color: "#444", fontWeight: 400,
          textTransform: "none", letterSpacing: 0, marginLeft: 6
        }}>({hint})</span>}
      </label>
      {children}
    </div>
  );
}

const inputStyle = {
  width: "100%", background: "#111120",
  border: "1px solid #1e1e30", borderRadius: 8,
  color: "#e0e0f0", padding: "10px 12px",
  fontSize: 13, outline: "none",
  boxSizing: "border-box",
};

export default function Login() {
  const navigate = useNavigate();
  // Hooks must be inside the component
  const { login, register, updateProfile, loginWithGoogle } = useAuth();

  // tab: "login" | "register"
  const [tab, setTab] = useState("login");
  const [step, setStep] = useState(1);   // register = 2-step
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Login fields
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  // Register step 1
  const [orgName, setOrgName] = useState("");
  const [regEmail, setRegEmail] = useState("");
  const [regPass, setRegPass] = useState("");

  // Register step 2 — profile enrichment
  const [mission, setMission] = useState("");
  const [location, setLocation] = useState("");
  const [causeArea, setCauseArea] = useState("");
  const [website, setWebsite] = useState("");
  const [teamSize, setTeamSize] = useState("");
  const [geoFocus, setGeoFocus] = useState("");
  const [selSDGs, setSelSDGs] = useState([]);

  const toggleSDG = (s) =>
    setSelSDGs(prev => prev.includes(s) ? prev.filter(x => x !== s) : [...prev, s]);

  // ── Login submit ──────────────────────────────────────────
  const handleLogin = async (e) => {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      await login(email, password);
      navigate("/dashboard");
    } catch (err) {
      setError(err.message || "Login failed.");
    } finally { setLoading(false); }
  };

  // ── Register step 1 → 2 ──────────────────────────────────
  const handleStep1 = (e) => {
    e.preventDefault();
    if (!orgName.trim() || !regEmail.trim() || regPass.length < 6) {
      setError("Please fill all fields. Password must be 6+ characters.");
      return;
    }
    setError("");
    setStep(2);
  };

  // ── Register step 2 submit ────────────────────────────────
  const handleRegister = async (e) => {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      await register(regEmail, regPass, orgName);

      if (mission || location || causeArea) {
        await updateProfile({
          mission, location, cause_area: causeArea,
          website, team_size: teamSize,
          geographic_focus: geoFocus ? [geoFocus] : [],
          sdgs: selSDGs,
        });
      }
      navigate("/dashboard");
    } catch (err) {
      setError(err.message || "Registration failed.");
    } finally { setLoading(false); }
  };

  // ── Google Login Handler ──────────────────────────────────
  const handleGoogleLogin = async () => {
    setError(""); setLoading(true);
    try {
      const result = await loginWithGoogle();

      if (result.isNewUser) {
        // It's a brand new Google account! 
        // Pre-fill the organization name and jump straight to Step 2
        setOrgName(result.profile.org_name);
        setTab("register");
        setStep(2);
      } else {
        // Existing user, redirect directly to the dashboard
        navigate("/dashboard");
      }
    } catch (err) {
      setError(err.message || "Google sign-in failed.");
    } finally { setLoading(false); }
  };

  // ── Reusable Google Button UI ──────────────────────────────
  const renderGoogleButton = (text) => (
    <>
      <button
        type="button"
        onClick={handleGoogleLogin}
        disabled={loading}
        style={{
          width: "100%", padding: "12px 0",
          background: "#ffffff", border: "1px solid #ddd", borderRadius: 10,
          color: "#333", fontSize: 14, fontWeight: 700,
          cursor: loading ? "wait" : "pointer",
          display: "flex", alignItems: "center", justifyContent: "center", gap: 10
        }}>
        <svg width="18" height="18" viewBox="0 0 24 24">
          <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
          <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
          <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
          <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
        </svg>
        {text}
      </button>

      <div style={{ display: "flex", alignItems: "center", gap: 10, margin: "16px 0" }}>
        <div style={{ flex: 1, height: 1, background: "#1e1e30" }}></div>
        <span style={{ color: "#555", fontSize: 12, fontWeight: 600 }}>OR</span>
        <div style={{ flex: 1, height: 1, background: "#1e1e30" }}></div>
      </div>
    </>
  );

  // ── render ────────────────────────────────────────────────

  return (
    <div style={{
      minHeight: "100vh", background: "var(--bg)",
      display: "flex", alignItems: "center", justifyContent: "center",
      padding: 24,
    }}>
      {/* Left decorative panel — hidden on small screens */}
      <div style={{
        width: 420, marginRight: 60, flexShrink: 0,
        display: "flex", flexDirection: "column", gap: 20,
      }}
        className="hide-mobile"
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
          <span style={{ fontSize: 28 }}>⊚</span>
          <span style={{ fontWeight: 800, fontSize: 22, color: "#fff", letterSpacing: "-0.02em" }}>
            ImpactLink AI
          </span>
        </div>
        <h2 style={{
          fontSize: 38, fontWeight: 800, color: "#fff",
          letterSpacing: "-0.03em", lineHeight: 1.15, margin: 0
        }}>
          One platform for<br />
          <span style={{ color: "var(--accent)" }}>smarter funding.</span>
        </h2>
        <p style={{ color: "#555", fontSize: 14, lineHeight: 1.8, margin: 0, maxWidth: 340 }}>
          Find matching grants, draft winning proposals with AI,
          and connect with NGOs working on the same mission.
        </p>

        <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 8 }}>
          {[
            { icon: "✦", text: "AI grant matching from 150+ real sources" },
            { icon: "✍", text: "Proposal drafting agents tailored per funder" },
            { icon: "💰", text: "Locality-aware budget builder" },
            { icon: "🤝", text: "NGO collaboration network (coming soon)" },
          ].map(f => (
            <div key={f.text} style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span style={{ color: "var(--accent)", fontSize: 14, width: 20, textAlign: "center" }}>
                {f.icon}
              </span>
              <span style={{ color: "#666", fontSize: 13 }}>{f.text}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Auth card */}
      <div style={{
        width: "100%", maxWidth: 460,
        background: "var(--bg-card)", border: "1px solid var(--border)",
        borderRadius: 16, padding: "32px 36px",
      }}>
        {/* Tabs */}
        <div style={{
          display: "flex", marginBottom: 28,
          background: "#0a0a0f", borderRadius: 10, padding: 4,
        }}>
          {["login", "register"].map(t => (
            <button
              key={t}
              onClick={() => { setTab(t); setStep(1); setError(""); }}
              style={{
                flex: 1, padding: "9px 0",
                background: tab === t ? "var(--accent)" : "transparent",
                border: "none", borderRadius: 8,
                color: tab === t ? "#fff" : "#555",
                fontSize: 13, fontWeight: 700, cursor: "pointer",
                transition: "all 0.15s", textTransform: "capitalize",
              }}
            >
              {t === "login" ? "Sign In" : "Create Account"}
            </button>
          ))}
        </div>

        {/* ── LOGIN FORM ─────────────────────────────── */}
        {tab === "login" && (
          <div style={{ display: "flex", flexDirection: "column" }}>
            {renderGoogleButton("Sign in with Google")}

            <form onSubmit={handleLogin}>
              <Field label="Email">
                <input
                  style={inputStyle} type="email" required
                  value={email} onChange={e => setEmail(e.target.value)}
                  placeholder="you@yourorg.org"
                />
              </Field>
              <Field label="Password">
                <input
                  style={inputStyle} type="password" required
                  value={password} onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••"
                />
              </Field>

              {error && <p style={{ color: "var(--red)", fontSize: 12, margin: "0 0 14px" }}>⚠ {error}</p>}

              <button type="submit" disabled={loading} style={{
                width: "100%", padding: "12px 0",
                background: loading ? "#1a1a28" : "var(--accent)",
                border: "none", borderRadius: 10,
                color: loading ? "#333" : "#fff",
                fontSize: 14, fontWeight: 700,
                cursor: loading ? "wait" : "pointer",
              }}>
                {loading ? "Signing in…" : "Sign In →"}
              </button>

              <p style={{ color: "#444", fontSize: 12, textAlign: "center", margin: "16px 0 0" }}>
                No account?{" "}
                <span
                  onClick={() => { setTab("register"); setError(""); }}
                  style={{ color: "var(--accent)", cursor: "pointer", fontWeight: 600 }}
                >
                  Create one free
                </span>
              </p>
            </form>
          </div>
        )}

        {/* ── REGISTER STEP 1 ──────────────────────── */}
        {tab === "register" && step === 1 && (
          <div style={{ display: "flex", flexDirection: "column" }}>
            <div style={{ marginBottom: 20 }}>
              <p style={{ margin: "0 0 4px", fontWeight: 700, color: "#fff", fontSize: 16 }}>
                Create your NGO account
              </p>
              <p style={{ margin: 0, color: "#444", fontSize: 12 }}>Step 1 of 2 — Account basics</p>
            </div>

            {renderGoogleButton("Sign up with Google")}

            <form onSubmit={handleStep1}>
              <Field label="Organization Name">
                <input
                  style={inputStyle} required
                  value={orgName} onChange={e => setOrgName(e.target.value)}
                  placeholder="Amara Foundation"
                />
              </Field>
              <Field label="Email">
                <input
                  style={inputStyle} type="email" required
                  value={regEmail} onChange={e => setRegEmail(e.target.value)}
                  placeholder="you@yourorg.org"
                />
              </Field>
              <Field label="Password" hint="min. 6 characters">
                <input
                  style={inputStyle} type="password" required
                  value={regPass} onChange={e => setRegPass(e.target.value)}
                  placeholder="••••••••"
                />
              </Field>

              {error && <p style={{ color: "var(--red)", fontSize: 12, margin: "0 0 14px" }}>⚠ {error}</p>}

              <button type="submit" style={{
                width: "100%", padding: "12px 0",
                background: "var(--accent)", border: "none", borderRadius: 10,
                color: "#fff", fontSize: 14, fontWeight: 700, cursor: "pointer",
              }}>
                Continue →
              </button>
            </form>
          </div>
        )}

        {/* ── REGISTER STEP 2 ──────────────────────── */}
        {tab === "register" && step === 2 && (
          <form onSubmit={handleRegister} style={{ maxHeight: "60vh", overflowY: "auto", paddingRight: 4 }}>
            <div style={{ marginBottom: 20 }}>
              <p style={{ margin: "0 0 4px", fontWeight: 700, color: "#fff", fontSize: 16 }}>
                Tell us about {orgName}
              </p>
              <p style={{ margin: 0, color: "#444", fontSize: 12 }}>
                Step 2 of 2 — Used for grant matching & NGO collaboration
              </p>
            </div>

            <Field label="Mission Statement" hint="optional">
              <textarea
                style={{ ...inputStyle, resize: "none", minHeight: 72 }}
                value={mission} onChange={e => setMission(e.target.value)}
                placeholder="Empowering youth through digital literacy…"
              />
            </Field>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
              <Field label="Location" hint="City, Country">
                <input
                  style={inputStyle}
                  value={location} onChange={e => setLocation(e.target.value)}
                  placeholder="Nairobi, Kenya"
                />
              </Field>
              <Field label="Team Size">
                <select
                  style={{ ...inputStyle, cursor: "pointer" }}
                  value={teamSize} onChange={e => setTeamSize(e.target.value)}
                >
                  <option value="">Select…</option>
                  {["1–5", "6–15", "16–50", "51–200", "200+"].map(s => (
                    <option key={s} value={s}>{s} people</option>
                  ))}
                </select>
              </Field>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
              <Field label="Cause Area">
                <select
                  style={{ ...inputStyle, cursor: "pointer" }}
                  value={causeArea} onChange={e => setCauseArea(e.target.value)}
                >
                  <option value="">Select…</option>
                  {CAUSE_AREAS.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </Field>
              <Field label="Primary Region">
                <input
                  style={inputStyle}
                  value={geoFocus} onChange={e => setGeoFocus(e.target.value)}
                  placeholder="Sub-Saharan Africa"
                />
              </Field>
            </div>

            <Field label="Website" hint="optional">
              <input
                style={inputStyle}
                value={website} onChange={e => setWebsite(e.target.value)}
                placeholder="https://yourorg.org"
              />
            </Field>

            <Field label="SDG Alignment" hint="select all that apply">
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 2 }}>
                {SDG_OPTIONS.map(sdg => {
                  const active = selSDGs.includes(sdg);
                  return (
                    <button
                      key={sdg} type="button"
                      onClick={() => toggleSDG(sdg)}
                      style={{
                        background: active ? "var(--accent)" : "#111120",
                        border: `1px solid ${active ? "var(--accent)" : "#1e1e30"}`,
                        color: active ? "#fff" : "#555",
                        borderRadius: 20, padding: "4px 10px",
                        fontSize: 11, cursor: "pointer",
                        transition: "all 0.12s",
                      }}
                    >
                      {sdg.split(":")[0]}
                    </button>
                  );
                })}
              </div>
            </Field>

            {error && <p style={{ color: "var(--red)", fontSize: 12, margin: "0 0 14px" }}>⚠ {error}</p>}

            <div style={{ display: "flex", gap: 10 }}>
              <button
                type="button"
                onClick={() => { setStep(1); setError(""); }}
                style={{
                  flex: 1, padding: "12px 0",
                  background: "transparent", border: "1px solid var(--border)",
                  borderRadius: 10, color: "#888",
                  fontSize: 13, fontWeight: 600, cursor: "pointer",
                }}
              >
                ← Back
              </button>
              <button type="submit" disabled={loading} style={{
                flex: 2, padding: "12px 0",
                background: loading ? "#1a1a28" : "var(--accent)",
                border: "none", borderRadius: 10,
                color: loading ? "#333" : "#fff",
                fontSize: 14, fontWeight: 700,
                cursor: loading ? "wait" : "pointer",
              }}>
                {loading ? "Creating account…" : "Create Account →"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}