import { act, fireEvent, render, screen } from "@testing-library/react";
import Login from "./Login";
const mockNavigate = jest.fn();
const mockLogin = jest.fn();
const mockRegister = jest.fn();
const mockGoogle = jest.fn();
jest.mock("react-router-dom", () => ({ useNavigate: () => mockNavigate }), { virtual: true });
jest.mock("../context/AuthContext.js", () => ({ useAuth: () => ({ login: mockLogin, register: mockRegister, loginWithGoogle: mockGoogle }) }));
beforeEach(() => jest.clearAllMocks());

test("a new Google account goes to organization setup without registering again", async () => {
  mockGoogle.mockResolvedValue({ isNewUser: true, profile: { onboarding_completed: false } });
  render(<Login />);
  await act(async () => fireEvent.click(screen.getByText("Continue with Google")));
  expect(mockNavigate).toHaveBeenCalledWith("/onboarding");
  expect(mockRegister).not.toHaveBeenCalled();
});

test("email registration creates the account once then opens onboarding", async () => {
  mockRegister.mockResolvedValue({});
  render(<Login />);
  fireEvent.click(screen.getByRole("button", { name: "Create account", exact: true }));
  fireEvent.change(screen.getByLabelText("Organization name"), { target: { value: "New organization" } });
  fireEvent.change(screen.getByLabelText("Work email"), { target: { value: "org@example.test" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "a-long-password" } });
  await act(async () => fireEvent.click(screen.getByText("Create account & continue")));
  expect(mockRegister).toHaveBeenCalledTimes(1);
  expect(mockRegister).toHaveBeenCalledWith("org@example.test", "a-long-password", "New organization");
  expect(mockNavigate).toHaveBeenCalledWith("/onboarding");
});

test.each([[false, "/onboarding"], [true, "/dashboard"], [undefined, "/dashboard"]])("returning users with setup status %s land on %s", async (completed, path) => {
  mockLogin.mockResolvedValue({ onboarding_completed: completed });
  render(<Login />);
  fireEvent.change(screen.getByLabelText("Work email"), { target: { value: "org@example.test" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "password" } });
  await act(async () => fireEvent.click(screen.getByText("Sign in to ImpactLink")));
  expect(mockNavigate).toHaveBeenCalledWith(path);
});
