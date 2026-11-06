import { render, screen, fireEvent } from "@testing-library/react";
import Dashboard from "./Dashboard";

const mockNavigate = jest.fn();
const mockWork = {
  drafts: [{ id: "d1", title: "Revised proposal", grant_id: "190509", sections: { summary: { content: "Revised content" } }, updated_at: "2026-11-05T12:00:00Z" }],
  builds: [{ id: "b1", title: "Generated proposal", sections: { summary: { content: "Generated content" } }, updated_at: "2026-11-05T12:00:00Z", matched_grants: [{ grant_id: "190509", title: "Urban Streams Restoration", focus_areas: "Water", similarity_score: 80 }] }],
  budgets: [{ id: "bu1", title: "Saved budget", total_requested: 10000, updated_at: "2026-11-05T12:00:00Z" }],
  loading: false, deleteDraft: jest.fn(), deleteBuild: jest.fn(), deleteBudget: jest.fn(),
};
jest.mock("react-router-dom", () => ({ useNavigate: () => mockNavigate }), { virtual: true });
jest.mock("../hooks/useWorkStore", () => () => mockWork);
jest.mock("../hooks/useGrants", () => () => ({ grants: [] }));
jest.mock("../context/AuthContext", () => ({ useAuth: () => ({ profile: { org_name: "Demo nonprofit" } }) }));
jest.mock("../services/api", () => ({ __esModule: true, default: { get: jest.fn() } }));
jest.mock("../components", () => ({
  Nav: () => null, StatCard: () => null, SectionHeader: () => null,
  GrantCard: require("../components/GrantCard").default,
}));

beforeEach(() => { mockNavigate.mockClear(); sessionStorage.clear(); });

test.each([
  ["Generated proposal", "/build?load=b1"],
  ["Revised proposal", "/draft?load=d1&grant=190509"],
  ["Saved budget", "/budget?load=bu1"],
])("clicking %s opens that saved record", (title, route) => {
  render(<Dashboard />);
  fireEvent.click(screen.getByText(title));
  expect(mockNavigate).toHaveBeenCalledWith(route);
});

test("persisted grant matches open even with an empty browser match cache", () => {
  render(<Dashboard />);
  fireEvent.click(screen.getByText("Urban Streams Restoration"));
  expect(mockNavigate).toHaveBeenCalledWith("/grants/190509");
});
