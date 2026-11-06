import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import Budget from "./Budget";
jest.mock("../services/api", () => ({ __esModule: true, default: { post: jest.fn() } }));

const mockSaved = { id: "bu1", title: "Restoration budget", max_budget: 10000, total_requested: 9000, locality_explanation: "Local restoration costs", items: [{ category: "Training", amount: 9000, description: "Volunteer training" }] };
const mockBudget = { budget: null, loading: null, error: null, generate: jest.fn(), refine: jest.fn(), reset: jest.fn() };
const mockSaveBudget = jest.fn();
const mockUpdateBudget = jest.fn();
const mockWork = { budgets: [mockSaved], proposals: [], saveBudget: mockSaveBudget, updateBudget: mockUpdateBudget };
let mockQuery = "load=bu1";
let mockGrants = [];
jest.mock("react-router-dom", () => ({ useNavigate: () => jest.fn(), useSearchParams: () => [new URLSearchParams(mockQuery)] }), { virtual: true });
jest.mock("../hooks/useBudget", () => () => mockBudget);
jest.mock("../hooks/useWorkStore", () => () => mockWork);
jest.mock("../hooks/useGrants", () => () => ({ grants: mockGrants, proposal: null }));
jest.mock("../components", () => ({ Nav: () => null }));
jest.mock("../context/AuthContext", () => ({ useAuth: () => ({ profile: { org_name: "Demo" } }) }));

beforeEach(() => {
  sessionStorage.clear();
  Element.prototype.scrollIntoView = jest.fn();
  mockQuery = "load=bu1";
  mockGrants = [];
  mockBudget.budget = null;
  mockBudget.loading = null;
  mockBudget.error = null;
  mockBudget.generate.mockResolvedValue();
  mockSaveBudget.mockImplementation(async payload => ({ ...payload, id: "new-budget" }));
});

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

test("budget setup submits explicit salary, FTE, fringe and indirect assumptions", async () => {
  mockQuery = "";
  render(<Budget />);
  fireEvent.change(screen.getByPlaceholderText("e.g. 250000"), { target: { value: "100000" } });
  fireEvent.click(screen.getByText("Add staff role"));
  fireEvent.change(screen.getByLabelText("Role 1"), { target: { value: "Coordinator" } });
  fireEvent.change(screen.getByLabelText("Headcount 1"), { target: { value: "2" } });
  fireEvent.change(screen.getByLabelText("Annual salary per person 1"), { target: { value: "60000" } });
  fireEvent.change(screen.getByLabelText("FTE per person 1"), { target: { value: "0.5" } });
  fireEvent.change(screen.getByLabelText("Project months 1"), { target: { value: "6" } });
  fireEvent.change(screen.getByLabelText("Fringe rate (%) 1"), { target: { value: "20" } });
  fireEvent.change(screen.getByLabelText("Indirect rate method"), { target: { value: "none" } });
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: /Build Budget/ })); });
  expect(mockBudget.generate).toHaveBeenCalledWith({}, 100000, expect.objectContaining({ staff: [expect.objectContaining({ role: "Coordinator", headcount: 2, annual_salary: "60000", fte_per_person: "0.5", months: "6", fringe_rate_pct: "20" })], indirect: expect.objectContaining({ method: "none", rate_pct: 0 }) }));
});

test("scope reductions are applied only on click and cost assumptions are saved", async () => {
  mockQuery = "";
  const inputs = { staff: [{ id: "s", role: "Coordinator", headcount: 2, annual_salary: "60000", fte_per_person: "0.5", months: "6", fringe_rate_pct: "20" }], direct_costs: [], indirect: { method: "none", rate_pct: 0, base: "MTDC", reference: "", de_minimis_eligible: false, funder_cap_pct: null, funder_cap_base: "MTDC" }, unallowable_kinds: [] };
  const reduced = { ...inputs, staff: [{ ...inputs.staff[0], headcount: 1 }] };
  mockBudget.budget = { model_version: 2, cost_inputs: inputs, items: [{ category: "Personnel", description: "Coordinator", amount: 36000 }], total_requested: 36000, max_budget: 30000, funding_gap: 6000, scope_options: [{ label: "Reduce team by one", cost_inputs: reduced, savings: 18000, funding_gap: 0 }], compliance_summary: { warnings: [], requires_funder_review: true } };
  render(<Budget />);
  expect(screen.getByRole("alert")).toHaveTextContent("$6,000");
  expect(mockBudget.generate).not.toHaveBeenCalled();
  await waitFor(() => expect(mockSaveBudget).toHaveBeenCalledWith(expect.objectContaining({ model_version: 2, cost_inputs: inputs, compliance_summary: expect.objectContaining({ requires_funder_review: true }) })));
  await act(async () => { fireEvent.click(screen.getByText("Apply this scope change")); });
  expect(mockBudget.generate).toHaveBeenCalledWith({}, 30000, reduced);
});

test("award floors and total program funding are never used as a grant ceiling", () => {
  mockQuery = "grant=g1";
  mockGrants = [{ grant_id: "g1", title: "Restoration opportunity", award_floor: 10000, estimated_total: "$53,000,000" }];
  render(<Budget />);
  expect(screen.getByPlaceholderText("e.g. 250000")).toHaveValue(null);
});
