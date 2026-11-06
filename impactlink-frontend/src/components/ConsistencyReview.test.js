import { render, screen } from "@testing-library/react";
import ConsistencyReview from "./ConsistencyReview";

test("unavailable and stale reviews are never shown as a pass", () => {
  const { rerender } = render(<ConsistencyReview review={{ status: "unavailable", reason: "Check failed", issues: [] }} />);
  expect(screen.getByText("Consistency check unavailable")).toBeInTheDocument();
  expect(screen.queryByText("AI check found no inconsistencies")).not.toBeInTheDocument();
  rerender(<ConsistencyReview review={{ status: "stale", issues: [{ section: "summary", severity: "high", issue: "Counts differ", fix: "Confirm actual participants" }] }} />);
  expect(screen.getByText(/Counts differ/)).toBeInTheDocument();
  expect(screen.getByText(/Listed findings refer to earlier text/)).toBeInTheDocument();
  expect(screen.getByText(/does not verify facts/)).toBeInTheDocument();
});

test("legacy proposals remain unchecked and policy or loading can disable another AI check", () => {
  render(<ConsistencyReview review={null} onCheck={jest.fn()} disabled />);
  expect(screen.getByText("No recorded consistency check")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Check full proposal consistency" })).toBeDisabled();
});
