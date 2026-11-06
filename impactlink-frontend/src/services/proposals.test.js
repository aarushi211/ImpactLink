import { proposalContext, stageProposalMatch, workItemPath } from "./proposals";

beforeEach(() => sessionStorage.clear());

test("matching uses the latest generated/revised sections instead of stale upload text", () => {
  const context = proposalContext({ title: "Restoration", proposal_context: { raw_text: "Old upload", sections: { summary: { content: "Old version" } } }, sections: { summary: { title: "Summary", content: "The latest restoration plan" } } });
  expect(context.sections.summary.content).toBe("The latest restoration plan");
  expect(context.raw_text).not.toContain("Old upload");
  expect(context.raw_text).toContain("The latest restoration plan");
});

test("Find Grants stages a one-time automatic matching request with full proposal text", () => {
  sessionStorage.setItem("grants_searchMode", "ai");
  const route = stageProposalMatch({ id: "built-1", _type: "build", title: "Restoration", sections: { summary: { content: "Restore native habitat" } } });
  expect(route).toBe("/grants?proposal=built-1");
  expect(JSON.parse(sessionStorage.getItem("grant_match_request")).proposal_context.sections.summary.content).toBe("Restore native habitat");
  expect(sessionStorage.getItem("grants_searchMode")).toBe("filter");
});

test.each([
  ["build", "/build?load=item"], ["draft", "/draft?load=item&grant=123"],
  ["budget", "/budget?load=item"], ["grant", "/grants/123"],
])("saved %s records link to their specific saved content", (_type, path) => {
  expect(workItemPath({ id: "item", _type, grant_id: "123" })).toBe(path);
});
