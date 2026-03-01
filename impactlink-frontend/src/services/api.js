import axios from "axios";

const api = axios.create({
  baseURL: process.env.REACT_APP_API_URL || "http://localhost:8000",
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

export default api;