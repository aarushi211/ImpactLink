// Lay out text line by line so even a paragraph longer than a page is preserved.
export function createProposalPdf(jsPDF, { title, agency = "", organization = "", sections, sectionOrder, date = new Date() }) {
  const doc = new jsPDF({ unit: "pt", format: "letter" });
  const width = doc.internal.pageSize.getWidth();
  const height = doc.internal.pageSize.getHeight();
  const margin = 60;
  const contentWidth = width - margin * 2;
  const bottom = height - 62;
  let y = 82;

  const clean = text => String(text || "")
    .replace(/\r\n?/g, "\n")
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1")
    .replace(/[\u2018\u2019]/g, "'")
    .replace(/[\u201c\u201d]/g, '"')
    .replace(/[\u2013\u2014]/g, "-")
    .replace(/\u2022/g, "-");

  const header = () => {
    doc.setFont("helvetica", "bold");
    doc.setFontSize(9);
    doc.setTextColor(80, 70, 150);
    doc.text("IMPACTLINK | GRANT PROPOSAL", margin, 36);
    doc.setDrawColor(210, 210, 225);
    doc.line(margin, 46, width - margin, 46);
  };
  const ensureSpace = needed => {
    if (y + needed > bottom) {
      doc.addPage();
      header();
      y = 76;
    }
  };
  const write = (text, { size = 11, bold = false, leading = 16, indent = 0, gap = 8 } = {}) => {
    doc.setFont("helvetica", bold ? "bold" : "normal");
    doc.setFontSize(size);
    const lines = doc.splitTextToSize(clean(text), contentWidth - indent);
    for (const line of lines) {
      ensureSpace(leading);
      // A new-page header changes the font, so restore body styling per line.
      doc.setFont("helvetica", bold ? "bold" : "normal");
      doc.setFontSize(size);
      doc.setTextColor(35, 35, 50);
      doc.text(line, margin + indent, y);
      y += leading;
    }
    y += gap;
  };

  header();
  write(title || "Grant Proposal", { size: 22, bold: true, leading: 28, gap: 14 });
  if (agency) write(agency, { size: 11, leading: 16, gap: 4 });
  if (organization) write(organization, { size: 11, leading: 16, gap: 4 });
  write(date.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" }), { size: 10, gap: 22 });

  sectionOrder.forEach((key, index) => {
    const section = sections[key];
    if (!section) return;
    doc.setFont("helvetica", "bold");
    doc.setFontSize(14);
    const heading = `${String(index + 1).padStart(2, "0")}  ${clean(section.title || key)}`;
    const headingLines = doc.splitTextToSize(heading, contentWidth);
    ensureSpace(Math.min(headingLines.length * 20 + 40, bottom - 76));
    write(heading, { size: 14, bold: true, leading: 20, gap: 12 });
    for (const paragraph of clean(section.content).split(/\n\s*\n/)) {
      if (!paragraph.trim()) continue;
      const rows = paragraph.trim().split("\n");
      const structured = rows.some(row => /^\s*(?:[-*]\s|\d+[.)]\s|#{1,6}\s|\|)/.test(row));
      if (!structured) {
        write(rows.map(row => row.trim()).join(" "));
        continue;
      }
      for (const row of rows) {
        if (!row.trim() || /^\s*\|?[\s:|-]+\|\s*$/.test(row)) continue;
        const headingRow = /^\s*#{1,6}\s/.test(row);
        const bullet = /^\s*(?:[-*]\s|\d+[.)]\s)/.test(row);
        write(row.replace(/^\s*#{1,6}\s+/, "").replace(/^\s*\*\s/, "- "), {
          bold: headingRow, indent: bullet ? 12 : 0, gap: 5,
        });
      }
      y += 5;
    }
    y += 14;
  });

  const total = doc.internal.getNumberOfPages();
  for (let page = 1; page <= total; page += 1) {
    doc.setPage(page);
    doc.setDrawColor(210, 210, 225);
    doc.line(margin, height - 44, width - margin, height - 44);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(9);
    doc.setTextColor(110, 110, 125);
    doc.text("Prepared with ImpactLink", margin, height - 28);
    doc.text(`Page ${page} of ${total}`, width - margin, height - 28, { align: "right" });
  }
  return doc;
}
