import { useState, useCallback, useEffect } from "react";
import { createSession, advanceSession, getSessionStatus } from "../services/api";

/**
 * useProposalSession — Managed state for a Gated Proposal Flow.
 * 
 * Flow Types: "improve" or "scratch"
 * Gates: "gap_review", "slot_filling", "slot_confirm", "draft_review", "final_save", "complete"
 */
export default function useProposalSession(initialSessionId = null) {
  const [sessionId, setSessionId] = useState(initialSessionId);
  const [gate, setGate]           = useState("none");
  const [data, setData]           = useState({});
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState(null);

  // Sync state from a backend response (GateResponse)
  const _sync = useCallback((res) => {
    if (res.session_id) setSessionId(res.session_id);
    if (res.gate)       setGate(res.gate);
    
    // Merge res into data, but keep useful stuff
    setData(prev => ({
      ...prev,
      ...res,
      // For convenience, flatten sections if present
      sections: res.sections || prev.sections || {},
      slots:    res.slots    || prev.slots    || {},
      analysis: res.analysis || prev.analysis || null,
    }));
  }, []);

  const start = async (flowType, grant, profile, originalSections = {}) => {
    setLoading(true);
    setError(null);
    try {
      const res = await createSession(flowType, grant, profile, originalSections);
      _sync(res);
      return res.session_id;
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Failed to start session");
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const advance = async (userInput = {}) => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await advanceSession(sessionId, userInput);
      _sync(res);
      return res;
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Failed to advance session");
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const refresh = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    try {
      const res = await getSessionStatus(sessionId);
      _sync(res);
    } catch (err) {
      setError("Failed to refresh session status");
    } finally {
      setLoading(false);
    }
  }, [sessionId, _sync]);

  // Re-hydrate if sessionId changes (e.g. from URL param)
  useEffect(() => {
    if (initialSessionId && !sessionId) {
      setSessionId(initialSessionId);
    }
  }, [initialSessionId, sessionId]);

  useEffect(() => {
    if (sessionId && gate === "none") {
      refresh();
    }
  }, [sessionId, gate, refresh]);

  return {
    sessionId,
    gate,
    data,
    loading,
    error,
    start,
    advance,
    refresh,
    setGate,
    setData,
    reset: () => {
      setSessionId(null);
      setGate("none");
      setData({});
      setError(null);
    }
  };
}
