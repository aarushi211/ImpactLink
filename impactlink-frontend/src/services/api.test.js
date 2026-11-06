import { TextDecoder, TextEncoder } from "util";
import api, { advanceSessionStream } from "./api";

jest.mock("../firebase", () => ({ auth: { currentUser: null } }));
jest.mock("axios", () => ({
  create: () => ({ defaults: { baseURL: "http://localhost:8000" }, interceptors: { request: { use: jest.fn() } } }),
}));

const encoder = new TextEncoder();
const originalFetch = global.fetch;
global.TextDecoder = TextDecoder;
const flush = async () => { for (let i = 0; i < 12; i += 1) await Promise.resolve(); };

beforeEach(() => { jest.useFakeTimers(); api.defaults.baseURL = "http://localhost:8000"; });
afterEach(() => { jest.useRealTimers(); global.fetch = originalFetch; });

function controlledStream() {
  let deliver;
  const reader = {
    read: jest.fn(() => new Promise(resolve => { deliver = resolve; })),
    cancel: jest.fn().mockResolvedValue(),
    releaseLock: jest.fn(),
  };
  global.fetch = jest.fn().mockResolvedValue({ ok: true, body: { getReader: () => reader } });
  return {
    reader,
    send: async (text, done = false) => {
      deliver({ value: encoder.encode(text), done });
      await flush();
    },
  };
}

test("heartbeats keep a draft alive beyond five minutes and progress is delivered", async () => {
  const stream = controlledStream();
  const progress = jest.fn();
  const result = advanceSessionStream("session", { confirmed: true }, jest.fn(), progress);
  await flush();
  await stream.send('data: {"type":"progress","message":"Drafting sections..."}\n\n');
  for (let i = 0; i < 7; i += 1) {
    jest.advanceTimersByTime(60_000);
    await stream.send(": keep-alive\n\n");
  }
  expect(global.fetch.mock.calls[0][1].signal.aborted).toBe(false);
  await stream.send('data: {"type":"complete","response":{"gate":"draft_');
  await stream.send('review","session_id":"session"}}\n\n');
  await stream.send("", true);
  await expect(result).resolves.toEqual({ gate: "draft_review", session_id: "session" });
  expect(progress).toHaveBeenCalledWith({ type: "progress", message: "Drafting sections..." });
  expect(stream.reader.releaseLock).toHaveBeenCalled();
});

test("an idle connection times out with session recovery guidance", async () => {
  global.fetch = jest.fn((url, { signal }) => new Promise((resolve, reject) => {
    signal.addEventListener("abort", () => reject(new Error("aborted")));
  }));
  const result = advanceSessionStream("session");
  const rejected = expect(result).rejects.toThrow("check its status before starting another draft");
  jest.advanceTimersByTime(90_001);
  await rejected;
});

test("server errors reject cleanly and release the stream", async () => {
  const stream = controlledStream();
  const result = advanceSessionStream("session");
  const rejected = expect(result).rejects.toThrow("Draft generation failed");
  await flush();
  await stream.send('data: {"type":"error","message":"Draft generation failed"}\n\n');
  await rejected;
  expect(stream.reader.cancel).toHaveBeenCalled();
});

test("Firebase Hosting's root API base uses a same-origin stream URL", async () => {
  const stream = controlledStream();
  api.defaults.baseURL = "/";
  const result = advanceSessionStream("session");
  await flush();
  expect(global.fetch.mock.calls[0][0]).toBe("/api/session/session/advance/stream");
  await stream.send('data: {"type":"complete","response":{"gate":"draft_review"}}\n\n');
  await stream.send("", true);
  await expect(result).resolves.toEqual({ gate: "draft_review" });
});

test("section lifecycle and interleaved token events reach their callbacks", async () => {
  const stream = controlledStream();
  const tokens = jest.fn(), sections = jest.fn();
  const result = advanceSessionStream("session", {}, tokens, jest.fn(), sections);
  await flush();
  await stream.send('data: {"type":"section_start","section_key":"summary","title":"Summary"}\n\n');
  await stream.send('data: {"type":"token","section_key":"summary","content":"Our "}\n\ndata: {"type":"token","section_key":"budget","content":"$100"}\n\n');
  await stream.send('data: {"type":"section_complete","section_key":"summary","section":{"content":"Reviewed text"}}\n\n');
  await stream.send('data: {"type":"complete","response":{"gate":"draft_review"}}\n\n', true);
  await result;
  expect(tokens.mock.calls).toEqual([["summary", "Our "], ["budget", "$100"]]);
  expect(sections).toHaveBeenCalledWith(expect.objectContaining({ type: "section_start", section_key: "summary" }));
  expect(sections).toHaveBeenCalledWith(expect.objectContaining({ type: "section_complete", section: { content: "Reviewed text" } }));
});
