import { render, screen } from "@testing-library/react";
import GrantFreshness from "./GrantFreshness";

test("shows the official source and verification date", () => {
  render(<GrantFreshness grant={{ source: "grants_gov", source_url: "https://www.grants.gov/search-results-detail/123", last_verified_at: "2026-11-06T00:00:00Z" }} link />);
  expect(screen.getByRole("link", { name: "Grants.gov" })).toHaveAttribute("href", "https://www.grants.gov/search-results-detail/123");
  expect(screen.getByText(/Checked/)).toBeInTheDocument();
});

test("does not invent a verification date or render unsafe links", () => {
  render(<GrantFreshness grant={{ source: "california", source_url: "javascript:alert(1)", last_verified_at: "invalid" }} link />);
  expect(screen.getByText(/Not yet verified/)).toBeInTheDocument();
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
});
