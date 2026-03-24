import { useState, useEffect, useCallback } from "react";
import api from "../services/api";

/**
 * useWorkStore — fetches and manages saved drafts, builds, budgets.
 *
 * Key design:
 *  - drafts / builds / budgets  — typed arrays
 *  - proposals                  — drafts + builds merged, newest-first
 *                                 used by Draft + Budget page selectors
 *  - summary                    — counts + recent items for Dashboard
 */
export default function useWorkStore() {
  // Note: auth token is passed automatically via api.js interceptor

  const [drafts,  setDrafts]  = useState([]);
  const [builds,  setBuilds]  = useState([]);
  const [budgets, setBudgets] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [dRes, bRes, buRes, sRes] = await Promise.all([
        api.get("/api/work/drafts/me"),
        api.get("/api/work/builds/me"),
        api.get("/api/work/budgets/me"),
        api.get("/api/work/summary/me"),
      ]);
      setDrafts(dRes.data.drafts   || []);
      setBuilds(bRes.data.builds   || []);
      setBudgets(buRes.data.budgets || []);
      setSummary(sRes.data);
    } catch (e) {
      console.error("useWorkStore refresh error:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  // All proposals (drafts + builds) newest-first, for page selectors
  const proposals = [
    ...drafts.map(d  => ({ ...d, _type: "draft" })),
    ...builds.map(b  => ({ ...b, _type: "build" })),
  ].sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at));

  // ── Drafts ────────────────────────────────────────────────

  const saveDraft = useCallback(async (payload) => {
    try {
      const { data } = await api.post("/api/work/drafts", { ...payload });
      setDrafts(prev => [data, ...prev].slice(0, 20));
      return data;
    } catch (e) {
      console.error("saveDraft error:", e);
      return null;
    }
  }, []);

  const updateDraft = useCallback(async (draftId, sections, budgetId = null) => {
    try {
      const { data } = await api.patch("/api/work/drafts", {
        draft_id: draftId, sections,
        ...(budgetId ? { budget_id: budgetId } : {}),
      });
      setDrafts(prev => prev.map(d => d.id === draftId ? data : d));
      return data;
    } catch (e) {
      console.error("updateDraft error:", e);
      return null;
    }
  }, []);

  const deleteDraft = useCallback(async (draftId) => {
    await api.delete(`/api/work/drafts/${draftId}`);
    setDrafts(prev => prev.filter(d => d.id !== draftId));
  }, []);

  // ── Builds ────────────────────────────────────────────────

  const saveBuild = useCallback(async (payload) => {
    try {
      const { data } = await api.post("/api/work/builds", { ...payload });
      setBuilds(prev => [data, ...prev].slice(0, 20));
      return data;
    } catch (e) {
      console.error("saveBuild error:", e);
      return null;
    }
  }, []);

  const updateBuild = useCallback(async (buildId, sections, budgetId = null) => {
    try {
      const { data } = await api.patch("/api/work/builds", {
        build_id: buildId, sections,
        ...(budgetId ? { budget_id: budgetId } : {}),
      });
      setBuilds(prev => prev.map(b => b.id === buildId ? data : b));
      return data;
    } catch (e) {
      console.error("updateBuild error:", e);
      return null;
    }
  }, []);

  const deleteBuild = useCallback(async (buildId) => {
    await api.delete(`/api/work/builds/${buildId}`);
    setBuilds(prev => prev.filter(b => b.id !== buildId));
  }, []);

  // ── Budgets ───────────────────────────────────────────────

  const saveBudget = useCallback(async (payload) => {
    try {
      const { data } = await api.post("/api/work/budgets", { ...payload });
      setBudgets(prev => [data, ...prev].slice(0, 20));
      // Back-link: update parent proposal's budget_id in local state
      if (data.proposal_id) {
        setDrafts(prev => prev.map(d =>
          d.id === data.proposal_id ? { ...d, budget_id: data.id } : d));
        setBuilds(prev => prev.map(b =>
          b.id === data.proposal_id ? { ...b, budget_id: data.id } : b));
      }
      return data;
    } catch (e) {
      console.error("saveBudget error:", e);
      return null;
    }
  }, []);

  const deleteBudget = useCallback(async (budgetId) => {
    await api.delete(`/api/work/budgets/${budgetId}`);
    setBudgets(prev => prev.filter(b => b.id !== budgetId));
  }, []);

  return {
    drafts, builds, budgets, proposals, summary, loading, refresh,
    saveDraft, updateDraft, deleteDraft,
    saveBuild, updateBuild, deleteBuild,
    saveBudget, deleteBudget,
  };
}