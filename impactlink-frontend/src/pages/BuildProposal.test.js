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
