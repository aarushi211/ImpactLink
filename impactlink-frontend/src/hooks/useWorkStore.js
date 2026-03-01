import { useState, useEffect, useCallback } from "react";
import api from "../services/api";
import { useAuth } from "../context/AuthContext";

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
  const { profile } = useAuth();
  const ngoId = profile?.id;

  const [drafts,  setDrafts]  = useState([]);
  const [builds,  setBuilds]  = useState([]);
  const [budgets, setBudgets] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!ngoId) return;
    setLoading(true);
    try {
      const [dRes, bRes, buRes, sRes] = await Promise.all([
        api.get(`/api/work/drafts/${ngoId}`),
        api.get(`/api/work/builds/${ngoId}`),
        api.get(`/api/work/budgets/${ngoId}`),
        api.get(`/api/work/summary/${ngoId}`),
      ]);
      setDrafts(dRes.data.items   || []);
      setBuilds(bRes.data.items   || []);
      setBudgets(buRes.data.items || []);
      setSummary(sRes.data);
    } catch (e) {
      console.error("useWorkStore refresh error:", e);
    } finally {
      setLoading(false);
    }
  }, [ngoId]);

  useEffect(() => { refresh(); }, [refresh]);

  // All proposals (drafts + builds) newest-first, for page selectors
  const proposals = [
    ...drafts.map(d  => ({ ...d, _type: "draft" })),
    ...builds.map(b  => ({ ...b, _type: "build" })),
  ].sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at));

  // ── Drafts ────────────────────────────────────────────────

  const saveDraft = useCallback(async (payload) => {
    if (!ngoId) return null;
    try {
      const { data } = await api.post("/api/work/drafts", { ngo_id: ngoId, ...payload });
      setDrafts(prev => [data, ...prev].slice(0, 20));
      return data;
    } catch (e) {
      console.error("saveDraft error:", e);
      return null;
    }
  }, [ngoId]);

  const updateDraft = useCallback(async (draftId, sections, budgetId = null) => {
    if (!ngoId) return null;
    try {
      const { data } = await api.patch("/api/work/drafts", {
        ngo_id: ngoId, draft_id: draftId, sections,
        ...(budgetId ? { budget_id: budgetId } : {}),
      });
      setDrafts(prev => prev.map(d => d.id === draftId ? data : d));
      return data;
    } catch (e) {
      console.error("updateDraft error:", e);
      return null;
    }
  }, [ngoId]);

  const deleteDraft = useCallback(async (draftId) => {
    if (!ngoId) return;
    await api.delete(`/api/work/drafts/${ngoId}/${draftId}`);
    setDrafts(prev => prev.filter(d => d.id !== draftId));
  }, [ngoId]);

  // ── Builds ────────────────────────────────────────────────

  const saveBuild = useCallback(async (payload) => {
    if (!ngoId) return null;
    try {
      const { data } = await api.post("/api/work/builds", { ngo_id: ngoId, ...payload });
      setBuilds(prev => [data, ...prev].slice(0, 20));
      return data;
    } catch (e) {
      console.error("saveBuild error:", e);
      return null;
    }
  }, [ngoId]);

  const updateBuild = useCallback(async (buildId, sections, budgetId = null) => {
    if (!ngoId) return null;
    try {
      const { data } = await api.patch("/api/work/builds", {
        ngo_id: ngoId, build_id: buildId, sections,
        ...(budgetId ? { budget_id: budgetId } : {}),
      });
      setBuilds(prev => prev.map(b => b.id === buildId ? data : b));
      return data;
    } catch (e) {
      console.error("updateBuild error:", e);
      return null;
    }
  }, [ngoId]);

  const deleteBuild = useCallback(async (buildId) => {
    if (!ngoId) return;
    await api.delete(`/api/work/builds/${ngoId}/${buildId}`);
    setBuilds(prev => prev.filter(b => b.id !== buildId));
  }, [ngoId]);

  // ── Budgets ───────────────────────────────────────────────

  const saveBudget = useCallback(async (payload) => {
    if (!ngoId) return null;
    try {
      const { data } = await api.post("/api/work/budgets", { ngo_id: ngoId, ...payload });
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
  }, [ngoId]);

  const deleteBudget = useCallback(async (budgetId) => {
    if (!ngoId) return;
    await api.delete(`/api/work/budgets/${ngoId}/${budgetId}`);
    setBudgets(prev => prev.filter(b => b.id !== budgetId));
  }, [ngoId]);

  return {
    drafts, builds, budgets, proposals, summary, loading, refresh,
    saveDraft, updateDraft, deleteDraft,
    saveBuild, updateBuild, deleteBuild,
    saveBudget, deleteBudget,
  };
}