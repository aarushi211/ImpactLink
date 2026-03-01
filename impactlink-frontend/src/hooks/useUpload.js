import { useState } from "react";
import { uploadProposal } from "../services/api";
import api from "../services/api";

/**
 * useUpload — handles PDF upload and saves the result to the work store.
 *
 * After a successful upload we persist a "draft" record (no sections yet)
 * that carries:
 *   proposal_context  — the parsed proposal object
 *   matches_id        — array of matched grant_ids
 *
 * This lets Draft, Budget, and GrantsList pages reload the same context
 * from the DB instead of relying on ephemeral sessionStorage.
 */
export default function useUpload() {
  const [proposal,   setProposal]   = useState(null);
  const [scoring,    setScoring]    = useState(null);
  const [matches,    setMatches]    = useState([]);
  const [savedId,    setSavedId]    = useState(null); // work-store draft id
  const [loading,    setLoading]    = useState(false);
  const [error,      setError]      = useState(null);

  const upload = async (file, ngoId = null) => {
    setLoading(true);
    setError(null);
    setProposal(null);
    setScoring(null);
    setMatches([]);
    setSavedId(null);

    try {
      const data = await uploadProposal(file);
      setProposal(data.proposal);
      setScoring(data.scoring);
      const matchList = data.matches || [];
      setMatches(matchList);

      // Always persist in sessionStorage for immediate cross-page access
      sessionStorage.setItem("proposal", JSON.stringify(data.proposal));
      sessionStorage.setItem("scoring",  JSON.stringify(data.scoring));
      sessionStorage.setItem("matches",  JSON.stringify(matchList));

      // Persist to backend so this upload appears in Saved Work
      if (ngoId) {
        const matchIds   = matchList.map(m => String(m.grant_id));
        const orgName    = data.proposal?.organization_name || "Proposal";
        const causeArea  = data.proposal?.cause_area || "";
        const title      = `${orgName}${causeArea ? ` — ${causeArea}` : ""}`;

        try {
          const res = await api.post("/api/work/drafts", {
            ngo_id:           ngoId,
            title,
            grant_title:      "",
            grant_id:         "",
            agency:           "",
            proposal_context: data.proposal,
            matches_id:       matchIds,
            sections:         {},
            section_order:    [],
          });
          const saved = res.data;
          setSavedId(saved.id);
          // Store the draft id so Draft page can link back to it
          sessionStorage.setItem("upload_draft_id", saved.id);
        } catch (saveErr) {
          console.warn("Could not save upload to work store:", saveErr);
        }
      }
    } catch (err) {
      setError(err.response?.data?.detail || "Upload failed. Is the backend running?");
    } finally {
      setLoading(false);
    }
  };

  const reset = () => {
    setProposal(null);
    setScoring(null);
    setMatches([]);
    setSavedId(null);
    setError(null);
    sessionStorage.removeItem("proposal");
    sessionStorage.removeItem("scoring");
    sessionStorage.removeItem("matches");
    sessionStorage.removeItem("upload_draft_id");
  };

  return { upload, proposal, scoring, matches, savedId, loading, error, reset };
}