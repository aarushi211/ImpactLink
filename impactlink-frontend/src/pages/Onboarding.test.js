import { act, fireEvent, render, screen } from "@testing-library/react";
import Onboarding from "./Onboarding";

const mockNavigate = jest.fn();
const mockUpdate = jest.fn();
let mockProfile;
jest.mock("react-router-dom", () => ({ useNavigate: () => mockNavigate }), { virtual: true });
jest.mock("../context/AuthContext", () => ({ useAuth: () => ({ profile: mockProfile, updateProfile: mockUpdate }) }));
beforeEach(() => {
  jest.clearAllMocks();
  mockProfile = { org_name: "My Organization", email: "demo@example.test", geographic_focus: ["California", "Oregon"], privacy_redaction_terms: ["Private name"], collab_open: false };
  mockUpdate.mockResolvedValue({});
});

test("onboarding saves each step and finishes with eligibility defaults", async () => {
  render(<Onboarding />);
  fireEvent.change(screen.getByLabelText("Organization name"), { target: { value: "Watershed Partnership" } });
  fireEvent.change(screen.getByLabelText("Mission statement"), { target: { value: "Restore local watersheds" } });
  await act(async () => fireEvent.click(screen.getByText("Save & continue")));
  expect(mockUpdate).toHaveBeenLastCalledWith(expect.objectContaining({ org_name: "Watershed Partnership", mission: "Restore local watersheds", onboarding_completed: false, privacy_redaction_terms: ["Private name"] }));
  expect(screen.getByLabelText("Service areas")).toHaveValue("California\nOregon");
  fireEvent.change(screen.getByLabelText("Key programs and activities"), { target: { value: "Volunteer habitat restoration\nWater monitoring" } });
  fireEvent.change(screen.getByLabelText("Communities served"), { target: { value: "Rural communities" } });
  await act(async () => fireEvent.click(screen.getByText("Save & continue")));
  fireEvent.change(screen.getByLabelText("Applicant type"), { target: { value: "nonprofit" } });
  fireEvent.change(screen.getByLabelText("Project U.S. states"), { target: { value: "CA" } });
  await act(async () => fireEvent.click(screen.getByText("Finish setup")));
  expect(mockUpdate).toHaveBeenLastCalledWith(expect.objectContaining({ onboarding_completed: true, applicant_type: "nonprofit", project_states: ["CA"], geographic_focus: ["California", "Oregon"], key_activities: ["Volunteer habitat restoration", "Water monitoring"], target_beneficiaries: ["Rural communities"], collab_open: false }));
  expect(mockNavigate).toHaveBeenCalledWith("/dashboard");
});

test("finishing later saves partial information and failed saves keep the form", async () => {
  mockUpdate.mockRejectedValueOnce(new Error("Unable to save right now"));
  render(<Onboarding />);
  fireEvent.change(screen.getByLabelText("Mission statement"), { target: { value: "A mission in progress" } });
  await act(async () => fireEvent.click(screen.getByText("Save & finish later")));
  expect(screen.getByRole("alert")).toHaveTextContent("Unable to save right now");
  expect(screen.getByLabelText("Mission statement")).toHaveValue("A mission in progress");
  expect(mockNavigate).not.toHaveBeenCalled();
  await act(async () => fireEvent.click(screen.getByText("Save & finish later")));
  expect(mockUpdate).toHaveBeenLastCalledWith(expect.objectContaining({ mission: "A mission in progress", onboarding_completed: false }));
  expect(mockNavigate).toHaveBeenCalledWith("/dashboard");
});
