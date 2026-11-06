import { useState } from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { ApplicationRequirementsEditor, ApplicationReview } from "./ApplicationRequirements";
import { emptyApplicationSpec } from "../utils/application";

function Editor() {
  const [spec, setSpec] = useState(emptyApplicationSpec());
  return <><ApplicationRequirementsEditor value={spec} onChange={setSpec} /><output data-testid="spec">{JSON.stringify(spec)}</output></>;
}

test("records custom questions, exact limits and ordering", () => {
  render(<Editor />);
  fireEvent.click(screen.getByText("Application structure and requirements"));
  fireEvent.change(screen.getByLabelText("Application stage"), { target: { value: "loi" } });
  fireEvent.click(screen.getByText("Add application question"));
  fireEvent.change(screen.getByLabelText("Question title 1"), { target: { value: "Why this work?" } });
  fireEvent.change(screen.getByLabelText("Maximum words 1"), { target: { value: "100" } });
  fireEvent.change(screen.getByLabelText("Maximum characters 1"), { target: { value: "750" } });
  fireEvent.click(screen.getByText("Add work plan"));
  fireEvent.click(screen.getByText("Move question 2 up"));
  const spec = JSON.parse(screen.getByTestId("spec").textContent);
  expect(spec.stage).toBe("loi");
  expect(spec.sections[0].title).toBe("Work plan and timeline");
  expect(spec.sections[1]).toMatchObject({ title: "Why this work?", max_words: 100, max_characters: 750 });
});

test("checklist readiness is self-reported and does not count documents for another stage", () => {
  const onChange = jest.fn();
  const spec = { ...emptyApplicationSpec("loi"), sections: [{ key: "need", title: "Need", max_words: 2, required: true }], attachments: [{ id: "loi", title: "Support letter", stage: "loi", required: true, status: "not_started" }, { id: "financial", title: "Audited accounts", stage: "reporting", required: true, status: "not_started" }] };
  render(<ApplicationReview spec={spec} sections={{ need: "one two three" }} onChange={onChange} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Need");
  expect(screen.getByText(/3 \/ 2 words/)).toBeInTheDocument();
  expect(screen.queryByText("Audited accounts")).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Checklist status: Support letter"), { target: { value: "ready" } });
  expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ attachments: [expect.objectContaining({ id: "loi", status: "ready" }), expect.objectContaining({ id: "financial", status: "not_started" })] }));
  expect(screen.getByText(/Submission readiness is not verified/)).toBeInTheDocument();
});

test("records AI policy conditions and source without assuming permission", () => {
  render(<Editor />);
  expect(screen.getByText(/Funder AI policy unknown/)).toBeInTheDocument();
  fireEvent.click(screen.getByText("Application structure and requirements"));
  fireEvent.change(screen.getByLabelText("Funder AI-use policy"), { target: { value: "prohibited" } });
  fireEvent.change(screen.getByLabelText("AI policy source"), { target: { value: "Funder RFP page 8" } });
  fireEvent.change(screen.getByLabelText("AI policy conditions"), { target: { value: "No generative AI in applications" } });
  const spec = JSON.parse(screen.getByTestId("spec").textContent);
  expect(spec.ai_policy).toEqual({ status: "prohibited", source_reference: "Funder RFP page 8", notes: "No generative AI in applications", disclosure_ready: false });
  expect(screen.getByText(/AI drafting and revision are disabled/)).toBeInTheDocument();
});

test("disclosure is a self-reported checklist item and does not insert invented disclosure text", () => {
  const spec = { ...emptyApplicationSpec(), ai_policy: { status: "disclosure_required", source_reference: "RFP", notes: "Use portal disclosure field", disclosure_ready: false } };
  const onChange = jest.fn();
  render(<ApplicationReview spec={spec} sections={{ summary: "Original proposal text" }} onChange={onChange} />);
  expect(screen.getByText(/does not submit it for you/)).toBeInTheDocument();
  fireEvent.click(screen.getByLabelText("Required AI disclosure is ready"));
  expect(onChange).toHaveBeenCalledWith({ ...spec, ai_policy: { ...spec.ai_policy, disclosure_ready: true } });
});
