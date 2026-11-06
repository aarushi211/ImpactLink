import { render, screen } from "@testing-library/react";
import EligibilityStatus from "./EligibilityStatus";

test("unknown eligibility is presented as unverified rather than approved", () => {
  render(<EligibilityStatus result={{ status: "unverified", checks: [{ criterion: "geography", message: "Service area needs confirmation" }] }} detailed />);
  expect(screen.getByText("Eligibility needs confirmation")).toBeInTheDocument();
  expect(screen.getByText("Service area needs confirmation")).toBeInTheDocument();
  expect(screen.queryByText("Basic eligibility checks passed")).not.toBeInTheDocument();
});

test("passed basic checks are not described as guaranteed eligibility", () => {
  render(<EligibilityStatus result={{ status: "potentially_eligible" }} />);
  expect(screen.getByText("Basic eligibility checks passed")).toBeInTheDocument();
});
