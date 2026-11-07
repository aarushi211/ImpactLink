import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import Draft from "./Draft";
import api, { saveSessionChecklist } from "../services/api";
import { emptyApplicationSpec } from "../utils/application";

let mockPath = "/draft";
let mockQuery = "";
let mockNotifySession = () => {};
const mockNavigate = jest.fn(path => { mockPath = path.split("?")[0]; mockQuery = path.split("?")[1] || ""; });
const mockGrant = { grant_id: "g1", title: "Habitat Grant", description: "Restoration funding", agency: "Agency" };
const mockOriginal = { id: "original-1", title: "River Project", sections: { summary: { title: "Summary", content: "Original river project." } }, proposal_context: { primary_mission: "Restore rivers" } };
const mockSave = jest.fn(async value => ({ ...value, id: "revision-1" }));
const mockUpdate = jest.fn(async (id, sections, budget, metadata) => ({ ...metadata, id, sections }));
const mockWork = { proposals: [mockOriginal], drafts: [], saveDraft: mockSave, updateDraft: mockUpdate, loading: false };
const mockSession = { sessionId: null, gate: "none", data: {}, loading: false, error: null, progress: "", start: jest.fn(), advanceStream: jest.fn(), reset: jest.fn(), restore: jest.fn(), refresh: jest.fn(), setData: jest.fn(), setGate: jest.fn() };
jest.mock("react-router-dom", () => ({ useNavigate: () => mockNavigate, useLocation: () => ({ pathname: mockPath }), useSearchParams: () => [new URLSearchParams(mockQuery)] }), { virtual: true });
jest.mock("../components", () => ({ Nav: () => null }));
jest.mock("../context/AuthContext", () => ({ useAuth: () => ({ profile: { org_name: "River nonprofit" } }) }));
jest.mock("../hooks/useGrants", () => () => ({ grants: [mockGrant], proposal: null }));
jest.mock("../hooks/useWorkStore", () => () => mockWork);
jest.mock("../hooks/useProposalSession", () => () => {
  const React = require("react");
  const [, refresh] = React.useState(0);
  mockNotifySession = () => refresh(value => value + 1);
  return { ...mockSession };
});
jest.mock("../services/api", () => ({ __esModule: true, default: { get: jest.fn(), post: jest.fn() }, saveSessionChecklist: jest.fn() }));

beforeEach(() => {
  jest.clearAllMocks(); sessionStorage.clear(); mockPath = "/draft"; mockQuery = "";
  mockWork.drafts = []; mockWork.loading = false;
  Object.assign(mockSession, { sessionId: null, gate: "none", data: {}, loading: false, error: null, progress: "" });
  mockNavigate.mockImplementation(path => { mockPath = path.split("?")[0]; mockQuery = path.split("?")[1] || ""; });
  mockSave.mockImplementation(async value => ({ ...value, id: "revision-1" }));
  mockUpdate.mockImplementation(async (id, sections, budget, metadata) => ({ ...metadata, id, sections }));
  api.get.mockResolvedValue({ data: mockGrant });
  saveSessionChecklist.mockResolvedValue({});
  api.post.mockResolvedValue({ data: { application_spec: emptyApplicationSpec(), evidence: [], warnings: ["Stored summary does not include portal questions."] } });
  mockSession.reset.mockImplementation(() => { mockSession.gate = "none"; mockSession.data = {}; mockSession.sessionId = null; });
  mockSession.setData.mockImplementation(data => { mockSession.data = data; mockNotifySession(); });
  mockSession.setGate.mockImplementation(gate => { mockSession.gate = gate; mockNotifySession(); });
  mockSession.start.mockImplementation(async (flow, grant, profile, originals) => {
    mockSession.sessionId = "session-1"; mockSession.gate = "gap_review";
    mockSession.data = { grant, application_spec: grant.application_spec, original_sections: originals, analysis: { sections_to_rewrite: ["summary"] } };
    mockNotifySession();
    return "session-1";
  });
});

test("setup puts selectors horizontally above expanded requirements and prefills on grant selection", async () => {
  render(<Draft />);
  expect(screen.getByRole("combobox", { name: "Proposal" })).toHaveValue("original-1");
  expect(screen.getByRole("combobox", { name: "Target grant" })).toBeInTheDocument();
  const heading = screen.getByRole("heading", { name: "Application structure and requirements" });
  expect(heading.closest("details")).toBeNull();
  expect(screen.queryByText("Ready to draft")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Find grants" })).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Target grant"), { target: { value: "g1" } });
  await screen.findByText(/Prefilled 0 questions/);
  expect(api.post).toHaveBeenCalledWith("/api/grants/g1/application-requirements");
  expect(screen.getByText(/Stored summary does not include portal questions/)).toBeInTheDocument();
  expect(screen.getByLabelText("New draft name")).toHaveValue("River Project - Habitat Grant");
  expect(screen.getByRole("button", { name: "Review gaps" })).toBeEnabled();
});

test("redraft opens a writing page, streams without setup panels and saves a separate named revision", async () => {
  let finish;
  mockSession.advanceStream.mockImplementation((payload, token) => {
    token("summary", "Rewritten river project.");
    return new Promise(resolve => { finish = () => {
      mockSession.gate = "draft_review";
      mockSession.data = { ...mockSession.data, sections: { summary: { title: "Summary", content: "Rewritten river project." } } };
      mockNotifySession();
      resolve(mockSession.data);
    }; });
  });
  const { rerender } = render(<Draft />);
  fireEvent.change(screen.getByLabelText("Target grant"), { target: { value: "g1" } });
  await screen.findByText(/Prefilled 0 questions/);
  fireEvent.change(screen.getByLabelText("Instructions for this rewrite"), { target: { value: "Keep verified figures" } });
  await act(async () => { fireEvent.click(screen.getByText("Review gaps")); });
  expect(mockNavigate).toHaveBeenCalledWith("/draft/write");
  expect(mockSession.advanceStream).not.toHaveBeenCalled();
  expect(screen.getByRole("region", { name: "Gap analysis" })).toBeInTheDocument();
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Draft", exact: true })); });
  expect(screen.getByText("Rewritten river project.")).toBeInTheDocument();
  expect(screen.queryByLabelText("Target grant")).not.toBeInTheDocument();
  expect(screen.queryByText("Edit draft")).not.toBeInTheDocument();
  expect(screen.queryByText("Find grants")).not.toBeInTheDocument();
  expect(mockSession.advanceStream).toHaveBeenCalledWith(expect.objectContaining({ user_additions: "Keep verified figures" }), expect.any(Function));
  expect(mockSession.advanceStream.mock.calls[0][0].sections_to_rewrite).toEqual(["summary"]);
  await act(async () => { finish(); });
  rerender(<Draft />);
  await waitFor(() => expect(mockSave).toHaveBeenCalledTimes(1));
  expect(mockSave).toHaveBeenCalledWith(expect.objectContaining({ title: "River Project - Habitat Grant", source_proposal_id: "original-1", original_sections: mockOriginal.sections }));
  expect(mockUpdate).not.toHaveBeenCalled();
  expect(screen.getByText("Find grants")).toBeInTheDocument();
  expect(screen.getByText("Edit draft")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Edit draft", exact: true }));
  fireEvent.change(screen.getByLabelText("Edit Summary"), { target: { value: "Manually edited revision." } });
  await act(async () => { fireEvent.click(screen.getByText("Save draft")); });
  expect(mockUpdate).toHaveBeenCalledWith("revision-1", expect.objectContaining({ summary: expect.objectContaining({ content: "Manually edited revision." }) }), null, expect.any(Object));
  fireEvent.click(screen.getByText("Compare versions"));
  expect(screen.getByRole("heading", { name: "Original proposal" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Revised proposal" })).toBeInTheDocument();
  expect(mockOriginal.sections.summary.content).toBe("Original river project.");
  expect(api.post.mock.calls.some(([path]) => path === "/api/match")).toBe(true);
});

test("failed prefill leaves editable fields and never invents funder questions", async () => {
  api.post.mockRejectedValue(new Error("Failed extraction"));
  render(<Draft />);
  fireEvent.change(screen.getByLabelText("Target grant"), { target: { value: "g1" } });
  await screen.findByRole("alert");
  expect(screen.getByLabelText("Application stage")).toBeEnabled();
  expect(screen.queryByLabelText("Question title 1")).not.toBeInTheDocument();
  expect(screen.getByLabelText("Funder AI-use policy")).toHaveValue("unknown");
});

test("gap review waits for Draft and submits only the areas the user selected", async () => {
  mockPath = "/draft/write";
  mockSession.sessionId = "manual-review"; mockSession.gate = "gap_review";
  mockSession.data = { grant: mockGrant, original_sections: { summary: "Original summary", budget: "Original budget" }, analysis: { missing_content: [{ section: "summary", description: "Clarify monitoring", target_units: [0] }], sections_to_rewrite: ["summary", "budget"] } };
  mockSession.advanceStream.mockResolvedValue({});
  const { rerender } = render(<Draft />);
  expect(screen.getByRole("region", { name: "Gap analysis" })).toHaveTextContent("Clarify monitoring");
  expect(mockSession.advanceStream).not.toHaveBeenCalled();
  rerender(<Draft />);
  expect(mockSession.advanceStream).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("checkbox", { name: "Budget", exact: true }));
  fireEvent.change(screen.getByLabelText("Additional drafting instructions"), { target: { value: "Keep all other text and tables unchanged." } });
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Draft", exact: true })));
  expect(mockSession.advanceStream).toHaveBeenCalledTimes(1);
  expect(mockSession.advanceStream).toHaveBeenCalledWith(expect.objectContaining({ sections_to_rewrite: ["summary"], user_additions: "Keep all other text and tables unchanged." }), expect.any(Function));
});

test("finished revision previews tables and keeps the gap panel hidden", async () => {
  mockPath = "/draft/write";
  const table = "| Activity | Months |\n| --- | --- |\n| Outdoor trips | 4–22 |\n\nThe original narrative remains.";
  Object.assign(mockSession, { sessionId: "table-preview", gate: "draft_review", data: { grant: { ...mockGrant, revision_context: { title: "Revision", source_title: "River Project" } }, sections: { work_plan: { title: "Work plan", content: table } }, analysis: { sections_to_rewrite: ["work_plan"] } } });
  api.post.mockResolvedValue({ data: { matches: [] } });
  render(<Draft />);
  expect(screen.getByRole("table")).toHaveTextContent("Outdoor trips");
  expect(screen.getByRole("columnheader", { name: "Months" })).toBeInTheDocument();
  expect(screen.getByText("The original narrative remains.")).toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Gap analysis" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Edit draft", exact: true }));
  expect(screen.getByLabelText("Edit Work plan")).toHaveValue(table);
  fireEvent.click(screen.getByRole("button", { name: "View draft", exact: true }));
  expect(screen.getByRole("table")).toBeInTheDocument();
  await act(async () => {});
});

test("gap review shows the original score and keeps it distinct from the revised score", async () => {
  mockPath = "/draft/write";
  mockSession.sessionId = "before-after"; mockSession.gate = "gap_review";
  mockSession.data = { grant: { ...mockGrant, revision_context: { title: "Revision", source_title: "River Project" } }, original_sections: { summary: "Original river project." }, analysis: { sections_to_rewrite: ["summary"] } };
  const originalMatch = { grant_id: "g1", similarity_score: 61, fit_level: "moderate", match_explanation: "Original proposal needs stronger monitoring." };
  const revisedMatch = { grant_id: "g1", similarity_score: 84, fit_level: "strong", match_explanation: "Revised monitoring improves alignment." };
  api.post.mockResolvedValueOnce({ data: { matches: [originalMatch] } }).mockResolvedValueOnce({ data: { matches: [revisedMatch] } });
  mockSession.advanceStream.mockImplementation(async () => {
    mockSession.gate = "draft_review";
    mockSession.data = { ...mockSession.data, sections: { summary: { title: "Summary", content: "Revised river project with monitoring." } } };
    mockNotifySession();
  });
  render(<Draft />);
  await screen.findByText("Original proposal needs stronger monitoring.");
  expect(screen.getByRole("region", { name: "Original grant match" })).toHaveTextContent("61 / 100");
  expect(api.post).toHaveBeenCalledWith("/api/match", expect.objectContaining({ grant_id: "g1", target_only: true, proposal: expect.objectContaining({ sections: { summary: { title: "Summary", content: "Original river project." } } }) }));
  expect(mockSession.advanceStream).not.toHaveBeenCalled();
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Draft", exact: true })));
  await screen.findByText("Revised monitoring improves alignment.");
  expect(screen.queryByRole("region", { name: "Original grant match" })).not.toBeInTheDocument();
  const updated = screen.getByRole("region", { name: "Updated grant match" });
  expect(updated).toHaveTextContent("84 / 100");
  expect(updated).toHaveTextContent("Original proposal: 61 / 100");
  await waitFor(() => expect(mockSave).toHaveBeenCalledWith(expect.objectContaining({ original_match_assessment: expect.objectContaining({ match: originalMatch }) })));
});

test("comparison restores red deletions and green additions, including manual edits", async () => {
  mockPath = "/draft/write";
  Object.assign(mockSession, { sessionId: "colors", gate: "draft_review", data: {
    grant: { ...mockGrant, revision_context: { title: "Revision", source_title: "River Project" } },
    original_sections: { summary: "Old funding." },
    sections: { summary: { title: "Summary", content: "New funding." } },
    diffs: { summary: [{ type: "remove", text: "Old" }, { type: "add", text: "New" }, { type: "equal", text: " funding." }] },
  } });
  api.post.mockResolvedValue({ data: { matches: [] } });
  render(<Draft />);
  const preview = screen.getByRole("region", { name: "Revised proposal preview" });
  expect(preview.querySelector('[data-change="add"]')).toHaveTextContent("New");
  fireEvent.click(screen.getByText("Compare versions"));
  const original = screen.getByRole("heading", { name: "Original proposal" }).closest("article");
  const revised = screen.getByRole("heading", { name: "Revised proposal" }).closest("article");
  const removed = original.querySelector('[data-change="remove"]');
  expect(removed).toHaveTextContent("Old");
  expect(removed).toHaveStyle({ background: "#fee2e2", color: "#991b1b", textDecoration: "line-through" });
  expect(revised.querySelector('[data-change="add"]')).toHaveTextContent("New");
  expect(revised.querySelector('[data-change="add"]')).toHaveStyle({ background: "#dcfce7", color: "#166534" });
  fireEvent.change(within(revised).getByLabelText("Edit revised Summary"), { target: { value: "New funded program." } });
  expect(original.querySelector('[data-change="remove"]')).toBeInTheDocument();
  expect(revised.querySelectorAll('[data-change="add"]').length).toBeGreaterThan(0);
  expect(within(revised).getByLabelText("Edit revised Summary")).toHaveValue("New funded program.");
  await act(async () => fireEvent.click(screen.getByText("Save draft")));
  const savedDiff = mockUpdate.mock.calls.at(-1)[3].diffs.summary;
  expect(savedDiff.filter(token => token.type !== "add").map(token => token.text).join("")).toBe("Old funding.");
  expect(savedDiff.filter(token => token.type !== "remove").map(token => token.text).join("")).toBe("New funded program.");
});

test("gap findings are saved but hidden after rewriting", async () => {
  mockPath = "/draft/write";
  mockSession.sessionId = "review-gaps";
  mockSession.gate = "draft_review";
  const analysis = { missing_content: [{ section: "summary", description: "Explain how restoration outcomes will be monitored.", severity: "high" }], sections_to_rewrite: ["summary"] };
  mockSession.data = { grant: { ...mockGrant, revision_context: { title: "Targeted revision" } }, original_sections: { summary: "Original river project." }, sections: { summary: { title: "Summary", content: "Original river project. Monitoring added." }, budget: { title: "Budget", content: "Unchanged budget." } }, analysis };
  render(<Draft />);
  expect(screen.queryByRole("region", { name: "Gap analysis" })).not.toBeInTheDocument();
  expect(screen.queryByText("Gaps identified before revision")).not.toBeInTheDocument();
  await waitFor(() => expect(mockSave).toHaveBeenCalledWith(expect.objectContaining({ analysis })));
});

test("failed gap analysis does not silently launch a blanket rewrite", async () => {
  mockPath = "/draft/write";
  mockSession.sessionId = "failed-analysis";
  mockSession.gate = "gap_review";
  mockSession.data = { analysis: { status: "unavailable", sections_to_rewrite: [] } };
  render(<Draft />);
  expect(screen.getByRole("alert")).toHaveTextContent("No automatic rewrite was started");
  expect(mockSession.advanceStream).not.toHaveBeenCalled();
});

test("revised text is scored against the selected grant and becomes stale after editing", async () => {
  mockPath = "/draft/write";
  Object.assign(mockSession, { sessionId: "updated-match", gate: "draft_review", data: {
    grant: { ...mockGrant, revision_context: { title: "River Project - Habitat Grant", source_title: "River Project" } },
    original_sections: { summary: "Original river project." },
    sections: { summary: { title: "Summary", content: "Revised river project with outcome monitoring." } },
  } });
  const match = { grant_id: "g1", title: "Habitat Grant", similarity_score: 86, fit_level: "strong", score_method: "ai_project_fit", match_explanation: "The revised monitoring plan addresses the grant priorities." };
  api.post.mockResolvedValue({ data: { matches: [match] } });
  render(<Draft />);
  await screen.findByText("The revised monitoring plan addresses the grant priorities.");
  expect(api.post).toHaveBeenCalledWith("/api/match", expect.objectContaining({ target_only: true, grant_id: "g1", top_k: 1, proposal: expect.objectContaining({ project_title: "River Project", sections: expect.objectContaining({ summary: expect.objectContaining({ content: "Revised river project with outcome monitoring." }) }) }) }));
  await waitFor(() => expect(mockUpdate).toHaveBeenCalledWith("revision-1", expect.any(Object), null, expect.objectContaining({ match_assessment: expect.objectContaining({ match }), matched_grants: [match] })));
  fireEvent.click(screen.getByRole("button", { name: "Edit draft", exact: true }));
  fireEvent.change(screen.getByLabelText("Edit Summary"), { target: { value: "Manually changed project." } });
  expect(screen.getByRole("region", { name: "Updated grant match" })).toHaveTextContent("changed since this score was calculated");
  expect(screen.queryByText("The revised monitoring plan addresses the grant priorities.")).not.toBeInTheDocument();
  expect(api.post).toHaveBeenCalledTimes(1);
  await act(async () => fireEvent.click(screen.getByText("Refresh match")));
  expect(api.post).toHaveBeenLastCalledWith("/api/match", expect.objectContaining({ proposal: expect.objectContaining({ sections: expect.objectContaining({ summary: expect.objectContaining({ content: "Manually changed project." }) }) }) }));
});

test("failed match refresh is recoverable and never uses another grant's score", async () => {
  mockPath = "/draft/write";
  Object.assign(mockSession, { sessionId: "match-retry", gate: "draft_review", data: {
    grant: { ...mockGrant, revision_context: { title: "Revision", source_title: "River Project" } },
    original_sections: { summary: "Original" }, sections: { summary: { title: "Summary", content: "Revised" } },
  } });
  api.post.mockRejectedValueOnce(new Error("Match service unavailable"));
  render(<Draft />);
  await screen.findByText("Match service unavailable");
  expect(screen.getByRole("region", { name: "Revised proposal preview" })).toHaveTextContent("Revised");
  api.post.mockResolvedValueOnce({ data: { matches: [{ grant_id: "other", similarity_score: 99 }] } });
  await act(async () => fireEvent.click(screen.getByText("Refresh match")));
  expect(screen.getByRole("region", { name: "Updated grant match" })).toHaveTextContent("No match score is available for the selected grant");
  expect(screen.getByRole("region", { name: "Updated grant match" })).not.toHaveTextContent("99");
});

test("a saved current match is shown on reopening without another scoring request", async () => {
  mockPath = "/draft/write";
  Object.assign(mockSession, { sessionId: "saved-match", gate: "draft_review", data: {
    grant: { ...mockGrant, revision_context: { title: "Saved revision", source_title: "River Project" } },
    original_sections: { summary: "Original" }, sections: { summary: { title: "Summary", content: "Revised" } },
  } });
  const match = { grant_id: "g1", similarity_score: 84, fit_level: "strong", match_explanation: "Saved current assessment." };
  api.post.mockResolvedValue({ data: { matches: [match] } });
  const first = render(<Draft />);
  await screen.findByText("Saved current assessment.");
  await waitFor(() => expect(mockUpdate).toHaveBeenCalled());
  const saved = mockUpdate.mock.calls.at(-1)[3];
  first.unmount();
  Object.assign(mockSession, { sessionId: null, gate: "none", data: {} });
  mockPath = "/draft"; mockQuery = "load=revision-1";
  mockWork.drafts = [{ ...saved, id: "revision-1" }];
  api.post.mockClear();
  render(<Draft />);
  await screen.findByText("Saved current assessment.");
  expect(api.post).not.toHaveBeenCalled();
});

test("a score arriving after manual edits is not applied to the newer proposal", async () => {
  mockPath = "/draft/write";
  Object.assign(mockSession, { sessionId: "pending-match", gate: "draft_review", data: {
    grant: { ...mockGrant, revision_context: { title: "Revision", source_title: "River Project" } },
    original_sections: { summary: "Original" }, sections: { summary: { title: "Summary", content: "First revision" } },
  } });
  let finish;
  api.post.mockReturnValue(new Promise(resolve => { finish = resolve; }));
  render(<Draft />);
  await waitFor(() => expect(api.post).toHaveBeenCalled());
  fireEvent.click(screen.getByRole("button", { name: "Edit draft", exact: true }));
  fireEvent.change(screen.getByLabelText("Edit Summary"), { target: { value: "Newer edited revision" } });
  await act(async () => finish({ data: { matches: [{ grant_id: "g1", similarity_score: 90, match_explanation: "Old text score" }] } }));
  expect(screen.queryByText("Old text score")).not.toBeInTheDocument();
  expect(screen.getByLabelText("Edit Summary")).toHaveValue("Newer edited revision");
  expect(mockUpdate.mock.calls.some(call => call[3]?.match_assessment?.match)).toBe(false);
});

test("saved revisions reopen for editing without another extraction or a new copy", async () => {
  mockQuery = "load=revision-1";
  mockWork.drafts = [{ id: "revision-1", title: "River Project - Habitat Grant", source_proposal_id: "original-1", source_title: "River Project", grant_id: "g1", grant: mockGrant, application_spec: emptyApplicationSpec(), original_sections: mockOriginal.sections, sections: { summary: { title: "Summary", content: "Saved revised text." } } }];
  render(<Draft />);
  await screen.findByRole("button", { name: "Edit draft", exact: true });
  fireEvent.click(screen.getByRole("button", { name: "Edit draft", exact: true }));
  expect(screen.getByDisplayValue("Saved revised text.")).toBeInTheDocument();
  expect(api.post.mock.calls.some(([path]) => path.includes("application-requirements"))).toBe(false);
  expect(mockSave).not.toHaveBeenCalled();
  await act(async () => { fireEvent.click(screen.getByText("Save draft")); });
  expect(mockUpdate).toHaveBeenCalledWith("revision-1", expect.any(Object), null, expect.objectContaining({ title: "River Project - Habitat Grant" }));
});

test("recovering a completed checkpoint reuses the revision already saved for that session", async () => {
  mockPath = "/draft/write"; mockQuery = "session=session-1";
  mockWork.drafts = [{ id: "revision-existing", session_id: "session-1" }];
  Object.assign(mockSession, { sessionId: "session-1", gate: "draft_review", data: {
    grant: { ...mockGrant, revision_context: { title: "Recovered revision", source_title: "River Project", source_proposal_id: "original-1" } },
    application_spec: { ...emptyApplicationSpec(), sections: [{ key: "summary", title: "Summary", instructions: "Explain the need", max_words: 100, required: true }] },
    original_sections: mockOriginal.sections, sections: { summary: { title: "Summary", content: "Recovered text" } },
  } });
  render(<Draft />);
  await waitFor(() => expect(mockUpdate).toHaveBeenCalled());
  expect(mockSave).not.toHaveBeenCalled();
  expect(mockUpdate).toHaveBeenCalledWith("revision-existing", expect.any(Object), null, expect.objectContaining({ application_spec: expect.objectContaining({ sections: [expect.objectContaining({ max_words: 100 })] }) }));
});

test("skipping a slow prefill leaves manual setup intact when the response arrives later", async () => {
  let finish;
  api.post.mockReturnValue(new Promise(resolve => { finish = resolve; }));
  render(<Draft />);
  fireEvent.change(screen.getByLabelText("Target grant"), { target: { value: "g1" } });
  await waitFor(() => expect(api.post).toHaveBeenCalled());
  fireEvent.click(screen.getByText("Enter requirements manually"));
  fireEvent.change(screen.getByLabelText("Application process notes"), { target: { value: "Confirmed manually" } });
  await act(async () => { finish({ data: { application_spec: { ...emptyApplicationSpec(), process_notes: "Old response" } } }); });
  expect(screen.getByLabelText("Application process notes")).toHaveValue("Confirmed manually");
});

test("saving disclosure updates the checkpoint and every saved copy, with confirmation after reopening", async () => {
  mockQuery = "load=revision-1";
  const spec = { ...emptyApplicationSpec(), ai_policy: { status: "disclosure_required", disclosure_ready: false } };
  mockWork.drafts = [{ id: "revision-1", session_id: "old-session", title: "River revision", grant_id: "g1", grant: { ...mockGrant, application_spec: spec }, application_spec: spec, original_sections: mockOriginal.sections, sections: mockOriginal.sections }];
  const view = render(<Draft />);
  await screen.findByRole("button", { name: "Edit draft", exact: true });
  fireEvent.click(screen.getByRole("button", { name: "Edit draft", exact: true }));
  fireEvent.click(screen.getByLabelText("Required AI disclosure is ready"));
  await act(async () => { fireEvent.click(screen.getByText("Save application checklist")); });
  expect(screen.getByText("Checklist saved.")).toBeInTheDocument();
  expect(saveSessionChecklist).toHaveBeenCalledWith("old-session", expect.objectContaining({ ai_policy: expect.objectContaining({ disclosure_ready: true }) }));
  const saved = await mockUpdate.mock.results[0].value;
  expect(saved.application_spec.ai_policy.disclosure_ready).toBe(true);
  expect(saved.grant.application_spec.ai_policy.disclosure_ready).toBe(true);
  expect(saved.proposal_context.application_spec.ai_policy.disclosure_ready).toBe(true);
  view.unmount();
  mockWork.drafts = [saved];
  render(<Draft />);
  await screen.findByRole("button", { name: "Edit draft", exact: true });
  fireEvent.click(screen.getByRole("button", { name: "Edit draft", exact: true }));
  expect(screen.getByLabelText("Required AI disclosure is ready")).toBeChecked();
});
