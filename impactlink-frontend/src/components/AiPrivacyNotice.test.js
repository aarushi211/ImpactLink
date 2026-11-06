import { fireEvent, render, screen, act } from "@testing-library/react";
import AiPrivacyNotice from "./AiPrivacyNotice";
import api from "../services/api";

jest.mock("../services/api", () => ({ __esModule: true, default: { post: jest.fn() } }));

test("privacy limitations and original storage are visible without a consent popup or API call", () => {
  render(<AiPrivacyNotice />);
  expect(screen.getByText(/local name detection and identifier masking/)).toBeInTheDocument();
  fireEvent.click(screen.getByText(/AI privacy/));
  expect(screen.getByText(/Automatic checks can still miss names/)).toBeInTheDocument();
  expect(screen.getByText(/Provider retention policies still apply/)).toBeInTheDocument();
  expect(api.post).not.toHaveBeenCalled();
});

test("preview calls only the local redaction endpoint and clears stale previews after editing", async () => {
  api.post.mockResolvedValue({ data: { text: "Email: [REDACTED_EMAIL]", counts: { email: 1 } } });
  render(<AiPrivacyNotice preview />);
  fireEvent.click(screen.getByText(/AI privacy/));
  fireEvent.change(screen.getByLabelText("Text to preview for AI"), { target: { value: "Email: jane@example.org" } });
  await act(async () => { fireEvent.click(screen.getByText("Preview AI redaction")); });
  expect(api.post).toHaveBeenCalledWith("/api/privacy/preview", { text: "Email: jane@example.org" });
  expect(screen.getByLabelText("Redacted preview")).toHaveTextContent("[REDACTED_EMAIL]");
  fireEvent.change(screen.getByLabelText("Text to preview for AI"), { target: { value: "New text" } });
  expect(screen.queryByLabelText("Redacted preview")).not.toBeInTheDocument();
});

test("upload feedback contains category counts rather than identifier values", () => {
  render(<AiPrivacyNotice counts={{ email: 2, ssn: 1 }} />);
  expect(screen.getByRole("status")).toHaveTextContent("email: 2, ssn: 1");
});

test("unsaved protected terms are previewed and changing them clears an older preview", async () => {
  api.post.mockResolvedValue({ data: { text: "[REDACTED_CUSTOM]", counts: { custom: 1 } } });
  const { rerender } = render(<AiPrivacyNotice preview protectedTerms={["Zyqra"]} />);
  fireEvent.click(screen.getByText(/AI privacy/));
  fireEvent.change(screen.getByLabelText("Text to preview for AI"), { target: { value: "Zyqra" } });
  await act(async () => { fireEvent.click(screen.getByText("Preview AI redaction")); });
  expect(api.post).toHaveBeenCalledWith("/api/privacy/preview", { text: "Zyqra", custom_terms: ["Zyqra"] });
  expect(screen.getByLabelText("Redacted preview")).toHaveTextContent("[REDACTED_CUSTOM]");
  rerender(<AiPrivacyNotice preview protectedTerms={["Other term"]} />);
  expect(screen.queryByLabelText("Redacted preview")).not.toBeInTheDocument();
});
