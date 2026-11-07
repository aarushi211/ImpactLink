import { render, screen, fireEvent, act } from "@testing-library/react";
import Profile from "./Profile";
jest.mock("../services/api", () => ({ __esModule: true, default: { post: jest.fn() } }));

const mockUpdate = jest.fn();
const mockProfile = { org_name: "Demo nonprofit", email: "demo@example.test", sdgs: [], geographic_focus: ["California", "Oregon"] };
jest.mock("react-router-dom", () => ({ useNavigate: () => jest.fn() }), { virtual: true });
jest.mock("../components", () => ({ Nav: () => null }));
jest.mock("../context/AuthContext.js", () => ({ useAuth: () => ({ profile: mockProfile, updateProfile: mockUpdate, logout: jest.fn() }) }));
beforeEach(() => { jest.clearAllMocks(); });

test("eligibility fields are explicitly declared and saved with the profile", async () => {
  mockUpdate.mockResolvedValue();
  render(<Profile />);
  expect(screen.getByLabelText("Applicant type")).toHaveValue("");
  fireEvent.change(screen.getByLabelText("Applicant type"), { target: { value: "public_agency" } });
  fireEvent.change(screen.getByLabelText("Project U.S. states"), { target: { value: "CA" } });
  fireEvent.change(screen.getByLabelText("Project U.S. states"), { target: { value: "NY" } });
  fireEvent.change(screen.getByLabelText("Names and phrases to mask"), { target: { value: "Zyqra\nPrivate case 44" } });
  await act(async () => { fireEvent.click(screen.getByText("Save Changes")); });
  expect(mockUpdate).toHaveBeenCalledWith(expect.objectContaining({ applicant_type: "public_agency", project_states: ["CA", "NY"], privacy_redaction_terms: ["Zyqra", "Private case 44"] }));
});

test("organization identity, communities and all service areas survive saving", async () => {
  mockUpdate.mockResolvedValue();
  render(<Profile />);
  expect(screen.getByLabelText("Service areas")).toHaveValue("California\nOregon");
  fireEvent.change(screen.getByLabelText("Organization name"), { target: { value: "Real organization" } });
  fireEvent.change(screen.getByLabelText("Communities served"), { target: { value: "Rural youth\nLocal families" } });
  fireEvent.change(screen.getByLabelText("Website (optional)"), { target: { value: "example.org" } });
  fireEvent.change(screen.getByLabelText("Year founded (optional)"), { target: { value: "2014" } });
  await act(async () => fireEvent.click(screen.getByText("Save Changes")));
  expect(mockUpdate).toHaveBeenCalledWith(expect.objectContaining({ org_name: "Real organization", target_beneficiaries: ["Rural youth", "Local families"], geographic_focus: ["California", "Oregon"], website: "https://example.org", founding_year: 2014 }));
  expect(screen.getByRole("status")).toHaveTextContent("Profile saved.");
  expect(screen.queryByText("Funding Secured")).not.toBeInTheDocument();
});

test("discard restores saved values and a failed save keeps edits available", async () => {
  mockUpdate.mockRejectedValueOnce(new Error("Save unavailable"));
  render(<Profile />);
  fireEvent.change(screen.getByLabelText("Mission statement"), { target: { value: "Unsaved mission" } });
  await act(async () => fireEvent.click(screen.getByText("Save Changes")));
  expect(screen.getByRole("alert")).toHaveTextContent("Save unavailable");
  expect(screen.getByLabelText("Mission statement")).toHaveValue("Unsaved mission");
  fireEvent.click(screen.getByText("Discard changes"));
  expect(screen.getByLabelText("Mission statement")).toHaveValue("");
  expect(screen.getByLabelText("Service areas")).toHaveValue("California\nOregon");
});
