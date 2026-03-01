import { useState } from "react";

/**
 * useDraft — streams proposal sections from /api/draft/stream.
 * Saving is handled by the Draft page via useWorkStore after streaming completes.
 *
 * draft(proposal, grant)   — start streaming
 * sections / sectionOrder / activeSection / loading / done / error / reset
 */
export default function useDraft() {
  const [sections,      setSections]      = useState({});
  const [sectionOrder,  setSectionOrder]  = useState([]);
  const [activeSection, setActiveSection] = useState(null);
  const [loading,       setLoading]       = useState(false);
  const [done,          setDone]          = useState(false);
  const [error,         setError]         = useState(null);

  const draft = async (proposal, grant) => {
    setLoading(true);
    setDone(false);
    setError(null);
    setSections({});
    setSectionOrder([]);
    setActiveSection(null);

    try {
      const res = await fetch(
        `${process.env.REACT_APP_API_URL || "http://localhost:8000"}/api/draft/stream`,
        {
          method:  "POST",
          headers: { "Content-Type": "application/json" },
          body:    JSON.stringify({ proposal, grant }),
        }
      );
      if (!res.ok) throw new Error(`Server error: ${res.status}`);

      const reader  = res.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { value, done: streamDone } = await reader.read();
        if (streamDone) break;

        const lines = decoder.decode(value).split("\n").filter(Boolean);
        for (const line of lines) {
          try {
            const chunk = JSON.parse(line);
            if (chunk.done) {
              setDone(true);
              setActiveSection(null);
              setLoading(false);
              return;
            }
            setActiveSection(chunk.key);
            setSections(prev => ({
              ...prev,
              [chunk.key]: { title: chunk.title, content: chunk.content },
            }));
            setSectionOrder(prev =>
              prev.includes(chunk.key) ? prev : [...prev, chunk.key]
            );
          } catch (_) {}
        }
      }
    } catch (err) {
      setError(err.message || "Draft failed. Is the backend running?");
    } finally {
      setLoading(false);
    }
  };

  const reset = () => {
    setSections({});
    setSectionOrder([]);
    setActiveSection(null);
    setDone(false);
    setError(null);
  };

  return { draft, sections, sectionOrder, activeSection, loading, done, error, reset };
}