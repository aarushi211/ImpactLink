import { act, fireEvent, render, screen, within } from "@testing-library/react";
import BuildProposal from "./BuildProposal";

const mockSession = {
  sessionId: "saved", gate: "draft_review", loading: false, error: null,
  data: { sections: { summary: { title: "Summary", content: "The completed proposal text." } } },
  refresh: jest.fn(), advance: jest.fn(), advanceStream: jest.fn(),
};
const mockNavigate = jest.fn();
const mockProfile = { org_name: "Demo nonprofit" };
const mockSaveBuild = jest.fn(async payload => ({ ...payload, id: "build-1" }));
const mockUpdateBuild = jest.fn(async (id, sections, budget, metadata) => ({ ...metadata, id, sections }));
jest.mock("../hooks/useProposalSession", () => () => mockSession);
jest.mock("react-router-dom", () => ({ useNavigate: () => mockNavigate, useSearchParams: () => [new URLSearchParams(), jest.fn()] }), { virtual: true });
jest.mock("../components", () => ({ Nav: () => null }));
jest.mock("../hooks/useGrants", () => () => ({ grants: [] }));
jest.mock("../context/AuthContext", () => ({ useAuth: () => ({ profile: mockProfile }) }));
jest.mock("../hooks/useWorkStore", () => () => ({ saveBuild: mockSaveBuild, updateBuild: mockUpdateBuild, builds: [] }));
jest.mock("../services/api", () => ({ __esModule: true, default: { post: jest.fn() }, reviseSection: jest.fn() }));

beforeEach(() => {
  sessionStorage.clear(); jest.clearAllMocks();
  mockSaveBuild.mockImplementation(async payload => ({ ...payload, id: "build-1" }));
  mockUpdateBuild.mockImplementation(async (id, sections, budget, metadata) => ({ ...metadata, id, sections }));
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
