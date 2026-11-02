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
    flow: flowType,
    grant: grant,
    profile: profile,
    original_sections: originalSections,
  });
  return res.data; // { session_id, gate }
};

/**
 * advanceSession moves the session forward with user input (e.g. gap confirmation, slot answer).
 */
export const advanceSession = async (sessionId, userInput = {}) => {
  const res = await api.post(`/api/session/${sessionId}/advance`, userInput, {
    timeout: 300_000, // 5 minutes — rewrite_sections can take 60–120s
  });
  return res.data; // GateResponse
};

export const advanceSessionStream = async (sessionId, userInput = {}, onToken = () => {}) => {
  const headers = { "Content-Type": "application/json" };
  if (auth.currentUser) {
    headers.Authorization = `Bearer ${await auth.currentUser.getIdToken()}`;
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 300_000);
  try {
    const response = await fetch(
      `${api.defaults.baseURL}/api/session/${sessionId}/advance/stream`,
      {
        method: "POST",
        headers,
        body: JSON.stringify(userInput),
        signal: controller.signal,
      }
    );
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || "Draft generation failed.");
    }
    if (!response.body) {
      throw new Error("Streaming is not supported by this browser.");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let result = null;

    const processEvent = (eventText) => {
      const data = eventText
        .split("\n")
        .filter(line => line.startsWith("data:"))
        .map(line => line.slice(5).trim())
        .join("\n");
      if (!data) return;

      const event = JSON.parse(data);
      if (event.type === "token") {
        onToken(event.section_key, event.content);
      } else if (event.type === "error") {
        throw new Error(event.message || "Draft generation failed.");
      } else if (event.type === "complete") {
        result = event.response;
      }
    };

    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        processEvent(buffer.slice(0, boundary));
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf("\n\n");
      }
      if (done) break;
    }

    if (buffer.trim()) processEvent(buffer);
    if (!result) throw new Error("Draft stream ended before completion.");
    return result;
  } finally {
    clearTimeout(timeout);
  }
};

/**
 * getSessionStatus re-hydrates the frontend state (e.g. after refresh).
 */
export const getSessionStatus = async (sessionId) => {
  const res = await api.get(`/api/session/${sessionId}`);
  return res.data;
};

/** Revise a single section with user feedback (SectionRewriteAgent). */
export const reviseSection = async (currentDraft, feedback, sectionTitle = "Proposal Section") => {
  const res = await api.post("/api/build/revise", {
    current_draft: currentDraft,
    feedback,
    section_title: sectionTitle,
  });
  return res.data;
};

export default api;