import { render, screen, waitFor } from "@testing-library/react";
import GrantsList from "./GrantsList";
import api from "../services/api";

const mockProposal = { id: "b1", _type: "build", title: "Generated restoration plan", sections: { summary: { content: "Restore creek habitat with local volunteers" } }, matches_id: ["old"] };
const mockWork = { proposals: [mockProposal], loading: false, refresh: jest.fn() };
jest.mock("react-router-dom", () => ({ useSearchParams: () => [new URLSearchParams("proposal=b1")] }), { virtual: true });
jest.mock("../hooks/useWorkStore", () => () => mockWork);
jest.mock("../hooks/useGrants", () => () => ({ grants: [{ grant_id: "old", title: "Old unrelated match" }], proposal: {}, hasRealData: true, loading: false }));
jest.mock("../hooks/useUpload", () => () => ({ upload: jest.fn(), loading: false, error: null }));
jest.mock("../context/AuthContext", () => ({ useAuth: () => ({ profile: { org_name: "Demo" } }) }));
jest.mock("../services/api", () => ({ __esModule: true, default: { post: jest.fn(), patch: jest.fn() } }));
jest.mock("../components", () => ({ Nav: () => null, SectionHeader: () => null, EmptyState: () => null, CollabCard: () => null, GrantCard: ({ grant }) => <div>{grant.title}</div> }));

beforeEach(() => {
  sessionStorage.clear();
  api.post.mockResolvedValue({ data: { matches: [{ grant_id: "190509", title: "Urban Streams Restoration", similarity_score: 90, focus_areas: "Water" }] } });
  api.patch.mockResolvedValue({ data: {} });
});

test("a Find Grants handoff automatically matches the generated text and persists results", async () => {
  sessionStorage.setItem("grant_match_request", JSON.stringify({ ...mockProposal, sections: { summary: { content: "The latest edited proposal" } } }));
  render(<GrantsList />);
  expect(await screen.findByText("Urban Streams Restoration")).toBeInTheDocument();
  await waitFor(() => expect(api.patch).toHaveBeenCalled());
  expect(api.post).toHaveBeenCalledTimes(1);
  expect(api.post).toHaveBeenCalledWith("/api/match", expect.objectContaining({ proposal: expect.objectContaining({ sections: { summary: { title: "summary", content: "The latest edited proposal" } } }) }));
  expect(api.patch).toHaveBeenCalledWith("/api/work/builds/b1", expect.objectContaining({ matched_grants: [expect.objectContaining({ grant_id: "190509" })] }));
  expect(screen.queryByText("Old unrelated match")).not.toBeInTheDocument();
});

test("a bookmarked proposal matcher reloads its saved content without a handoff cache", async () => {
  render(<GrantsList />);
  await screen.findByText("Urban Streams Restoration");
  expect(api.post).toHaveBeenCalledWith("/api/match", expect.objectContaining({ proposal: expect.objectContaining({ raw_text: expect.stringContaining("Restore creek habitat") }) }));
});
