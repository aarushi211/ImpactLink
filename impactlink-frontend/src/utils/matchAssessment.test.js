import { matchFingerprint } from "./matchAssessment";

test("match identity survives property ordering and detects text and grant changes", () => {
  const proposal = { sections: { summary: { content: "Updated proposal.", title: "Summary" } }, eligibility_context: { project_states: ["CA"] } };
  const reordered = { eligibility_context: { project_states: ["CA"] }, sections: { summary: { title: "Summary", content: "Updated proposal." } } };
  expect(matchFingerprint("g1", proposal)).toBe(matchFingerprint("g1", reordered));
  expect(matchFingerprint("g1", proposal)).not.toBe(matchFingerprint("g2", proposal));
  expect(matchFingerprint("g1", proposal)).not.toBe(matchFingerprint("g1", { ...proposal, sections: { summary: { title: "Summary", content: "Manual edit." } } }));
});
