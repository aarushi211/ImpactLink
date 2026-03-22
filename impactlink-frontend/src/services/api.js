import axios from "axios";
import { auth } from "../firebase";

const api = axios.create({
  baseURL: process.env.REACT_APP_API_URL || "http://localhost:8000",
});

// Request interceptor: attach Firebase ID Token to every outgoing request
api.interceptors.request.use(async (config) => {
  const user = auth.currentUser;
  if (user) {
    const token = await user.getIdToken();
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
}, (error) => {
  return Promise.reject(error);
});

// Upload PDF → returns { proposal, scoring, matches }
export const uploadProposal = async (file) => {
  const formData = new FormData();
  formData.append("file", file);
  const res = await api.post("/api/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data;
};

// Get matches for already-parsed proposal
export const getMatches = async (proposal, topK = 5) => {
  const res = await api.post("/api/match", { proposal, top_k: topK });
  return res.data;
};

// Score a proposal
export const scoreProposal = async (proposal) => {
  const res = await api.post("/api/score", { proposal });
  return res.data;
};

// Generate a localized line-item budget
export const generateBudget = async (proposal, maxBudget) => {
  const res = await api.post("/api/budget/generate", { proposal, max_budget: maxBudget });
  return res.data;
};

// Refine an existing budget via plain-English chat
export const refineBudget = async (currentBudget, userRequest) => {
  const res = await api.post("/api/budget/refine", { current_budget: currentBudget, user_request: userRequest });
  return res.data;
};

// ── Unified Session API ──────────────────────────────────────────────────────

/**
 * createSession starts a gated proposal flow ("improve" or "scratch").
 */
export const createSession = async (flowType, grant, profile, originalSections = {}) => {
  const res = await api.post("/api/session", {
    flow:              flowType,
    grant:             grant,
    profile:           profile,
    original_sections: originalSections,
  });
  return res.data; // { session_id, gate }
};

/**
 * advanceSession moves the session forward with user input (e.g. gap confirmation, slot answer).
 */
export const advanceSession = async (sessionId, userInput = {}) => {
  const res = await api.post(`/api/session/${sessionId}/advance`, userInput);
  return res.data; // GateResponse
};

/**
 * getSessionStatus re-hydrates the frontend state (e.g. after refresh).
 */
export const getSessionStatus = async (sessionId) => {
  const res = await api.get(`/api/session/${sessionId}`);
  return res.data;
};

export default api;