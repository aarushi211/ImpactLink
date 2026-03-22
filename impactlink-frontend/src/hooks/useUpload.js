import { useState } from "react";
import { uploadProposal } from "../services/api";
import api from "../services/api";
import { auth } from "../firebase";

/**
 * useUpload — handles PDF upload and saves the result to the work store.
 */
export default function useUpload() {
  const [proposal,   setProposal]   = useState(null);
  const [scoring,    setScoring]    = useState(null);
  const [matches,    setMatches]    = useState([]);
  const [savedId,    setSavedId]    = useState(null); // work-store draft id
  const [loading,    setLoading]    = useState(false);
  const [error,      setError]      = useState(null);

  const upload = async (file) => {
    setLoading(true);
    setError(null);
    setProposal(null);
    setScoring(null);
    setMatches([]);
    setSavedId(null);

    try {
      const data = await uploadProposal(file);

      if (!data.proposal) {
        setError("Upload succeeded but returned no proposal data.");
        return false;
      }

      setProposal(data.proposal);
      setScoring(data.scoring);
      const matchList = data.matches || [];
      setMatches(matchList);

      // Persist in sessionStorage for immediate cross-page access
      sessionStorage.setItem("proposal", JSON.stringify(data.proposal));
      sessionStorage.setItem("scoring",  JSON.stringify(data.scoring));
      sessionStorage.setItem("matches",  JSON.stringify(matchList));

      // Persist to backend if user is logged in
      if (auth.currentUser) {
        const matchIds = matchList.map(m => String(m.grant_id));
        const fileBaseName = file?.name
          ? file.name.replace(/\.(pdf|docx)$/i, "")
          : null;
        const orgName  = data.proposal?.organization_name || "Proposal";
        const title    = fileBaseName || orgName;

        try {
          const initialSections = {};
          if (data.proposal?.raw_text) {
            initialSections["uploaded_content"] = {
              title: "Original Proposal",
              content: data.proposal.raw_text,
              score: 0,
              retries: 0,
              flagged: false,
              approved: true
            };
          }

          const res = await api.post("/api/work/drafts", {
            title,
            grant_title:      "",
            grant_id:         "",
            agency:           "",
            proposal_context: data.proposal,
            matches_id:       matchIds,
            sections:         initialSections,
            section_order:    data.proposal?.raw_text ? ["uploaded_content"] : [],
          });
          const saved = res.data;
          setSavedId(saved.id);
          sessionStorage.setItem("upload_draft_id", saved.id);
        } catch (saveErr) {
          console.warn("Could not save upload to work store:", saveErr);
        }
      }

      return true;
    } catch (err) {
      setError(err.response?.data?.detail || "Upload failed. Is the backend running?");
      return false;
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