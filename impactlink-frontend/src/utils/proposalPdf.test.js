import { createProposalPdf } from "./proposalPdf";

class PdfRecorder {
  constructor() {
    this.pages = [[]]; this.page = 0; this.size = 11;
    this.internal = { pageSize: { getWidth: () => 612, getHeight: () => 792 }, getNumberOfPages: () => this.pages.length };
  }
  setFont() {}
  setFontSize(size) { this.size = size; }
  setTextColor() {}
  setDrawColor() {}
  line() {}
  addPage() { this.pages.push([]); this.page = this.pages.length - 1; }
  setPage(page) { this.page = page - 1; }
  text(text, x, y) { this.pages[this.page].push({ text, x, y, size: this.size }); }
  splitTextToSize(text, width) {
    const limit = Math.max(1, Math.floor(width / (this.size * 0.55)));
    const lines = []; let line = "";
    for (const word of text.split(/\s+/)) {
      if (line && (line + " " + word).length > limit) { lines.push(line); line = ""; }
      line = line ? line + " " + word : word;
    }
    if (line) lines.push(line);
    return lines;
  }
}

test("a paragraph longer than a page is fully preserved across readable pages", () => {
  const content = Array.from({ length: 1500 }, (_, i) => `word${i}`).join(" ");
  const doc = createProposalPdf(PdfRecorder, { title: "Creek restoration", sections: { summary: { title: "Summary", content } }, sectionOrder: ["summary"] });
  expect(doc.pages.length).toBeGreaterThan(2);
  const body = doc.pages.flat().filter(line => line.y >= 60 && line.y <= 730);
  const printed = body.map(line => line.text).join(" ");
  for (let i = 0; i < 1500; i += 1) expect(printed).toContain(`word${i}`);
  expect(doc.pages.flat().filter(line => line.text.includes("word")).every(line => line.y >= 60 && line.y <= 730 && line.size === 11)).toBe(true);
  doc.pages.forEach((page, index) => expect(page.some(line => line.text === `Page ${index + 1} of ${doc.pages.length}`)).toBe(true));
});

test("metadata wraps, headings stay with text, and lists remain separate", () => {
  const doc = createProposalPdf(PdfRecorder, {
    title: "Community restoration", agency: "A long agency name ".repeat(30), organization: "Demo nonprofit",
    sections: { budget: { title: "Budget", content: "## Personnel\n- Volunteers: training\n- Equipment: supplies\n\n**Total:** $10,000" } }, sectionOrder: ["budget"],
  });
  const printed = doc.pages.flat().map(line => line.text).join("\n");
  expect(printed).toContain("Personnel");
  expect(printed).toContain("- Volunteers: training\n- Equipment: supplies");
  expect(printed).toContain("Total: $10,000");
  expect(printed).not.toContain("**");
  expect(printed).not.toContain("##");
});
