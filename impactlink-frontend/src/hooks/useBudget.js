import { useState, useCallback } from "react";
import api from "../services/api";

/**
 * useBudget — manages the full budget lifecycle
 *
 * generate(proposal, maxBudget)  → calls POST /api/budget/generate
 * refine(currentBudget, message) → calls POST /api/budget/refine
 *
 * State:
 *   budget      – { items: [...], total_requested, locality_explanation } | null
 *   loading     – "generating" | "refining" | null
 *   error       – string | null
 */
export default function useBudget() {
  const [budget,  setBudget]  = useState(null);
  const [loading, setLoading] = useState(null);   // "generating" | "refining" | null
  const [error,   setError]   = useState(null);

  const generate = useCallback(async (proposal, maxBudget) => {
    setLoading("generating");
    setError(null);
    setBudget(null);
    try {
      const { data } = await api.post("/api/budget/generate", {
        proposal,
        max_budget: maxBudget,
      });
      setBudget(data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Failed to generate budget.");
    } finally {
      setLoading(null);
    }
  }, []);

  const refine = useCallback(async (currentBudget, userRequest) => {
    setLoading("refining");
    setError(null);
    try {
      const { data } = await api.post("/api/budget/refine", {
        current_budget: currentBudget,
        user_request:   userRequest,
      });
      setBudget(data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Failed to refine budget.");
    } finally {
      setLoading(null);
    }
  }, []);

  const reset = useCallback(() => {
    setBudget(null);
    setError(null);
    setLoading(null);
  }, []);

  return { budget, loading, error, generate, refine, reset };
}