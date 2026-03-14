import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Nav } from "../components";
import useUpload from "../hooks/useUpload";
import { useAuth } from "../context/AuthContext";

export default function Upload() {
  const navigate = useNavigate();
  const { profile } = useAuth();
  const { upload, loading, error } = useUpload();
  const [dragOver, setDragOver] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const inputRef = useRef();

  const handleFile = (file) => {
    if (!file) return;
    if (!file.name.match(/\.(pdf|docx)$/i)) {
      alert("Please upload a PDF or DOCX file.");
      return;
    }
    setSelectedFile(file);
  };

  const handleSubmit = async () => {
    if (!selectedFile) return;
    const ok = await upload(selectedFile, profile?.id);
    // Only navigate if the upload was successful and we have real data
    if (ok) navigate("/grants");
  };

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)" }}>
      <Nav />
      <div style={{ maxWidth: 680, margin: "0 auto", padding: "60px 40px" }}>

        <div style={{ marginBottom: 36 }}>
          <p style={{ color: "var(--accent)", fontSize: 13, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", marginBottom: 6 }}>
            Mission Brain
          </p>
          <h1 style={{ fontSize: 32, fontWeight: 800, letterSpacing: "-0.03em", color: "#fff", margin: "0 0 8px" }}>
            Upload Your Proposal
          </h1>
          <p style={{ color: "var(--text-muted)", fontSize: 15 }}>
            Our AI will parse your mission, match grants, and score your application readiness.
          </p>
        </div>

        {/* Drop Zone */}
        <div
          onClick={() => !selectedFile && inputRef.current.click()}
          onDragOver={e => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={e => {
            e.preventDefault();
            setDragOver(false);
            handleFile(e.dataTransfer.files[0]);
          }}
          style={{
            border: `2px dashed ${dragOver ? "var(--accent)" : selectedFile ? "var(--green)" : "var(--border)"}`,
            borderRadius: 16, padding: "52px 40px",
            textAlign: "center", cursor: selectedFile ? "default" : "pointer",
            background: dragOver ? "#0f0f1e" : "var(--bg-card)",
            transition: "all 0.2s",
            marginBottom: 16,
          }}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".pdf,.docx"
            style={{ display: "none" }}
            onChange={e => handleFile(e.target.files[0])}
          />

          {selectedFile ? (
            <>
              <p style={{ fontSize: 36, marginBottom: 12 }}>📄</p>
              <p style={{ fontWeight: 700, color: "var(--green)", fontSize: 16, marginBottom: 4 }}>{selectedFile.name}</p>
              <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
                {(selectedFile.size / 1024).toFixed(1)} KB ·{" "}
                <span
                  onClick={e => { e.stopPropagation(); setSelectedFile(null); }}
                  style={{ color: "var(--red)", cursor: "pointer", textDecoration: "underline" }}
                >
                  Remove
                </span>
              </p>
            </>
          ) : (
            <>
              <p style={{ fontSize: 36, marginBottom: 12 }}>⬆</p>
              <p style={{ fontWeight: 700, color: "#fff", fontSize: 16, marginBottom: 6 }}>
                Drop your proposal here
              </p>
              <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
                PDF or DOCX · Max 20MB · or click to browse
              </p>
            </>
          )}
        </div>

        {/* Error */}
        {error && (
          <div style={{
            background: "#2d0f0f", border: "1px solid #7f1d1d",
            borderRadius: 10, padding: "12px 16px", marginBottom: 16,
            color: "var(--red)", fontSize: 13,
          }}>
            ⚠ {error}
          </div>
        )}

        {/* Submit */}
        <button
          onClick={handleSubmit}
          disabled={!selectedFile || loading}
          style={{
            width: "100%",
            background: selectedFile && !loading ? "var(--accent)" : "#1a1a2e",
            border: "none", color: selectedFile && !loading ? "#fff" : "#444",
            padding: "14px", borderRadius: 12,
            fontSize: 15, fontWeight: 700,
            cursor: selectedFile && !loading ? "pointer" : "not-allowed",
            transition: "all 0.2s",
          }}
        >
          {loading ? "⏳ Analyzing proposal..." : "✦ Analyze & Match Grants"}
        </button>

        {/* What happens next */}
        {!selectedFile && (
          <div style={{ marginTop: 36 }}>
            <p style={{ color: "#444", fontSize: 12, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 16 }}>
              What happens next
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {[
                { icon: "◎", label: "Parse",   desc: "AI extracts your mission, beneficiaries, SDGs, and cause area" },
                { icon: "✦", label: "Match",   desc: "Vector search finds the most relevant grants from our database" },
                { icon: "◈", label: "Score",   desc: "LLM scores your proposal readiness and gives improvement tips" },
                { icon: "✍", label: "Explain", desc: "RAG explains why each grant matches your specific mission" },
              ].map((step, i) => (
                <div key={i} style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
                  <div style={{
                    width: 32, height: 32, borderRadius: 8, flexShrink: 0,
                    background: "#1a1a2e", border: "1px solid var(--border)",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 14, color: "var(--accent)",
                  }}>
                    {step.icon}
                  </div>
                  <div>
                    <p style={{ fontWeight: 700, color: "#fff", fontSize: 13, margin: "0 0 2px" }}>{step.label}</p>
                    <p style={{ color: "var(--text-muted)", fontSize: 12, margin: 0 }}>{step.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}