import { organizationForm, organizationUpdates } from "./organization";

test("profile editing preserves all saved regions and private terms", () => {
  const profile = { org_name: "Example", geographic_focus: ["California", "Oregon"], privacy_redaction_terms: ["Private case"], sdgs: ["SDG 9: Existing custom label"], collab_open: false };
  expect(organizationUpdates(organizationForm(profile))).toEqual(expect.objectContaining(profile));
});

test.each(["javascript:alert(1)", "ftp://example.org", "https://user:secret@example.org", "https://"])('invalid website %s cannot be saved', website => {
  expect(() => organizationUpdates({ ...organizationForm({ org_name: "Example" }), website })).toThrow(/website/);
});

test("bare domains are normalized and unknown founding years remain empty", () => {
  expect(organizationUpdates({ ...organizationForm({ org_name: "Example" }), website: "example.org" })).toEqual(expect.objectContaining({ website: "https://example.org", founding_year: null }));
});
