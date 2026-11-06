import { render, screen, fireEvent, act } from "@testing-library/react";
import Budget from "./Budget";

const mockSaved = { id: "bu1", title: "Restoration budget", max_budget: 10000, total_requested: 9000, locality_explanation: "Local restoration costs", items: [{ category: "Training", amount: 9000, description: "Volunteer training" }] };
const mockBudget = { budget: null, loading: null, error: null, generate: jest.fn(), refine: jest.fn(), reset: jest.fn() };
const mockSaveBudget = jest.fn();
const mockUpdateBudget = jest.fn();
const mockWork = { budgets: [mockSaved], proposals: [], saveBudget: mockSaveBudget, updateBudget: mockUpdateBudget };
jest.mock("react-router-dom", () => ({ useNavigate: () => jest.fn(), useSearchParams: () => [new URLSearchParams("load=bu1")] }), { virtual: true });
jest.mock("../hooks/useBudget", () => () => mockBudget);
jest.mock("../hooks/useWorkStore", () => () => mockWork);
jest.mock("../hooks/useGrants", () => () => ({ grants: [], proposal: null }));
jest.mock("../components", () => ({ Nav: () => null }));
jest.mock("../context/AuthContext", () => ({ useAuth: () => ({ profile: { org_name: "Demo" } }) }));

test("a reopened budget is viewable and refinable without generating or saving a duplicate", async () => {
  Element.prototype.scrollIntoView = jest.fn();
  mockBudget.budget = null;
  mockBudget.refine.mockResolvedValue();
  mockUpdateBudget.mockImplementation(async (id, payload) => ({ id, ...payload }));
  const { rerender } = render(<Budget />);
  expect(screen.getByText("Volunteer training")).toBeInTheDocument();
  const chat = screen.getByPlaceholderText(/Move \$5k/);
  expect(chat).not.toBeDisabled();
  await act(async () => {
    fireEvent.change(chat, { target: { value: "Add equipment" } });
    fireEvent.keyDown(chat, { key: "Enter" });
  });
  expect(mockBudget.refine).toHaveBeenCalledWith(mockSaved, "Add equipment");
  mockBudget.budget = { ...mockSaved, total_requested: 9500 };
  await act(async () => { rerender(<Budget />); });
  expect(mockUpdateBudget).toHaveBeenCalledWith("bu1", expect.objectContaining({ total_requested: 9500 }));
  expect(mockSaveBudget).not.toHaveBeenCalled();
  expect(mockBudget.generate).not.toHaveBeenCalled();
});
