import { render, screen, fireEvent, act } from "@testing-library/react";
import Profile from "./Profile";
jest.mock("../services/api", () => ({ __esModule: true, default: { post: jest.fn() } }));

const mockUpdate = jest.fn();
const mockProfile = { org_name: "Demo nonprofit", email: "demo@example.test", sdgs: [] };
jest.mock("react-router-dom", () => ({ useNavigate: () => jest.fn() }), { virtual: true });
jest.mock("../components", () => ({ Nav: () => null }));
jest.mock("../context/AuthContext.js", () => ({ useAuth: () => ({ profile: mockProfile, updateProfile: mockUpdate, logout: jest.fn() }) }));

test("eligibility fields are explicitly declared and saved with the profile", async () => {
  mockUpdate.mockResolvedValue();
  render(<Profile />);
  expect(screen.getByLabelText("Applicant type")).toHaveValue("");
  fireEvent.change(screen.getByLabelText("Applicant type"), { target: { value: "public_agency" } });
  fireEvent.change(screen.getByLabelText("Project U.S. states"), { target: { value: "CA, New York" } });
  fireEvent.change(screen.getByLabelText("Names and phrases to mask"), { target: { value: "Zyqra\nPrivate case 44" } });
  await act(async () => { fireEvent.click(screen.getByText("Save Changes")); });
  expect(mockUpdate).toHaveBeenCalledWith(expect.objectContaining({ applicant_type: "public_agency", project_states: ["CA", "New York"], privacy_redaction_terms: ["Zyqra", "Private case 44"] }));
});
