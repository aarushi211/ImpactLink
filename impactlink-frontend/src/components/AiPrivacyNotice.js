import { useEffect, useRef, useState } from "react";
import api from "../services/api";

export default function AiPrivacyNotice({ preview = false, counts, protectedTerms }) {
  const [text, setText] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const requestSequence = useRef(0);
  const termsKey = JSON.stringify(protectedTerms ?? null);
  useEffect(() => {
    requestSequence.current += 1;
    setResult(null);
    setLoading(false);
  }, [termsKey]);
  const matches = Object.entries(counts || {}).filter(([, count]) => count > 0);
  const scan = async () => {
    const request = ++requestSequence.current;
    setLoading(true); setError(""); setResult(null);
    try {
      const response = await api.post("/api/privacy/preview", { text, ...(protectedTerms !== undefined ? { custom_terms: protectedTerms } : {}) });
      if (request === requestSequence.current) setResult(response.data);
    } catch (err) {
      if (request === requestSequence.current) setError(typeof err?.response?.data?.detail === "string" ? err.response.data.detail : "Could not preview redaction. Please try again.");
    }
    finally { if (request === requestSequence.current) setLoading(false); }
  };
  return <details aria-label="AI privacy disclaimer" style={{ margin: "24px 0 0", padding: "12px 0", border: 0, borderTop: "1px solid var(--border)", color: "#888", fontSize: 11, lineHeight: 1.6 }}>
    <summary style={{ cursor: "pointer", color: "#bbb" }}>AI privacy · local name detection and identifier masking; originals saved in the app</summary>
    <p>AI features send relevant proposal text, profile details and your instructions to the configured AI provider. We combine local English person-name detection, identifier patterns and your saved names or phrases to mask. Detection runs on the app server before the AI request.</p>
    <p>Automatic checks can still miss names, addresses and sensitive narratives or mask harmless text. Add known identifiers to the private list in Profile, preview the result and remove remaining confidential case details. Saved terms apply across your account's AI features. AI processing stops if the local name model or privacy settings cannot be loaded.</p>
    <p>Original uploads and saved text remain in the app's storage. Review AI drafts for placeholders before submitting them.</p>
    <p>Optional API response storage is disabled. Provider retention policies still apply. <a href="https://developers.openai.com/api/docs/guides/your-data" target="_blank" rel="noopener noreferrer">OpenAI data controls</a></p>
    {matches.length > 0 && <p role="status">Detected in this upload: {matches.map(([kind, count]) => `${kind.replace(/_/g, " ")}: ${count}`).join(", ")}. The AI copy was masked; your original was retained.</p>}
    {preview && <div>
      <label style={{ display: "block" }}>Preview what the detector masks<textarea aria-label="Text to preview for AI" value={text} maxLength={50000} disabled={loading} onChange={event => { setText(event.target.value); setResult(null); }} style={{ display: "block", width: "100%", minHeight: 80, boxSizing: "border-box", padding: 10, color: "#ddd", background: "#111120", border: "1px solid var(--border)", borderRadius: 6 }} /></label>
      <p>This preview runs on the app server without calling the AI or saving the preview text.</p>
      <button disabled={!text.trim() || loading} onClick={scan}>{loading ? "Checking…" : "Preview AI redaction"}</button>
      {error && <p role="alert">{error}</p>}
      {result && <div><p>Detected matches: {Object.entries(result.counts || {}).map(([kind, count]) => `${kind.replace(/_/g, " ")}: ${count}`).join(", ") || "none"}. Review any text that remains.</p><pre aria-label="Redacted preview" style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", color: "#ddd" }}>{result.text}</pre></div>}
    </div>}
  </details>;
}
