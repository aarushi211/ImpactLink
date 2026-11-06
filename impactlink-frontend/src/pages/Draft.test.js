import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  expect(screen.getByRole("button", { name: "Redraft proposal" })).toBeEnabled();
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
  await act(async () => { fireEvent.click(screen.getByText("Redraft proposal")); });
  expect(mockNavigate).toHaveBeenCalledWith("/draft/write");
  expect(screen.getByText("Rewritten river project.")).toBeInTheDocument();
  expect(screen.queryByLabelText("Target grant")).not.toBeInTheDocument();
  expect(screen.queryByText("Edit draft")).not.toBeInTheDocument();
  expect(screen.queryByText("Find grants")).not.toBeInTheDocument();
  expect(mockSession.advanceStream).toHaveBeenCalledWith(expect.objectContaining({ sections_to_rewrite: ["summary"], user_additions: "Keep verified figures" }), expect.any(Function));
  await act(async () => { finish(); });
  rerender(<Draft />);
  await waitFor(() => expect(mockSave).toHaveBeenCalledTimes(1));
  expect(mockSave).toHaveBeenCalledWith(expect.objectContaining({ title: "River Project - Habitat Grant", source_proposal_id: "original-1", original_sections: mockOriginal.sections }));
  expect(mockUpdate).not.toHaveBeenCalled();
  expect(screen.getByText("Find grants")).toBeInTheDocument();
  expect(screen.getByText("Edit draft")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Edit Summary"), { target: { value: "Manually edited revision." } });
  await act(async () => { fireEvent.click(screen.getByText("Save draft")); });
  expect(mockUpdate).toHaveBeenCalledWith("revision-1", expect.objectContaining({ summary: expect.objectContaining({ content: "Manually edited revision." }) }), null, expect.any(Object));
  fireEvent.click(screen.getByText("Compare versions"));
  expect(screen.getByRole("heading", { name: "Original proposal" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Revised proposal" })).toBeInTheDocument();
  expect(mockOriginal.sections.summary.content).toBe("Original river project.");
  expect(api.post.mock.calls.some(([path]) => path === "/api/match")).toBe(false);
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

test("saved revisions reopen for editing without another extraction or a new copy", async () => {
  mockQuery = "load=revision-1";
  mockWork.drafts = [{ id: "revision-1", title: "River Project - Habitat Grant", source_proposal_id: "original-1", source_title: "River Project", grant_id: "g1", grant: mockGrant, application_spec: emptyApplicationSpec(), original_sections: mockOriginal.sections, sections: { summary: { title: "Summary", content: "Saved revised text." } } }];
  render(<Draft />);
  await screen.findByLabelText("Edit Summary");
  expect(screen.getByDisplayValue("Saved revised text.")).toBeInTheDocument();
  expect(api.post).not.toHaveBeenCalled();
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
  await screen.findByLabelText("Edit Summary");
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
  await screen.findByLabelText("Edit Summary");
  expect(screen.getByLabelText("Required AI disclosure is ready")).toBeChecked();
});
