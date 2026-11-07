import { act, renderHook } from "@testing-library/react";
import useProposalSession from "./useProposalSession";
import { createSession, advanceSession, advanceSessionStream, getSessionStatus } from "../services/api";

jest.mock("../services/api", () => ({
  createSession: jest.fn(), advanceSession: jest.fn(), advanceSessionStream: jest.fn(), getSessionStatus: jest.fn(),
}));

beforeEach(() => jest.resetAllMocks());

test("opening a saved session restores review without generating another draft", async () => {
  getSessionStatus.mockResolvedValue({ session_id: "saved-session", gate: "draft_review", sections: { summary: { content: "Saved draft" } } });
  const { result } = renderHook(() => useProposalSession("saved-session"));
  await act(async () => {});
  expect(result.current.gate).toBe("draft_review");
  expect(result.current.data.sections.summary.content).toBe("Saved draft");
  expect(createSession).not.toHaveBeenCalled();
  expect(advanceSession).not.toHaveBeenCalled();
});

test("a timeout keeps the session recoverable and refresh restores the completed draft", async () => {
  createSession.mockResolvedValue({ session_id: "saved-session", gate: "slot_confirm" });
  advanceSession.mockRejectedValue(Object.assign(new Error("timeout"), { code: "ECONNABORTED" }));
  getSessionStatus.mockResolvedValue({ session_id: "saved-session", gate: "draft_review", sections: { summary: { content: "Saved draft" } } });
  const { result } = renderHook(() => useProposalSession());
  await act(async () => { await result.current.start("scratch", {}, {}); });
  await act(async () => { await result.current.advance({ confirmed: true }).catch(() => {}); });
  expect(result.current.sessionId).toBe("saved-session");
  expect(result.current.error).toContain("backend may still be working");
  await act(async () => { await result.current.refresh(); });
  expect(result.current.gate).toBe("draft_review");
  expect(result.current.data.sections.summary.content).toBe("Saved draft");
  expect(result.current.error).toBeNull();
  expect(advanceSession).toHaveBeenCalledTimes(1);
});

test("stream failures preserve the current gate and surface an error", async () => {
  createSession.mockResolvedValue({ session_id: "saved-session", gate: "slot_confirm" });
  advanceSessionStream.mockRejectedValue(new Error("Connection interrupted"));
  const { result } = renderHook(() => useProposalSession());
  await act(async () => { await result.current.start("scratch", {}, {}); });
  await act(async () => { await result.current.advanceStream({ confirmed: true }).catch(() => {}); });
  expect(result.current.gate).toBe("slot_confirm");
  expect(result.current.error).toBe("Connection interrupted");
  expect(result.current.loading).toBe(false);
});

test("checking a running session keeps recovery guidance without resubmitting", async () => {
  createSession.mockResolvedValue({ session_id: "saved-session", gate: "slot_confirm" });
  getSessionStatus.mockResolvedValue({ session_id: "saved-session", gate: "slot_confirm", running: true });
  const { result } = renderHook(() => useProposalSession());
  await act(async () => { await result.current.start("scratch", {}, {}); });
  await act(async () => { await result.current.refresh(); });
  expect(result.current.data.running).toBe(true);
  expect(result.current.error).toContain("draft is still running");
  expect(advanceSession).not.toHaveBeenCalled();
  expect(advanceSessionStream).not.toHaveBeenCalled();
});

test("temporary database failure preserves the session and a later status check recovers it", async () => {
  getSessionStatus.mockRejectedValueOnce({ response: { status: 503, data: { detail: "Database temporarily unavailable. Check the saved session status again." } } });
  const { result } = renderHook(() => useProposalSession("saved-session"));
  await act(async () => {});
  expect(result.current.sessionId).toBe("saved-session");
  expect(result.current.error).toContain("Database temporarily unavailable");
  getSessionStatus.mockResolvedValue({ session_id: "saved-session", gate: "draft_review", sections: { summary: { content: "Already generated draft" } } });
  await act(async () => { await result.current.refresh(); });
  expect(result.current.data.sections.summary.content).toBe("Already generated draft");
  expect(result.current.error).toBeNull();
  expect(advanceSession).not.toHaveBeenCalled();
  expect(advanceSessionStream).not.toHaveBeenCalled();
});
