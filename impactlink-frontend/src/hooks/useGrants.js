import { useState, useEffect } from "react";

export default function useGrants() {
  const [grants,      setGrants]   = useState([]);
  const [proposal,    setProposal] = useState(null);
  const [hasRealData, setHasReal]  = useState(false);
  const [loading,     setLoading]  = useState(true);

  useEffect(() => {
    const storedMatches  = sessionStorage.getItem("matches");
    const storedProposal = sessionStorage.getItem("proposal");

    if (storedMatches) {
      try {
        setGrants(JSON.parse(storedMatches));
        setProposal(storedProposal ? JSON.parse(storedProposal) : null);
        setHasReal(true);
      } catch (_) {}
      setLoading(false);
    } else {
      import("../services/mockData").then(m => {
        setGrants(m.mockGrants);
        setProposal(m.mockProfile);
        setHasReal(false);
        setLoading(false);
      });
    }
  }, []);

  return { grants, proposal, hasRealData, loading };
}