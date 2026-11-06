import { renderHook, act } from "@testing-library/react";
import useBudget from "./useBudget";
import api from "../services/api";

jest.mock("../services/api", () => ({ __esModule: true, default: { post: jest.fn() } }));

test("cost inputs travel to the API and calculated metadata is retained", async () => {
  const result = { model_version: 2, total_requested: 12000, cost_inputs: { staff: [] }, compliance_summary: { requires_funder_review: true } };
  api.post.mockResolvedValue({ data: result });
  const { result: hook } = renderHook(() => useBudget());
  const inputs = { direct_costs: [{ id: "a", quantity: "2", unit_cost: "6000" }] };
  await act(async () => { await hook.current.generate({}, 15000, inputs); });
  expect(api.post).toHaveBeenCalledWith("/api/budget/generate", { proposal: {}, max_budget: 15000, cost_inputs: inputs });
  expect(hook.current.budget).toEqual(result);
});

test("input validation errors are readable instead of rendering API error objects", async () => {
  api.post.mockRejectedValue({ response: { data: { detail: [{ loc: ["body", "cost_inputs", "staff", 0, "headcount"], msg: "Input should be a valid integer" }] } } });
  const { result } = renderHook(() => useBudget());
  await act(async () => { await result.current.generate({}, 10000, {}); });
  expect(result.current.error).toContain("headcount");
  expect(result.current.error).toContain("valid integer");
});
