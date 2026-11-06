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
