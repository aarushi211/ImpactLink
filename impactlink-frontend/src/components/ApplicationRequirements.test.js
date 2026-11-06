import { useState } from "react";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { ApplicationRequirementsEditor, ApplicationReview } from "./ApplicationRequirements";
import { emptyApplicationSpec } from "../utils/application";
import api from "../services/api";
jest.mock("../services/api", () => ({ __esModule: true, default: { post: jest.fn() } }));

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

test("grant extraction previews evidence and only replaces setup when applied", async () => {
  const onChange = jest.fn();
  const spec = { ...emptyApplicationSpec("loi"), sections: [{ key: "need", title: "Describe the need", instructions: "Describe the need in 100 words.", max_words: 100, required: true }] };
  api.post.mockResolvedValue({ data: { application_spec: spec, evidence: [{ field: "Describe the need", quote: "Describe the need in 100 words." }], warnings: [] } });
  render(<ApplicationRequirementsEditor grant={{ grant_id: "g-1" }} value={emptyApplicationSpec()} onChange={onChange} />);
  await act(async () => { fireEvent.click(screen.getByText("Prefill from selected grant")); });
  expect(api.post).toHaveBeenCalledWith("/api/grants/g-1/application-requirements");
  expect(onChange).not.toHaveBeenCalled();
  expect(screen.getByText("Describe the need in 100 words.")).toBeInTheDocument();
  fireEvent.click(screen.getByText("Use extracted setup"));
  expect(onChange).toHaveBeenCalledWith(spec);
});

test("a late extraction for a previous grant is discarded", async () => {
  let finish;
  api.post.mockReturnValue(new Promise(resolve => { finish = resolve; }));
  const { rerender } = render(<ApplicationRequirementsEditor grant={{ grant_id: "first" }} onChange={jest.fn()} />);
  fireEvent.click(screen.getByText("Prefill from selected grant"));
  rerender(<ApplicationRequirementsEditor grant={{ grant_id: "second" }} onChange={jest.fn()} />);
  await act(async () => { finish({ data: { application_spec: emptyApplicationSpec(), evidence: [], warnings: [] } }); });
  expect(screen.queryByLabelText("Extracted requirements preview")).not.toBeInTheDocument();
});

test("checklist saving has pending and success feedback and clears confirmation after edits", async () => {
  let finish;
  const onSave = jest.fn(() => new Promise(resolve => { finish = resolve; }));
  const spec = { ...emptyApplicationSpec(), ai_policy: { status: "disclosure_required", disclosure_ready: true } };
  const { rerender } = render(<ApplicationReview spec={spec} sections={{}} onChange={jest.fn()} onSave={onSave} />);
  fireEvent.click(screen.getByText("Save application checklist"));
  expect(screen.getByText("Saving checklist...")).toBeDisabled();
  expect(screen.getByLabelText("Required AI disclosure is ready")).toBeDisabled();
  await act(async () => { finish({ id: "saved" }); });
  expect(screen.getByText("Checklist saved.")).toBeInTheDocument();
  expect(onSave).toHaveBeenCalledWith(spec);
  rerender(<ApplicationReview spec={{ ...spec, ai_policy: { ...spec.ai_policy, disclosure_ready: false } }} sections={{}} onChange={jest.fn()} onSave={onSave} />);
  expect(screen.queryByText("Checklist saved.")).not.toBeInTheDocument();
});

test("checklist failures are shown beside the button and allow retry", async () => {
  const onSave = jest.fn().mockRejectedValueOnce(new Error("Could not save checkpoint")).mockResolvedValue({ id: "saved" });
  render(<ApplicationReview spec={emptyApplicationSpec()} sections={{}} onChange={jest.fn()} onSave={onSave} />);
  await act(async () => { fireEvent.click(screen.getByText("Save application checklist")); });
  expect(screen.getByRole("alert")).toHaveTextContent("Could not save checkpoint");
  expect(screen.queryByText("Checklist saved.")).not.toBeInTheDocument();
  await act(async () => { fireEvent.click(screen.getByText("Save application checklist")); });
  expect(screen.getByText("Checklist saved.")).toBeInTheDocument();
});
