import { applicationCheck, lengthCheck, attachmentStatuses } from "./application";

test("counts Unicode code points and normalized line breaks consistently with the backend", () => {
  expect(lengthCheck("é 😀\r\nOK", { max_words: 3, max_characters: 6 })).toEqual({ words: 3, characters: 6, within_limits: true });
  expect(lengthCheck("é 😀\nOK!", { max_characters: 6 }).within_limits).toBe(false);
});

test("enforces required custom answers and both limit types", () => {
  const spec = { stage: "loi", sections: [{ key: "need", required: true, max_words: 3 }, { key: "delivery", required: true, max_characters: 5 }] };
  const report = applicationCheck(spec, { need: { content: "one two three four" } });
  expect(report).toEqual({ can_finalize_text: false, missing: ["delivery"], over: ["need"] });
  expect(applicationCheck(spec, { need: "Short need", delivery: "Done" }).can_finalize_text).toBe(true);
});

test("generic structure does not invent mandatory funder questions", () => {
  expect(applicationCheck({ stage: "full_proposal", sections: [] }, { proposal: "An existing proposal" }).can_finalize_text).toBe(true);
  expect(applicationCheck({ stage: "loi", sections: [] }, {}).missing).toHaveLength(3);
  expect(attachmentStatuses({ attachments: [{ id: "letter", status: "in_progress" }] })).toEqual({ letter: "in_progress" });
});
