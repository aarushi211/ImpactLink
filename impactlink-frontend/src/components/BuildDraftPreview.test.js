import { render, screen } from "@testing-library/react";
import BuildDraftPreview, { buildPreviewReducer as reduce } from "./BuildDraftPreview";

test("interleaved section tokens stay separate and reviewed text replaces the initial preview", () => {
  let sections = reduce({}, { type: "section_start", section_key: "summary", title: "Summary" });
  sections = reduce(sections, { type: "section_start", section_key: "budget", title: "Budget" });
  sections = reduce(sections, { type: "token", section_key: "summary", content: "Our " });
  sections = reduce(sections, { type: "token", section_key: "budget", content: "$100" });
  sections = reduce(sections, { type: "token", section_key: "summary", content: "project" });
  const { rerender } = render(<BuildDraftPreview sections={sections} />);
  expect(screen.getByText("Our project")).toBeInTheDocument();
  expect(screen.getByText("$100")).toBeInTheDocument();
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
  sections = reduce(sections, { type: "section_complete", section_key: "summary", section: { title: "Summary", content: "Reviewed project summary", score: 90 } });
  rerender(<BuildDraftPreview sections={sections} />);
  expect(screen.getByText("Reviewed project summary")).toBeInTheDocument();
  expect(screen.queryByText("Our project")).not.toBeInTheDocument();
  expect(screen.getByText("$100")).toBeInTheDocument();
});

test("an interrupted preview is marked incomplete and a new run clears it", () => {
  const sections = reduce({}, { type: "token", section_key: "summary", content: "Partial draft" });
  render(<BuildDraftPreview sections={sections} interrupted />);
  expect(screen.getByText(/preview may be incomplete/)).toBeInTheDocument();
  expect(reduce(sections, { type: "reset" })).toEqual({});
});
