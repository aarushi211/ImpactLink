import { act, renderHook, waitFor } from "@testing-library/react";
import useWorkStore from "./useWorkStore";
import api from "../services/api";
jest.mock("../services/api", () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn(), patch: jest.fn() } }));

beforeEach(() => {
  api.get.mockImplementation(async path => ({ data: path.includes("/builds/") ? { builds: [{ id: "b1", title: "Saved build", proposal_context: { primary_mission: "Restore creeks" } }] } : path.includes("/drafts/") ? { drafts: [{ id: "d1", title: "Saved revision" }] } : { budgets: [] } }));
  api.patch.mockImplementation(async (path, payload) => ({ data: { ...payload, id: path.split("/").pop() } }));
});

test.each([["updateBuild", "builds", "b1"], ["updateDraft", "drafts", "d1"]])("%s updates the existing record and its matcher context", async (method, type, id) => {
  const { result } = renderHook(() => useWorkStore());
  await waitFor(() => expect(result.current.loading).toBe(false));
  await act(async () => { await result.current[method](id, { summary: { content: "Latest proposal text" } }); });
  expect(api.patch).toHaveBeenCalledWith(`/api/work/${type}/${id}`, expect.objectContaining({ proposal_context: expect.objectContaining({ sections: { summary: { title: "summary", content: "Latest proposal text" } } }) }));
  expect(result.current[type]).toHaveLength(1);
  expect(api.post).not.toHaveBeenCalled();
});
