import { useState, useEffect } from "react";
import { removeDemoGrants } from "../services/grants";

export default function useGrants() {
  const [grants,      setGrants]   = useState([]);
  const [proposal,    setProposal] = useState(null);
  const [hasRealData, setHasReal]  = useState(false);
  const [loading,     setLoading]  = useState(true);

  useEffect(() => {
    let matches = [];
    let storedProposal = null;

    try {
      matches = JSON.parse(sessionStorage.getItem("matches") || "[]");
      if (!Array.isArray(matches)) {
        throw new TypeError("Stored grant matches must be an array.");
      }
    } catch (error) {
      console.error("Could not load stored grant matches.", error);
      sessionStorage.removeItem("matches");
      matches = [];
    }

    const realMatches = removeDemoGrants(matches);
    if (realMatches.length !== matches.length) {
      sessionStorage.setItem("matches", JSON.stringify(realMatches));
    }

    try {
      const proposal = sessionStorage.getItem("proposal");
      storedProposal = proposal ? JSON.parse(proposal) : null;
    } catch (error) {
      console.error("Could not load the stored proposal.", error);
      sessionStorage.removeItem("proposal");
    }

    setGrants(realMatches);
    setProposal(storedProposal);
    setHasReal(realMatches.length > 0);
    setLoading(false);
  }, []);

  return { grants, proposal, hasRealData, loading };
}