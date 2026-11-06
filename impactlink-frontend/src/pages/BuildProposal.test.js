import { act, fireEvent, render, screen, within } from "@testing-library/react";
import BuildProposal from "./BuildProposal";
import api, { checkProposalConsistency, saveSessionChecklist } from "../services/api";
import { emptyApplicationSpec } from "../utils/application";

let mockPath = "/build/write";
let mockNotifySession = () => {};
let mockGrants = [];

const mockSession = {
  sessionId: "saved", gate: "draft_review", loading: false, error: null,
  data: { sections: { summary: { title: "Summary", content: "The completed proposal text." } } },
  refresh: jest.fn(), advance: jest.fn(), advanceStream: jest.fn(),
  reset: jest.fn(), start: jest.fn(),
};
const mockNavigate = jest.fn();
const mockProfile = { org_name: "Demo nonprofit" };
const mockSaveBuild = jest.fn(async payload => ({ ...payload, id: "build-1" }));
const mockUpdateBuild = jest.fn(async (id, sections, budget, metadata) => ({ ...metadata, id, sections }));
jest.mock("../hooks/useProposalSession", () => () => {
  const React = require("react");
  const [, refresh] = React.useState(0);
  mockNotifySession = () => refresh(value => value + 1);
  return { ...mockSession };
});
jest.mock("react-router-dom", () => ({ useNavigate: () => mockNavigate, useLocation: () => ({ pathname: mockPath }), useSearchParams: () => [new URLSearchParams(), jest.fn()] }), { virtual: true });
jest.mock("../components", () => ({ Nav: () => null }));
jest.mock("../hooks/useGrants", () => () => ({ grants: mockGrants }));
jest.mock("../context/AuthContext", () => ({ useAuth: () => ({ profile: mockProfile }) }));
jest.mock("../hooks/useWorkStore", () => () => ({ saveBuild: mockSaveBuild, updateBuild: mockUpdateBuild, builds: [] }));
jest.mock("../services/api", () => ({ __esModule: true, default: { post: jest.fn(), get: jest.fn() }, reviseSection: jest.fn(), checkProposalConsistency: jest.fn(), saveSessionChecklist: jest.fn() }));

beforeEach(() => {
  sessionStorage.clear(); jest.clearAllMocks();
  mockPath = "/build/write"; mockGrants = [];
  mockSession.sessionId = "saved";
  mockSession.loading = false; mockSession.error = null;
  mockNavigate.mockImplementation(path => { if (typeof path === "string") mockPath = path.split("?")[0]; });
  mockSession.reset.mockImplementation(() => { mockSession.sessionId = null; mockSession.gate = "none"; mockSession.data = {}; });
  mockSaveBuild.mockImplementation(async payload => ({ ...payload, id: "build-1" }));
  mockUpdateBuild.mockImplementation(async (id, sections, budget, metadata) => ({ ...metadata, id, sections }));
  saveSessionChecklist.mockResolvedValue({});
  mockSession.gate = "draft_review";
  mockSession.data = { sections: { summary: { title: "Summary", content: "The completed proposal text." } } };
});

test("finished proposal replies stay inside the chat's single scroll area", async () => {
  Element.prototype.scrollIntoView = jest.fn();
  render(<BuildProposal />);
  await act(async () => {});
  const conversation = screen.getByTestId("build-conversation");
  expect(within(conversation).getByText("The completed proposal text.")).toBeInTheDocument();
  expect(within(conversation).getByRole("button", { name: /Confirm Draft & Continue/ })).toBeInTheDocument();
  expect(conversation.style.flex).toBe("1");
  expect(Array.from(conversation.querySelectorAll("*")).filter(node => node.style.overflowY === "auto")).toHaveLength(0);
});

test("application setup follows the proposal name and privacy stays outside the chat", async () => {
  Element.prototype.scrollIntoView = jest.fn();
  mockSession.gate = "none";
  mockSession.data = {};
  mockPath = "/build";
  render(<BuildProposal />);
  await act(async () => {});
  const name = screen.getByPlaceholderText(/Grant Proposal/);
  const setup = screen.getByText("Application structure and requirements");
  expect(name.compareDocumentPosition(setup) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(screen.queryByTestId("build-conversation")).not.toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Application structure and requirements" }).closest("details")).toBeNull();
  expect(screen.queryByRole("complementary", { name: "Proposal building steps" })).not.toBeInTheDocument();
});

test("a generated proposal is saved before approval and Find Grants passes its full text", async () => {
  Element.prototype.scrollIntoView = jest.fn();
  render(<BuildProposal />);
  await act(async () => {});
  expect(mockSaveBuild).toHaveBeenCalledTimes(1);
  expect(mockSaveBuild.mock.calls[0][0].proposal_context.sections.summary.content).toBe("The completed proposal text.");
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Find grants" })); });
  expect(mockSaveBuild).toHaveBeenCalledTimes(1);
  expect(mockUpdateBuild).toHaveBeenCalledTimes(1);
  expect(mockNavigate).toHaveBeenCalledWith("/grants?proposal=build-1");
  const request = JSON.parse(sessionStorage.getItem("grant_match_request"));
  expect(request.proposal_context.sections.summary.content).toBe("The completed proposal text.");
});

test("streaming section text appears as a reply inside the same conversation", async () => {
  mockSession.gate = "slot_confirm";
  mockSession.data = { slots: {} };
  mockSession.advanceStream.mockImplementation(async (payload, onToken, onSection) => {
    onSection({ type: "section_start", section_key: "summary", title: "Summary" });
    onToken("summary", "A proposal appearing word by word.");
  });
  Element.prototype.scrollIntoView = jest.fn();
  render(<BuildProposal />);
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Confirm & Start Drafting" })); });
  const conversation = screen.getByTestId("build-conversation");
  expect(within(conversation).getByText("A proposal appearing word by word.")).toBeInTheDocument();
  expect(within(conversation).getByRole("region", { name: "Live proposal draft" })).toBeInTheDocument();
  expect(screen.getByRole("complementary", { name: "Proposal building steps" })).toBeInTheDocument();
  expect(screen.getByRole("complementary", { name: "Proposal building steps" }).style.position).toBe("fixed");
  expect(Array.from(conversation.querySelectorAll("*")).filter(node => node.style.overflowY === "auto")).toHaveLength(0);
});

test("funder limits survive saving and block confirmation of an over-limit answer", async () => {
  Element.prototype.scrollIntoView = jest.fn();
  const spec = { stage: "loi", source_reference: "Funder form page 2", process_notes: "LOI before full application", sections: [{ key: "summary", title: "Summary", instructions: "Summarize the project", max_words: 2, max_characters: null, required: true }], attachments: [] };
  mockSession.data = { ...mockSession.data, application_spec: spec };
  render(<BuildProposal />);
  await act(async () => {});
  expect(screen.getByRole("button", { name: /Confirm Draft & Continue/ })).toBeDisabled();
  expect(screen.getByRole("alert")).toHaveTextContent("over-limit");
  expect(mockSaveBuild).toHaveBeenCalledWith(expect.objectContaining({ application_spec: spec, proposal_context: expect.objectContaining({ application_spec: spec }) }));
});

test("required disclosure survives saving and must be marked ready before completion", async () => {
  Element.prototype.scrollIntoView = jest.fn();
  const spec = { stage: "full_proposal", sections: [], attachments: [], ai_policy: { status: "disclosure_required", source_reference: "Funder RFP page 8", notes: "Disclose in portal", disclosure_ready: false } };
  mockSession.data = { ...mockSession.data, application_spec: spec };
  const { rerender } = render(<BuildProposal />);
  await act(async () => {});
  mockSession.gate = "final_save";
  rerender(<BuildProposal />);
  const complete = screen.getByRole("button", { name: /Complete Session/ });
  expect(complete).toBeDisabled();
  expect(mockSaveBuild).toHaveBeenCalledWith(expect.objectContaining({ application_spec: spec }));
  await act(async () => { fireEvent.click(screen.getByLabelText("Required AI disclosure is ready")); });
  expect(complete).toBeEnabled();
  await act(async () => { fireEvent.click(complete); });
  expect(mockSession.advance).toHaveBeenCalledWith({ attachment_statuses: {}, ai_disclosure_ready: true });
  expect(mockUpdateBuild).toHaveBeenCalledWith("build-1", expect.any(Object), null, expect.objectContaining({ application_spec: { ...spec, ai_policy: { ...spec.ai_policy, disclosure_ready: true } } }));
});

test("a restored prohibited policy disables AI revision while keeping manual editing available", async () => {
  Element.prototype.scrollIntoView = jest.fn();
  mockSession.data = { ...mockSession.data, application_spec: { stage: "full_proposal", sections: [], attachments: [], ai_policy: { status: "prohibited", source_reference: "RFP" } } };
  render(<BuildProposal />);
  await act(async () => {});
  expect(screen.getByRole("button", { name: "Revise" })).toBeDisabled();
  expect(screen.getByTitle("Edit directly")).toBeEnabled();
  await act(async () => { fireEvent.click(screen.getByTitle("Edit directly")); });
  expect(screen.getByDisplayValue("The completed proposal text.")).toBeInTheDocument();
});

test("consistency results are saved with the proposal and manual edits mark them stale", async () => {
  Element.prototype.scrollIntoView = jest.fn();
  const review = { status: "passed", issues: [], section_count: 1, characters_reviewed: 60, content_fingerprint: "original-content" };
  mockSession.data = { ...mockSession.data, coherence_review: review };
  const { rerender } = render(<BuildProposal />);
  await act(async () => {});
  expect(mockSaveBuild).toHaveBeenCalledWith(expect.objectContaining({ coherence_review: review }));
  expect(screen.getByText("AI check found no inconsistencies")).toBeInTheDocument();
  fireEvent.click(screen.getByTitle("Edit directly"));
  fireEvent.change(screen.getByDisplayValue("The completed proposal text."), { target: { value: "A changed proposal." } });
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: /Save$/, exact: false })); });
  expect(screen.getByText("Text changed since the consistency check")).toBeInTheDocument();
  const updatedReview = { ...review, content_fingerprint: "updated-content" };
  checkProposalConsistency.mockResolvedValue(updatedReview);
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Check full proposal consistency" })); });
  expect(checkProposalConsistency).toHaveBeenCalledWith(expect.objectContaining({ summary: expect.objectContaining({ content: "A changed proposal." }) }), undefined);
  expect(mockUpdateBuild).toHaveBeenCalledWith("build-1", expect.any(Object), null, expect.objectContaining({ coherence_review: updatedReview }));
  mockSession.data = { ...mockSession.data, coherence_review: { ...review, status: "stale" } };
  rerender(<BuildProposal />);
  expect(screen.getByText("AI check found no inconsistencies")).toBeInTheDocument();
});

test("build checklist saving updates the session and saved build with local feedback", async () => {
  Element.prototype.scrollIntoView = jest.fn();
  mockSession.data = { ...mockSession.data, application_spec: { stage: "full_proposal", sections: [], attachments: [], ai_policy: { status: "disclosure_required", disclosure_ready: false } } };
  render(<BuildProposal />);
  await act(async () => {});
  fireEvent.click(screen.getByLabelText("Required AI disclosure is ready"));
  await act(async () => { fireEvent.click(screen.getByText("Save application checklist")); });
  expect(screen.getByText("Checklist saved.")).toBeInTheDocument();
  expect(saveSessionChecklist).toHaveBeenCalledWith("saved", expect.objectContaining({ ai_policy: expect.objectContaining({ disclosure_ready: true }) }));
  expect(mockUpdateBuild).toHaveBeenCalledWith("build-1", expect.any(Object), null, expect.objectContaining({ application_spec: expect.objectContaining({ ai_policy: expect.objectContaining({ disclosure_ready: true }) }) }));
});

test("selecting a grant automatically prefills the expanded setup form", async () => {
  mockPath = "/build"; mockSession.gate = "none"; mockSession.data = {};
  mockGrants = [{ grant_id: "g1", title: "Restoration grant" }];
  api.get.mockResolvedValue({ data: { ...mockGrants[0], description: "Grant instructions" } });
  api.post.mockResolvedValue({ data: { application_spec: emptyApplicationSpec("loi"), evidence: [], warnings: ["Portal limits need confirmation"] } });
  render(<BuildProposal />);
  fireEvent.change(screen.getByLabelText("Target grant"), { target: { value: "g1" } });
  await screen.findByText(/Prefilled 0 questions/);
  expect(screen.getByLabelText("Application stage")).toHaveValue("loi");
  expect(screen.getByText("Portal limits need confirmation")).toBeInTheDocument();
  expect(api.post).toHaveBeenCalledWith("/api/grants/g1/application-requirements");
});

test("Start opens the workspace and the assistant asks questions before drafting", async () => {
  Element.prototype.scrollIntoView = jest.fn();
  mockPath = "/build"; mockSession.gate = "none"; mockSession.data = {}; mockSession.sessionId = null;
  mockSession.start.mockImplementation(async (flow, grant) => {
    mockSession.sessionId = "build-new"; mockSession.gate = "slot_filling";
    mockSession.data = { grant, application_spec: grant.application_spec, question: "What problem does your project address?", slot_key: "problem", slots_filled: 0, slots_total: 1 };
    mockNotifySession();
    return "build-new";
  });
  render(<BuildProposal />);
  fireEvent.change(screen.getByLabelText("Proposal name"), { target: { value: "New river project" } });
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Start building" })); });
  expect(mockNavigate).toHaveBeenCalledWith("/build/write");
  expect(mockSession.start).toHaveBeenCalledWith("scratch", expect.objectContaining({ build_context: { proposal_name: "New river project" }, application_spec: expect.objectContaining({ stage: "full_proposal" }) }), mockProfile);
  expect(screen.getByText("What problem does your project address?")).toBeInTheDocument();
  expect(screen.getByPlaceholderText("Type your answer…")).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Application structure and requirements" })).not.toBeInTheDocument();
  expect(screen.getByRole("complementary", { name: "Proposal building steps" })).toBeInTheDocument();
  expect(mockSession.advanceStream).not.toHaveBeenCalled();
});
