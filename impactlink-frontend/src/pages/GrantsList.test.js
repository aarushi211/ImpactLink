import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import GrantsList from "./GrantsList";
import api from "../services/api";

const mockProposal = { id: "b1", _type: "build", title: "Generated restoration plan", sections: { summary: { content: "Restore creek habitat with local volunteers" } }, matches_id: ["old"] };
const mockWork = { proposals: [mockProposal], loading: false, refresh: jest.fn() };
let mockQuery = "proposal=b1";
let mockCachedGrants = [];
const mockUpload = jest.fn();
jest.mock("react-router-dom", () => ({ useSearchParams: () => [new URLSearchParams(mockQuery)] }), { virtual: true });
jest.mock("../hooks/useWorkStore", () => () => mockWork);
jest.mock("../hooks/useGrants", () => () => ({ grants: mockCachedGrants, proposal: {}, hasRealData: true, loading: false }));
jest.mock("../hooks/useUpload", () => () => ({ upload: mockUpload, loading: false, error: null }));
jest.mock("../context/AuthContext", () => ({ useAuth: () => ({ profile: { org_name: "Demo" } }) }));
jest.mock("../services/api", () => ({ __esModule: true, default: { post: jest.fn(), patch: jest.fn() } }));
jest.mock("../components", () => ({ Nav: () => null, SectionHeader: () => null, EmptyState: () => null, CollabCard: () => null, GrantCard: ({ grant }) => <div>{grant.title}</div> }));

beforeEach(() => {
  sessionStorage.clear();
  mockQuery = "proposal=b1";
  mockCachedGrants = [{ grant_id: "old", title: "Old unrelated match" }];
  mockUpload.mockReset();
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

test("eligibility precedes upload and privacy is a footer disclaimer", async () => {
  render(<GrantsList />);
  await screen.findByText("Urban Streams Restoration");
  const upload = screen.getByRole("button", { name: "Upload proposal" });
  const eligibility = screen.getByRole("region", { name: "Eligibility filters" });
  const privacy = screen.getByLabelText("AI privacy disclaimer");
  expect(eligibility.compareDocumentPosition(upload) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(eligibility.compareDocumentPosition(privacy) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(screen.getByRole("combobox", { name: "Project U.S. states" })).toBeInTheDocument();
});

test("a bookmarked proposal matcher reloads its saved content without a handoff cache", async () => {
  render(<GrantsList />);
  await screen.findByText("Urban Streams Restoration");
  expect(api.post).toHaveBeenCalledWith("/api/match", expect.objectContaining({ proposal: expect.objectContaining({ raw_text: expect.stringContaining("Restore creek habitat") }) }));
});

test("eligibility inputs override proposal defaults on a fresh match", async () => {
  render(<GrantsList />);
  await screen.findByText("Urban Streams Restoration");
  await waitFor(() => expect(screen.getByText("Find Grants")).not.toBeDisabled());
  fireEvent.change(screen.getByLabelText("Applicant type"), { target: { value: "individual" } });
  fireEvent.change(screen.getByLabelText("Project U.S. states"), { target: { value: "NY" } });
  fireEvent.click(screen.getByText("Find Grants"));
  await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2));
  expect(api.post).toHaveBeenLastCalledWith("/api/match", expect.objectContaining({ proposal: expect.objectContaining({ eligibility_context: { applicant_type: "individual", project_states: ["NY"] } }) }));
});

test("eligibility is selectable before upload and upload waits for an explicit search", async () => {
  mockQuery = ""; mockCachedGrants = [];
  mockUpload.mockResolvedValue({ proposal: { raw_text: "New uploaded proposal" }, savedId: "upload-1" });
  render(<GrantsList />);
  const applicant = screen.getByRole("combobox", { name: "Applicant type" });
  const states = screen.getByRole("combobox", { name: "Project U.S. states" });
  expect(applicant).toBeEnabled(); expect(states).toBeEnabled();
  fireEvent.change(applicant, { target: { value: "individual" } });
  fireEvent.change(states, { target: { value: "NY" } });
  expect(applicant).toHaveValue("individual"); expect(states).toHaveValue("NY");
  fireEvent.change(screen.getByLabelText("Upload proposal file"), { target: { files: [new File(["test"], "Project.pdf", { type: "application/pdf" })] } });
  await screen.findByText(/Selected: Project/);
  expect(mockUpload).toHaveBeenCalledTimes(1);
  expect(api.post).not.toHaveBeenCalled();
  fireEvent.change(applicant, { target: { value: "public_agency" } });
  fireEvent.click(screen.getByText("Find Grants"));
  await waitFor(() => expect(api.post).toHaveBeenCalledWith("/api/match", expect.objectContaining({ proposal: expect.objectContaining({ raw_text: "New uploaded proposal", eligibility_context: { applicant_type: "public_agency", project_states: ["NY"] } }) })));
});

test("selecting a saved proposal also waits for Find Grants", async () => {
  mockQuery = ""; mockCachedGrants = [];
  render(<GrantsList />);
  fireEvent.change(screen.getByLabelText("Select a saved proposal"), { target: { value: "b1" } });
  expect(api.post).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText("Find Grants"));
  await screen.findByText("Urban Streams Restoration");
  expect(api.post).toHaveBeenCalledTimes(1);
});

test("expired cached matches are rechecked without an LLM request and removed", async () => {
  mockQuery = "";
  api.post.mockResolvedValue({ data: { checks: { old: { status: "ineligible", checks: [{ criterion: "deadline", status: "fail", message: "Closed" }] } } } });
  render(<GrantsList />);
  await waitFor(() => expect(api.post).toHaveBeenCalledWith("/api/grants/eligibility/check", expect.objectContaining({ grant_ids: ["old"] })));
  await waitFor(() => expect(screen.queryByText("Old unrelated match")).not.toBeInTheDocument());
  expect(api.post).toHaveBeenCalledTimes(1);
});

test("cached topic results are checked even without proposal matches", async () => {
  mockQuery = "";
  mockCachedGrants = [];
  sessionStorage.setItem("grants_aiResults", JSON.stringify([{ grant_id: "old", title: "Expired topic result" }]));
  api.post.mockResolvedValue({ data: { checks: { old: { status: "ineligible", checks: [] } } } });
  render(<GrantsList />);
  await waitFor(() => expect(api.post).toHaveBeenCalledWith("/api/grants/eligibility/check", expect.objectContaining({ grant_ids: ["old"] })));
  expect(screen.queryByText("Expired topic result")).not.toBeInTheDocument();
});
