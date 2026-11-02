import { useEffect, useState, useRef } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { Nav } from "../components";
import useGrants from "../hooks/useGrants";
import { useAuth } from "../context/AuthContext";
import useWorkStore from "../hooks/useWorkStore";
import useProposalSession from "../hooks/useProposalSession";
import api from "../services/api";

// Loads jsPDF from CDN once via a script tag
function loadJsPDF() {
  return new Promise((resolve, reject) => {
    if (window.jspdf) return resolve();
    const script = document.createElement("script");
    script.src = "https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js";
    script.onload = resolve;
    script.onerror = reject;
    document.head.appendChild(script);
  });
}

const SECTION_ICONS = {
  executive_summary:       "01",
  problem_statement:       "02",
  proposed_solution:       "03",
  target_beneficiaries:    "04",
  organizational_capacity: "05",
  evaluation_plan:         "06",
  budget_narrative:        "07",
  sustainability:          "08",
};

function getSectionTitle(key, section) {
  if (key === "uploaded_content") return "Proposal";
  return section?.title || key.replace(/_/g, " ").replace(/\b\w/g, char => char.toUpperCase());
}

function normalizeSectionMap(sectionMap) {
  const normalized = { ...(sectionMap || {}) };
  if (normalized.uploaded_content && !normalized.proposal) {
    normalized.proposal = {
      ...normalized.uploaded_content,
      title: "Proposal",
    };
    delete normalized.uploaded_content;
  }
  return normalized;
}

// ── Formatting toolbar actions ─────────────────────────
function applyFormat(textarea, format) {
  if (!textarea) return null;
  const start = textarea.selectionStart;
  const end   = textarea.selectionEnd;
  const sel   = textarea.value.slice(start, end);
  const pre   = textarea.value.slice(0, start);
  const post  = textarea.value.slice(end);

  let newText = textarea.value;
  let newCursorStart = start;
  let newCursorEnd   = end;

  if (format === "bold") {
    newText = pre + `**${sel}**` + post;
    newCursorEnd = end + 4;
  } else if (format === "bullet") {
    const lines = sel.split("\n").map(l => `• ${l}`).join("\n");
    newText = pre + lines + post;
    newCursorEnd = start + lines.length;
  } else if (format === "h2") {
    newText = pre + `\n## ${sel}\n` + post;
    newCursorEnd = start + sel.length + 5;
  } else if (format === "table") {
    const table = sel
      ? `| Item | Details |\n| --- | --- |\n| ${sel.replace(/\n/g, " | ")} |  |`
      : "| Item | Details |\n| --- | --- |\n|  |  |";
    newText = pre + table + post;
    newCursorEnd = start + table.length;
  }
  return { newText, newCursorStart, newCursorEnd };
}

function createTextDiff(oldText, newText) {
  const oldTokens = Array.from(oldText);
  const newTokens = Array.from(newText);
  let prefixLength = 0;
  while (
    prefixLength < oldTokens.length
    && prefixLength < newTokens.length
    && oldTokens[prefixLength] === newTokens[prefixLength]
  ) {
    prefixLength += 1;
  }

  let suffixLength = 0;
  while (
    suffixLength < oldTokens.length - prefixLength
    && suffixLength < newTokens.length - prefixLength
    && oldTokens[oldTokens.length - suffixLength - 1]
      === newTokens[newTokens.length - suffixLength - 1]
  ) {
    suffixLength += 1;
  }

  const oldMiddle = oldTokens.slice(prefixLength, oldTokens.length - suffixLength);
  const newMiddle = newTokens.slice(prefixLength, newTokens.length - suffixLength);
  const middleDiff = [];
  const appendMiddle = (type, text) => {
    const previous = middleDiff[middleDiff.length - 1];
    if (previous?.type === type) previous.text += text;
    else middleDiff.push({ type, text });
  };

  if (!oldMiddle.length) {
    if (newMiddle.length) appendMiddle("add", newMiddle.join(""));
  } else if (!newMiddle.length) {
    appendMiddle("remove", oldMiddle.join(""));
  } else {
    const maxDistance = oldMiddle.length + newMiddle.length;
    const frontier = new Map([[1, 0]]);
    const trace = [];
    let completed = false;
    let distance = 0;
    let snapshotEntries = 0;

    for (; distance <= maxDistance; distance += 1) {
      snapshotEntries += frontier.size;
      if (snapshotEntries > 4000000) break;
      trace.push(new Map(frontier));
      for (let diagonal = -distance; diagonal <= distance; diagonal += 2) {
        let oldIndex;
        if (
          diagonal === -distance
          || (diagonal !== distance
            && (frontier.get(diagonal - 1) ?? -1) < (frontier.get(diagonal + 1) ?? -1))
        ) {
          oldIndex = frontier.get(diagonal + 1) ?? 0;
        } else {
          oldIndex = (frontier.get(diagonal - 1) ?? 0) + 1;
        }
        let newIndex = oldIndex - diagonal;
        while (
          oldIndex < oldMiddle.length
          && newIndex < newMiddle.length
          && oldMiddle[oldIndex] === newMiddle[newIndex]
        ) {
          oldIndex += 1;
          newIndex += 1;
        }
        frontier.set(diagonal, oldIndex);
        if (oldIndex >= oldMiddle.length && newIndex >= newMiddle.length) {
          completed = true;
          break;
        }
      }
      if (completed) break;
    }

    if (!completed) {
      appendMiddle("remove", oldMiddle.join(""));
      appendMiddle("add", newMiddle.join(""));
    } else {
      const reversed = [];
      let oldIndex = oldMiddle.length;
      let newIndex = newMiddle.length;
      for (let step = distance; step >= 0; step -= 1) {
        const previousFrontier = trace[step];
        const diagonal = oldIndex - newIndex;
        const previousDiagonal = (
          diagonal === -step
          || (diagonal !== step
            && (previousFrontier.get(diagonal - 1) ?? -1)
              < (previousFrontier.get(diagonal + 1) ?? -1))
        ) ? diagonal + 1 : diagonal - 1;
        const previousOldIndex = previousFrontier.get(previousDiagonal) ?? 0;
        const previousNewIndex = previousOldIndex - previousDiagonal;

        while (oldIndex > previousOldIndex && newIndex > previousNewIndex) {
          reversed.push({ type: "equal", text: oldMiddle[oldIndex - 1] });
          oldIndex -= 1;
          newIndex -= 1;
        }
        if (step > 0) {
          if (oldIndex === previousOldIndex) {
            reversed.push({ type: "add", text: newMiddle[newIndex - 1] });
            newIndex -= 1;
          } else {
            reversed.push({ type: "remove", text: oldMiddle[oldIndex - 1] });
            oldIndex -= 1;
          }
        }
      }
      reversed.reverse().forEach(segment => appendMiddle(segment.type, segment.text));
    }
  }

  const result = [];
  if (prefixLength) result.push({ type: "equal", text: oldTokens.slice(0, prefixLength).join("") });
  result.push(...middleDiff);
  if (suffixLength) result.push({ type: "equal", text: oldTokens.slice(oldTokens.length - suffixLength).join("") });

  const merged = [];
  const append = (type, text) => {
    if (!text) return;
    const previous = merged[merged.length - 1];
    if (previous?.type === type) previous.text += text;
    else merged.push({ type, text });
  };
  result.forEach(segment => append(segment.type, segment.text));
  return merged;
}

function getVisibleDiffSegments(tokens, variant, fallback, includeRemovals = false) {
  const source = typeof fallback === "string" ? fallback : "";
  const visibleTypes = variant === "original"
    ? new Set(["equal", "remove"])
    : new Set(includeRemovals ? ["equal", "add", "remove"] : ["equal", "add"]);
  const visibleSegments = Array.isArray(tokens)
    ? tokens.filter(token => visibleTypes.has(token.type))
    : [];
  if (visibleSegments
    .filter(token => variant === "original" ? token.type !== "add" : token.type !== "remove")
    .map(token => token.text)
    .join("") === source) {
    return visibleSegments;
  }
  return source ? [{ type: "equal", text: source }] : [];
}

function sliceDiffSegments(segments, start, end) {
  let offset = 0;
  const result = [];
  for (const segment of segments) {
    const segmentEnd = offset + segment.text.length;
    const from = Math.max(start, offset);
    const to = Math.min(end, segmentEnd);
    if (from < to) {
      result.push({ type: segment.type, text: segment.text.slice(from - offset, to - offset) });
    }
    offset = segmentEnd;
    if (offset >= end) break;
  }
  return result;
}

function composeRevisedDiffTokens(draftedTokens, editTokens, draftedText, revisedText) {
  const sourceTokens = Array.isArray(draftedTokens)
    ? draftedTokens.filter(token => token.type === "equal" || token.type === "add")
    : [];
  const validSource = sourceTokens.map(token => token.text).join("") === draftedText
    ? sourceTokens
    : (draftedText ? [{ type: "equal", text: draftedText }] : []);
  const result = [];
  const append = (type, text) => {
    if (!text) return;
    const previous = result[result.length - 1];
    if (previous?.type === type) previous.text += text;
    else result.push({ type, text });
  };
  let sourceIndex = 0;
  let sourceOffset = 0;

  const advanceSourceRange = (length, render = true) => {
    let remaining = length;
    while (remaining > 0 && sourceIndex < validSource.length) {
      const source = validSource[sourceIndex];
      const available = source.text.length - sourceOffset;
      const count = Math.min(remaining, available);
      if (render) {
        append(source.type, source.text.slice(sourceOffset, sourceOffset + count));
      }
      sourceOffset += count;
      remaining -= count;
      if (sourceOffset === source.text.length) {
        sourceIndex += 1;
        sourceOffset = 0;
      }
    }
  };

  for (const token of editTokens) {
    if (token.type === "equal") {
      advanceSourceRange(token.text.length);
    } else if (token.type === "remove") {
      append("remove", token.text);
      advanceSourceRange(token.text.length, false);
    } else if (token.type === "add") {
      append("add", token.text);
    }
  }

  if (result.filter(token => token.type !== "remove").map(token => token.text).join("") !== revisedText) {
    return revisedText ? [{ type: "equal", text: revisedText }] : [];
  }
  return result;
}

function renderChangeSegments(segments, keyPrefix) {
  return segments.map((segment, index) => {
    if (segment.type === "equal") return segment.text;
    const style = segment.type === "add"
      ? { background: "#dcfce7", color: "#166534", borderRadius: 3 }
      : { background: "#fee2e2", color: "#991b1b", textDecoration: "line-through", borderRadius: 3 };
    return (
      <span
        key={`${keyPrefix}-${segment.type}-${index}`}
        style={style}
        data-change={segment.type}
        contentEditable={segment.type === "remove" ? false : undefined}
        suppressContentEditableWarning
      >
        {segment.text}
      </span>
    );
  });
}

function renderInlineMarkdown(segments, keyPrefix) {
  const text = segments.map(segment => segment.text).join("");
  const pattern = /\*\*[^*\n]+?\*\*|__[^_\n]+?__|`[^`\n]+?`|\*[^*\n]+?\*|_[^_\n]+?_/g;
  const nodes = [];
  let cursor = 0;
  let match;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > cursor) {
      nodes.push(...renderChangeSegments(sliceDiffSegments(segments, cursor, match.index), `${keyPrefix}-text-${cursor}`));
    }
    const markerLength = match[0].startsWith("**") || match[0].startsWith("__") ? 2 : 1;
    const content = sliceDiffSegments(
      segments,
      match.index + markerLength,
      match.index + match[0].length - markerLength,
    );
    const contentNodes = renderChangeSegments(content, `${keyPrefix}-mark-${match.index}`);
    if (markerLength === 2) {
      nodes.push(<strong key={`${keyPrefix}-strong-${match.index}`}>{contentNodes}</strong>);
    } else if (match[0].startsWith("`")) {
      nodes.push(<code key={`${keyPrefix}-code-${match.index}`} style={{
        padding: "1px 4px", background: "#f1f1f5", borderRadius: 3, fontFamily: "Consolas, monospace",
      }}>{contentNodes}</code>);
    } else {
      nodes.push(<em key={`${keyPrefix}-em-${match.index}`}>{contentNodes}</em>);
    }
    cursor = match.index + match[0].length;
  }
  if (cursor < text.length) {
    nodes.push(...renderChangeSegments(sliceDiffSegments(segments, cursor, text.length), `${keyPrefix}-text-${cursor}`));
  }
  return nodes;
}

function getMarkdownCells(line) {
  const cells = [];
  let start = line.text.startsWith("|") ? 1 : 0;
  for (let index = start; index <= line.text.length; index += 1) {
    if (index !== line.text.length && line.text[index] !== "|") continue;
    if (
      index === line.text.length
      && !line.text.slice(start).trim()
      && line.text.slice(0, start).trimEnd().endsWith("|")
    ) break;
    let cellStart = start;
    let cellEnd = index;
    while (cellStart < cellEnd && /\s/.test(line.text[cellStart])) cellStart += 1;
    while (cellEnd > cellStart && /\s/.test(line.text[cellEnd - 1])) cellEnd -= 1;
    cells.push(sliceDiffSegments(line.segments, cellStart, cellEnd));
    start = index + 1;
  }
  return cells;
}

function FormattedProposalContent({
  tokens, variant, fallback, sectionTitle, includeRemovals = false,
}) {
  const segments = getVisibleDiffSegments(tokens, variant, fallback, includeRemovals);
  const text = segments.map(segment => segment.text).join("");
  const lines = [];
  let offset = 0;
  for (const lineText of text.split("\n")) {
    const line = lineText.endsWith("\r") ? lineText.slice(0, -1) : lineText;
    lines.push({
      text: line,
      segments: sliceDiffSegments(segments, offset, offset + line.length),
    });
    offset += lineText.length + 1;
  }

  const isTableLine = line => line.text.includes("|") && line.text.trim() !== "";
  const isTableDivider = line => /^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line.text);
  const isHeading = line => /^(#{1,6})\s+(.+?)\s*$/.exec(line.text);
  const isListItem = line => /^(\s*)([-*+•]|\d+[.)])(\s+)(.*)$/.exec(line.text);
  const blocks = [];
  const normalizeHeading = value => value.replace(/^\d{1,2}[.)]?\s+/, "").trim().toLowerCase();

  for (let index = 0; index < lines.length;) {
    const line = lines[index];
    if (!line.text.trim()) {
      index += 1;
      continue;
    }

    if (isTableLine(line)) {
      const tableLines = [];
      while (index < lines.length && isTableLine(lines[index])) {
        tableLines.push(lines[index]);
        index += 1;
      }
      const hasHeader = tableLines.length > 1 && isTableDivider(tableLines[1]);
      const rows = tableLines.filter((row, rowIndex) => !(hasHeader && rowIndex === 1));
      const heading = hasHeader ? rows.shift() : null;
      blocks.push(
        <div key={`table-${index}`} style={{ overflowX: "auto", margin: "14px 0 18px" }}>
          <table style={{
            width: "100%", borderCollapse: "collapse", font: "12px/1.55 Arial, sans-serif",
            color: "#303044",
          }}>
            {heading && (
              <thead>
                <tr>
                  {getMarkdownCells(heading).map((cell, cellIndex) => (
                    <th key={cellIndex} style={{
                      padding: "9px 10px", textAlign: "left", verticalAlign: "top",
                      background: "#f0eff8", border: "1px solid #d8d7e3", fontWeight: 700,
                    }}>
                      {renderInlineMarkdown(cell, `table-head-${index}-${cellIndex}`)}
                    </th>
                  ))}
                </tr>
              </thead>
            )}
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {getMarkdownCells(row).map((cell, cellIndex) => (
                    <td key={cellIndex} style={{
                      padding: "8px 10px", textAlign: "left", verticalAlign: "top",
                      border: "1px solid #dedde6",
                    }}>
                      {renderInlineMarkdown(cell, `table-cell-${index}-${rowIndex}-${cellIndex}`)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }

    const headingMatch = isHeading(line);
    if (headingMatch) {
      if (sectionTitle && normalizeHeading(headingMatch[2]) === normalizeHeading(sectionTitle)) {
        index += 1;
        continue;
      }
      const contentStart = headingMatch[0].indexOf(headingMatch[2]);
      const level = Math.min(headingMatch[1].length, 4);
      const HeadingTag = `h${level}`;
      blocks.push(
        <HeadingTag key={`heading-${index}`} style={{
          color: "#202033", fontFamily: "Georgia, serif", lineHeight: 1.35,
          fontSize: level === 1 ? 20 : level === 2 ? 17 : 15,
          margin: "18px 0 9px",
        }}>
          {renderInlineMarkdown(sliceDiffSegments(line.segments, contentStart, line.text.length), `heading-${index}`)}
        </HeadingTag>,
      );
      index += 1;
      continue;
    }

    const listMatch = isListItem(line);
    if (listMatch) {
      const ordered = /^\d/.test(listMatch[2]);
      const ListTag = ordered ? "ol" : "ul";
      const items = [];
      while (index < lines.length) {
        const itemMatch = isListItem(lines[index]);
        if (!itemMatch || /^\d/.test(itemMatch[2]) !== ordered) break;
        const contentStart = itemMatch[1].length + itemMatch[2].length + itemMatch[3].length;
        items.push(
          <li key={`list-item-${index}`} style={{ paddingLeft: 4, margin: "3px 0" }}>
            {renderInlineMarkdown(
              sliceDiffSegments(lines[index].segments, contentStart, lines[index].text.length),
              `list-${index}`,
            )}
          </li>,
        );
        index += 1;
      }
      blocks.push(
        <ListTag key={`list-${index}`} style={{
          margin: "8px 0 14px", paddingLeft: 26, color: "#333",
          font: "13px/1.75 Georgia, serif",
        }}>
          {items}
        </ListTag>,
      );
      continue;
    }

    const paragraphLines = [];
    while (
      index < lines.length
      && lines[index].text.trim()
      && !isTableLine(lines[index])
      && !isHeading(lines[index])
      && !isListItem(lines[index])
    ) {
      paragraphLines.push(lines[index]);
      index += 1;
    }
    blocks.push(
      <p key={`paragraph-${index}`} style={{
        margin: "0 0 12px", color: "#333", font: "13px/1.8 Georgia, serif",
        overflowWrap: "anywhere",
      }}>
        {paragraphLines.map((paragraphLine, lineIndex) => (
          <span key={lineIndex}>
            {lineIndex > 0 && <br />}
            {renderInlineMarkdown(paragraphLine.segments, `paragraph-${index}-${lineIndex}`)}
          </span>
        ))}
      </p>,
    );
  }

  return <>{blocks}</>;
}

function CompareEditableSection({
  tokens, value, sectionTitle, onChange,
}) {
  const textareaRef = useRef(null);
  const visibleTokens = getVisibleDiffSegments(tokens, "revised", value);

  useEffect(() => {
    if (!textareaRef.current) return;
    const textarea = textareaRef.current;
    textarea.style.height = "auto";
    textarea.style.height = `${textarea.scrollHeight}px`;
  }, [value]);

  return (
    <div
      style={{
        position: "relative", width: "100%", minHeight: "1.8em",
        color: "#333", font: "13px/1.8 Georgia, serif", whiteSpace: "pre-wrap",
        overflowWrap: "anywhere",
      }}
    >
      <div aria-hidden="true" style={{ minHeight: "1.8em" }}>
        {visibleTokens.map((token, index) => (
          <span
            key={`editor-${token.type}-${index}`}
            style={token.type === "add"
              ? { background: "#dcfce7", color: "#166534", borderRadius: 3 }
              : undefined}
          >
            {token.text}
          </span>
        ))}
      </div>
      <textarea
        ref={textareaRef}
        value={value}
        onChange={event => onChange(event.target.value)}
        spellCheck
        aria-label={`Edit revised ${sectionTitle}`}
        style={{
          position: "absolute", inset: 0, display: "block",
          boxSizing: "border-box", width: "100%", height: "100%",
          minHeight: "1.8em", margin: 0, padding: 0, border: "none",
          borderRadius: 0, outline: "none", resize: "none", overflow: "hidden",
          background: "transparent", color: "transparent", caretColor: "#222",
          WebkitTextFillColor: "transparent",
          font: "13px/1.8 Georgia, serif", whiteSpace: "pre-wrap",
          overflowWrap: "anywhere",
        }}
      />
    </div>
  );
}

export default function Draft() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const grantId = searchParams.get("grant");
  const loadId = searchParams.get("load");

  const { profile, currentUser } = useAuth();
  const { grants, proposal } = useGrants();
  const session = useProposalSession();
  const restoreSession = session.restore;
  const { saveDraft, updateDraft, drafts, proposals } = useWorkStore();
  const [originalSections, setOriginalSections] = useState({});
  
  // Bridge variables for legacy render logic
  const loading      = session.loading;
  const sections     = normalizeSectionMap(session.data.sections);
  const sectionDiffs = session.data.diffs?.uploaded_content && !session.data.diffs?.proposal
    ? { ...session.data.diffs, proposal: session.data.diffs.uploaded_content }
    : (session.data.diffs || {});
  const [compareDiffSnapshot, setCompareDiffSnapshot] = useState({
    sessionId: null,
    diffs: {},
  });
  const cachedCompareDiffs = compareDiffSnapshot.sessionId === session.sessionId
    ? compareDiffSnapshot.diffs
    : {};
  const liveCompareDiffs = Object.fromEntries(
    Object.entries(sectionDiffs).filter(([key, tokens]) => (
      Array.isArray(tokens) && (tokens.length > 0 || !cachedCompareDiffs[key])
    ))
  );
  const compareSectionDiffs = { ...cachedCompareDiffs, ...liveCompareDiffs };
  const sectionOrder = Array.from(new Set([
    ...Object.keys(originalSections),
    ...Object.keys(sections),
  ]));
  const sectionOrderKey = sectionOrder.join("|");
  const sectionCount = sectionOrder.length;
  const done = session.gate === "complete" || session.gate === "draft_review" || session.gate === "final_save";
  const autoSaveDone = session.gate === "complete"; // only auto-save when truly done
  const error        = session.error;
  const activeSection = session.gate === "none" ? null : (session.data.active_section || null);
  const [savedDraftId, setSavedDraftId] = useState(null);
  const [saveStatus,   setSaveStatus]   = useState(null); // "saved" | "error" | null

  const [selectedGrantId,   setSelectedGrantId]   = useState(grantId || "");
  const [selectedProposalId, setSelectedProposalId] = useState("");
  const [activeTab,       setActiveTab]       = useState(null);
  const [editedContent,   setEditedContent]   = useState({});
  const [previewSections, setPreviewSections] = useState({});
  const [wordCounts,      setWordCounts]      = useState({});
  const [pdfLoading,      setPdfLoading]      = useState(false);
  const [userInstructions, setUserInstructions] = useState("");
  const [streamedSections, setStreamedSections] = useState({});
  const [streamSectionOrder, setStreamSectionOrder] = useState([]);
  const [compareMode, setCompareMode] = useState(false);
  const [matchComparison, setMatchComparison] = useState({
    before: null, after: null, status: "idle",
  });

  const textareaRefs = useRef({});
  const sectionRefs = useRef({});
  const scrollContainerRef = useRef(null);
  const restoredSessionRef = useRef(false);
  const selectedGrant    = grants.find(g => String(g.grant_id) === String(selectedGrantId));
  // Active saved proposal (uploaded or built) — provides proposal_context for drafting
  const activeProposal   = proposals.find(p => p.id === selectedProposalId);
  // Resolved proposal: prefer saved proposal_context, fall back to sessionStorage proposal
  const resolvedProposal = activeProposal?.proposal_context
    || proposal
    || null;

  useEffect(() => {
    setMatchComparison({
      before: selectedGrant?.similarity_score ?? null,
      after: null,
      status: "idle",
    });
  }, [selectedGrantId, selectedGrant?.similarity_score]);

  // Auto-select most recent proposal if none selected
  useEffect(() => {
    if (!selectedProposalId && proposals.length > 0) {
      const storedId = sessionStorage.getItem("upload_draft_id");
      if (storedId && proposals.find(p => p.id === storedId)) {
        setSelectedProposalId(storedId);
      } else {
        setSelectedProposalId(proposals[0].id);
      }
    }
  }, [proposals, selectedProposalId]);

  useEffect(() => { if (grantId) setSelectedGrantId(grantId); }, [grantId]);

  useEffect(() => {
    const checkpointSections = session.data.original_sections;
    const proposalSections = resolvedProposal?.sections;
    const sourceSections = normalizeSectionMap(
      checkpointSections && Object.keys(checkpointSections).length
        ? checkpointSections
        : proposalSections
    );
    if (!Object.keys(sourceSections).length && resolvedProposal?.raw_text) {
      sourceSections.proposal = {
        title: "Proposal",
        content: resolvedProposal.raw_text,
      };
    }
    if (!Object.keys(sourceSections).length) return;

    setOriginalSections(Object.fromEntries(
      Object.entries(sourceSections).map(([key, value]) => [
        key,
        typeof value === "string" ? value : value?.content || "",
      ])
    ));
  }, [
    session.data.original_sections,
    session.sessionId,
    resolvedProposal?.raw_text,
    resolvedProposal?.sections,
  ]);

  useEffect(() => {
    if (restoredSessionRef.current || !currentUser?.uid || loadId) return;
    restoredSessionRef.current = true;

    try {
      const cachedSession = JSON.parse(
        sessionStorage.getItem(`impactlink:draft-session:${currentUser.uid}`) || "null"
      );
      if (!cachedSession?.session_id) return;
      if (grantId && String(cachedSession.grant_id) !== String(grantId)) return;

      if (!grantId && cachedSession.grant_id) {
        setSelectedGrantId(String(cachedSession.grant_id));
      }
      if (cachedSession.proposal_id) {
        setSelectedProposalId(String(cachedSession.proposal_id));
      }
      if (cachedSession.saved_draft_id) {
        setSavedDraftId(cachedSession.saved_draft_id);
      }
      restoreSession(cachedSession.session_id);
    } catch (storageError) {
      console.error("Could not restore the cached Draft Assistant session.", storageError);
    }
  }, [currentUser?.uid, grantId, loadId, restoreSession]);



  // Load saved draft if ?load=<id> is in URL
  useEffect(() => {
    if (!loadId || !drafts.length) return;
    const saved = drafts.find(d => d.id === loadId);
    if (!saved) return;
    const restoredSections = { ...(saved.sections || {}) };
    if (restoredSections.uploaded_content) {
      restoredSections.proposal = {
        ...restoredSections.uploaded_content,
        title: "Proposal",
      };
      delete restoredSections.uploaded_content;
    }
    const proposalSections = saved.proposal_context?.sections || {};
    const sourceSections = Object.keys(proposalSections).length
      ? proposalSections
      : saved.proposal_context?.raw_text
        ? { proposal: { title: "Proposal", content: saved.proposal_context.raw_text } }
        : restoredSections;
    setOriginalSections(Object.fromEntries(
      Object.entries(sourceSections).map(([key, value]) => [
        key,
        typeof value === "string" ? value : value?.content || "",
      ])
    ));
    const restoredOrder    = saved.section_order || Object.keys(restoredSections);
    // Restore grant + save ID
    if (saved.grant_id) setSelectedGrantId(saved.grant_id);
    setSavedDraftId(saved.id);
    // Restoration logic: simulate a "completed" session with these sections
    session.setData({ sections: restoredSections });
    session.setGate("complete");
    // Also seed editedContent so edits work from the start
    const ec = {};
    const wc = {};
    restoredOrder.forEach(key => {
      if (restoredSections[key]) {
        ec[key] = restoredSections[key].content || "";
        wc[key] = (restoredSections[key].content || "").trim().split(/\s+/).filter(Boolean).length;
      }
    });
    setEditedContent(ec);
    setWordCounts(wc);
    setCompareDiffSnapshot({ sessionId: null, diffs: {} });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadId, drafts]);

  useEffect(() => {
    if (!session.sessionId) return;
    const incomingDiffs = session.data.diffs?.uploaded_content && !session.data.diffs?.proposal
      ? { ...session.data.diffs, proposal: session.data.diffs.uploaded_content }
      : (session.data.diffs || {});
    setCompareDiffSnapshot(previous => {
      const previousDiffs = previous.sessionId === session.sessionId ? previous.diffs : {};
      const nextDiffs = { ...previousDiffs };
      Object.entries(incomingDiffs).forEach(([key, tokens]) => {
        if (Array.isArray(tokens) && (tokens.length > 0 || !nextDiffs[key])) {
          nextDiffs[key] = tokens;
        }
      });
      const unchanged = previous.sessionId === session.sessionId
        && Object.keys(nextDiffs).length === Object.keys(previousDiffs).length
        && Object.entries(nextDiffs).every(([key, tokens]) => previousDiffs[key] === tokens);
      return unchanged ? previous : { sessionId: session.sessionId, diffs: nextDiffs };
    });
  }, [session.sessionId, session.data.diffs]);

  useEffect(() => {
    if (sectionOrder.length > 0 && !activeTab) setActiveTab(sectionOrder[0]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sectionOrder]);

  useEffect(() => {
    if (activeSection) setActiveTab(activeSection);
  }, [activeSection]);

  useEffect(() => {
    const root = scrollContainerRef.current;
    if (!root || !sectionCount) return undefined;

    const observer = new IntersectionObserver(
      entries => {
        const visibleSections = entries
          .filter(entry => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visibleSections[0]) {
          setActiveTab(visibleSections[0].target.dataset.sectionKey);
        }
      },
      { root, rootMargin: "-12% 0px -65% 0px", threshold: 0 }
    );

    sectionOrderKey.split("|").filter(Boolean).forEach(key => {
      const element = sectionRefs.current[key];
      if (element) observer.observe(element);
    });

    return () => observer.disconnect();
  }, [sectionOrderKey, sectionCount, session.gate]);

  // Auto-save draft when AI fully completes (not at intermediate draft_review gate)
  useEffect(() => {
    if (autoSaveDone && sectionOrder.length > 0) {
      if (profile) handleSave();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoSaveDone]);

  // Sync session data to local states for editor
  useEffect(() => {
    if (session.gate === "draft_review" || session.gate === "final_save" || session.gate === "complete") {
      if (session.data.sections) {
        const ec = {};
        const wc = {};
        Object.entries(session.data.sections).forEach(([k, v]) => {
          ec[k] = v.content || "";
          wc[k] = (v.content || "").trim().split(/\s+/).filter(Boolean).length;
        });
        setEditedContent(ec);
        setWordCounts(wc);
      }
    }
  }, [session.gate, session.data.sections]);

  const handleEdit = (key, value) => {
    setEditedContent(prev => ({ ...prev, [key]: value }));
    setWordCounts(prev => ({ ...prev, [key]: value.trim().split(/\s+/).filter(Boolean).length }));
  };

  const handleFormat = (format) => {
    const ta = textareaRefs.current[activeTab];
    if (!ta || !activeTab) return;
    const result = applyFormat(ta, format);
    if (!result) return;
    handleEdit(activeTab, result.newText);
    setTimeout(() => {
      ta.selectionStart = result.newCursorStart;
      ta.selectionEnd   = result.newCursorEnd;
      ta.focus();
    }, 0);
  };

  const handleDraft = async () => {
    if (!resolvedProposal || !selectedGrant) return;
    setCompareDiffSnapshot({ sessionId: null, diffs: {} });
    setEditedContent({});
    setActiveTab(null);
    setSavedDraftId(null);
    setSaveStatus(null);
    setUserInstructions("");
    setStreamedSections({});
    setStreamSectionOrder([]);
    setCompareMode(false);
    setMatchComparison({
      before: selectedGrant.similarity_score ?? null,
      after: null,
      status: "idle",
    });
    session.reset();
    if (currentUser?.uid) {
      try {
        sessionStorage.removeItem(`impactlink:draft-session:${currentUser.uid}`);
      } catch (storageError) {
        console.error("Could not clear the cached Draft Assistant session.", storageError);
      }
    }
    
    // Filter current sections to only include non-empty ones
    const currentSections = {};
    let sourceSections = activeProposal?.sections || resolvedProposal?.sections || {};
    if (sourceSections.uploaded_content) {
      const savedUploadedContent = sourceSections.uploaded_content;
      const uploadedText = resolvedProposal?.raw_text
        || (typeof savedUploadedContent === "string"
          ? savedUploadedContent
          : savedUploadedContent.content || "")
        || "";
      sourceSections = {
        ...Object.fromEntries(
          Object.entries(sourceSections).filter(([key]) => key !== "uploaded_content")
        ),
        ...(uploadedText ? { proposal: { title: "Proposal", content: uploadedText } } : {}),
      };
    } else if (!Object.keys(sourceSections).length && resolvedProposal?.raw_text) {
      sourceSections = {
        proposal: { title: "Proposal", content: resolvedProposal.raw_text },
      };
    }
    Object.entries(sourceSections).forEach(([k, v]) => {
      const content = typeof v === "string" ? v : v?.content || "";
      if (content.trim()) {
        currentSections[k] = typeof v === "string" ? content : { ...v, content };
      }
    });
    setOriginalSections(Object.fromEntries(
      Object.entries(currentSections).map(([key, value]) => [
        key,
        typeof value === "string" ? value : value.content || "",
      ])
    ));

    try {
        const sessionId = await session.start("improve", selectedGrant, profile || {}, currentSections);
        if (currentUser?.uid && sessionId) {
          try {
            sessionStorage.setItem(
              `impactlink:draft-session:${currentUser.uid}`,
              JSON.stringify({
                session_id: sessionId,
                grant_id: String(selectedGrant.grant_id),
                proposal_id: selectedProposalId || null,
              })
            );
          } catch (storageError) {
            console.error("Could not cache the Draft Assistant session ID.", storageError);
          }
        }
    } catch (e) {
        console.error("Improve start error:", e);
    }
  };

  const handleAdvance = async (payload = {}) => {
      try {
          const shouldStreamDraft = Array.isArray(payload.sections_to_rewrite)
            && Object.prototype.hasOwnProperty.call(payload, "user_additions");
          let result;
          if (shouldStreamDraft) {
            const sectionKeys = payload.sections_to_rewrite;
            setStreamSectionOrder(sectionKeys);
            setStreamedSections(Object.fromEntries(sectionKeys.map(key => [key, ""])));
            result = await session.advanceStream(payload, (sectionKey, content) => {
              setStreamedSections(previous => ({
                ...previous,
                [sectionKey]: (previous[sectionKey] || "") + content,
              }));
            });
            setCompareMode(true);
          } else {
            result = await session.advance(payload);
          }

          if (shouldStreamDraft && result?.gate === "draft_review" && selectedGrant) {
            setMatchComparison(previous => ({ ...previous, status: "updating" }));
            try {
              const proposalForMatch = {
                ...resolvedProposal,
                sections: Object.fromEntries(
                  Object.entries(result.sections || {}).map(([key, section]) => [
                    key,
                    section.content || "",
                  ])
                ),
              };
              delete proposalForMatch.raw_text;

              const matchResponse = await api.post("/api/match", {
                proposal: proposalForMatch,
                top_k: 21,
                grant_id: String(selectedGrant.grant_id),
              });
              const updatedMatch = (matchResponse.data.matches || []).find(
                grant => String(grant.grant_id) === String(selectedGrant.grant_id)
              );
              if (!updatedMatch) {
                setMatchComparison(previous => ({ ...previous, status: "unavailable" }));
              } else {
                setMatchComparison(previous => ({
                  ...previous,
                  after: updatedMatch.similarity_score,
                  status: "updated",
                }));
                try {
                  const storedMatches = JSON.parse(sessionStorage.getItem("matches") || "[]");
                  const hasCachedMatch = storedMatches.some(
                    grant => String(grant.grant_id) === String(updatedMatch.grant_id)
                  );
                  const refreshedMatches = hasCachedMatch
                    ? storedMatches.map(grant => String(grant.grant_id) === String(updatedMatch.grant_id)
                      ? { ...grant, ...updatedMatch }
                      : grant)
                    : [...storedMatches, updatedMatch];
                  sessionStorage.setItem("matches", JSON.stringify(refreshedMatches));
                } catch (storageError) {
                  console.error("Could not update cached grant match.", storageError);
                }
              }
            } catch (matchError) {
              console.error("Could not recalculate grant match for the new draft.", matchError);
              setMatchComparison(previous => ({ ...previous, status: "unavailable" }));
            }
          }
      } catch (e) {
          console.error("Advance error:", e);
      }
  };

  // Save current draft to store
  const handleSave = async (currentSections) => {
    if (!profile || !selectedGrant) return;
    try {
      const secToSave = {};
      sectionOrder.forEach(key => {
        secToSave[key] = {
          title:   sections[key]?.title   || key,
          content: currentSections?.[key] ?? editedContent[key] ?? sections[key]?.content ?? "",
        };
      });
      let persistedDraftId = savedDraftId;
      if (savedDraftId) {
        await updateDraft(savedDraftId, secToSave);
      } else {
        const matchIds = (activeProposal?.matches_id || []);
        const saved = await saveDraft({
          title:            selectedGrant.title,
          grant_title:      selectedGrant.title,
          grant_id:         String(selectedGrant.grant_id),
          agency:           selectedGrant.agency || "",
          proposal_context: resolvedProposal || {},
          matches_id:       matchIds,
          sections:         secToSave,
          section_order:    sectionOrder,
        });
        if (saved) {
          persistedDraftId = saved.id;
          setSavedDraftId(saved.id);
        }
      }
      if (currentUser?.uid) {
        try {
          const cacheKey = `impactlink:draft-session:${currentUser.uid}`;
          const cachedSession = JSON.parse(sessionStorage.getItem(cacheKey) || "null");
          if (cachedSession?.session_id && persistedDraftId) {
            sessionStorage.setItem(cacheKey, JSON.stringify({
              ...cachedSession,
              saved_draft_id: persistedDraftId,
            }));
          }
        } catch (storageError) {
          console.error("Could not cache the saved Draft Assistant ID.", storageError);
        }
      }
      setSaveStatus("saved");
      setTimeout(() => setSaveStatus(null), 2500);
    } catch (e) {
      setSaveStatus("error");
    }
  };

  const handleDownloadPDF = async () => {
    if (!sectionOrder.length) return;
    setPdfLoading(true);
    try {
      // Dynamically load jsPDF
      // Load jsPDF via script tag (CRA doesn't support dynamic CDN ES module imports)
      await loadJsPDF();
      const { jsPDF } = window.jspdf;
      const doc = new jsPDF({ unit: "pt", format: "letter" });

      const marginLeft  = 72;
      const marginRight = 72;
      const pageWidth   = doc.internal.pageSize.getWidth();
      const pageHeight  = doc.internal.pageSize.getHeight();
      const contentW    = pageWidth - marginLeft - marginRight;
      let y = 80;

      const addPage = () => { doc.addPage(); y = 72; };

      const checkY = (needed = 20) => { if (y + needed > pageHeight - 60) addPage(); };

      // Cover header
      doc.setFillColor(18, 18, 32);
      doc.rect(0, 0, pageWidth, 56, "F");
      doc.setTextColor(124, 111, 239);
      doc.setFontSize(10);
      doc.setFont("helvetica", "bold");
      doc.text("IMPACTLINK  —  GRANT PROPOSAL", marginLeft, 34);
      doc.setTextColor(136, 136, 136);
      doc.text(new Date().toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" }), pageWidth - marginRight, 34, { align: "right" });

      y = 100;

      // Title block
      doc.setTextColor(20, 20, 35);
      doc.setFontSize(22);
      doc.setFont("helvetica", "bold");
      const titleLines = doc.splitTextToSize(selectedGrant?.title || "Grant Proposal", contentW);
      doc.text(titleLines, marginLeft, y);
      y += titleLines.length * 28 + 8;

      doc.setFontSize(11);
      doc.setFont("helvetica", "normal");
      doc.setTextColor(100, 100, 120);
      doc.text(`${selectedGrant?.agency || ""}  ·  ${proposal?.organization_name || ""}`, marginLeft, y);
      y += 12;

      // Divider
      doc.setDrawColor(200, 200, 220);
      doc.setLineWidth(0.5);
      doc.line(marginLeft, y, pageWidth - marginRight, y);
      y += 28;

      // Sections
      for (const key of sectionOrder) {
        const sec     = sections[key];
        const content = editedContent[key] || sec?.content || "";
        if (!sec) continue;

        checkY(60);

        // Section label pill
        doc.setFillColor(240, 240, 255);
        doc.roundedRect(marginLeft, y - 12, contentW, 22, 4, 4, "F");
        doc.setFontSize(9);
        doc.setFont("helvetica", "bold");
        doc.setTextColor(100, 90, 200);
        doc.text(`${SECTION_ICONS[key]}  ${sec.title.toUpperCase()}`, marginLeft + 10, y + 3);
        y += 28;

        // Body text
        doc.setFontSize(10.5);
        doc.setFont("helvetica", "normal");
        doc.setTextColor(40, 40, 60);

        // Strip markdown bold markers for clean PDF
        const cleanContent = content.replace(/\*\*(.*?)\*\*/g, "$1").replace(/^## (.+)$/gm, "$1");
        const paragraphs = cleanContent.split(/\n{2,}/);

        for (const para of paragraphs) {
          if (!para.trim()) continue;
          const lines = doc.splitTextToSize(para.trim(), contentW);
          checkY(lines.length * 14 + 8);
          doc.text(lines, marginLeft, y);
          y += lines.length * 14 + 10;
        }

        y += 16;

        // Section divider
        checkY(10);
        doc.setDrawColor(230, 230, 245);
        doc.setLineWidth(0.3);
        doc.line(marginLeft, y, pageWidth - marginRight, y);
        y += 20;
      }

      // Footer on every page
      const totalPages = doc.internal.getNumberOfPages();
      for (let i = 1; i <= totalPages; i++) {
        doc.setPage(i);
        doc.setFillColor(18, 18, 32);
        doc.rect(0, pageHeight - 36, pageWidth, 36, "F");
        doc.setFontSize(8);
        doc.setTextColor(80, 80, 100);
        doc.setFont("helvetica", "normal");
        doc.text("Prepared with ImpactLink", marginLeft, pageHeight - 16);
        doc.text(`Page ${i} of ${totalPages}`, pageWidth - marginRight, pageHeight - 16, { align: "right" });
      }

      const orgSlug = (proposal?.organization_name || "proposal").replace(/\s+/g, "_").toLowerCase();
      doc.save(`${orgSlug}_grant_proposal.pdf`);
    } catch (err) {
      console.error("PDF error:", err);
      alert("PDF generation failed. Check console for details.");
    } finally {
      setPdfLoading(false);
    }
  };

  const totalWords  = Object.values(wordCounts).reduce((a, b) => a + b, 0);
  const hasSections = sectionCount > 0;
  const activeContentValue = activeTab ? (editedContent[activeTab] ?? sections[activeTab]?.content ?? "") : "";
  const scrollToSection = (key) => {
    setActiveTab(key);
    sectionRefs.current[key]?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div style={{ minHeight: "100vh", background: "#1e1e2e", display: "flex", flexDirection: "column" }}>
      <Nav />

      {/* ── App Bar ─────────────────────────────────────── */}
      <div style={{
        background: "#13131f", borderBottom: "1px solid #2a2a3e",
        padding: "0 20px", height: 48,
        display: "flex", alignItems: "center", justifyContent: "space-between",
        position: "sticky", top: 64, zIndex: 90, gap: 12,
      }}>
        {/* Left: title */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
          <button onClick={() => navigate(-1)} style={{ background: "none", border: "none", color: "#555", fontSize: 13, cursor: "pointer", padding: 0, flexShrink: 0 }}>←</button>
          <span style={{ color: "#fff", fontWeight: 700, fontSize: 13, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 320 }}>
            {selectedGrant ? selectedGrant.title : "New Proposal"}
          </span>
          {selectedGrant && (
            <span style={{ background: "#1e1e30",
              color: "var(--accent)",
              border: "1px solid #2e2e4e", borderRadius: 5, padding: "2px 8px", fontSize: 10, fontWeight: 700, flexShrink: 0,
              transition: "color 0.3s",
            }}>
              {matchComparison.status === "updated"
                ? `${matchComparison.before}% → ${matchComparison.after}% match`
                : matchComparison.status === "updating"
                  ? `${matchComparison.before}% → updating…`
                  : `${selectedGrant.similarity_score}% match`}
            </span>
          )}
        </div>

        {/* Right: actions */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
          {(hasSections || resolvedProposal?.raw_text) && (
            <div style={{ display: "flex", gap: 4, marginRight: 6 }}>
              {[
                { label: "Edit draft", value: false },
                { label: "Compare versions", value: true },
              ].map(option => (
                <button
                  key={option.label}
                  type="button"
                  aria-pressed={compareMode === option.value}
                  onClick={() => setCompareMode(option.value)}
                  style={{
                    background: compareMode === option.value ? "#2b2944" : "transparent",
                    border: "1px solid #2a2a3e", borderRadius: 6,
                    color: compareMode === option.value ? "#d9d4ff" : "#777",
                    padding: "6px 9px", fontSize: 11, cursor: "pointer",
                  }}
                >
                  {option.label}
                </button>
              ))}
            </div>
          )}
          {hasSections && (
            <span style={{ color: "#444", fontSize: 11, marginRight: 4 }}>
              {totalWords.toLocaleString()} words
            </span>
          )}
          {savedDraftId && !done && (
            <span style={{ color: "#444", fontSize: 11, fontWeight: 600,
              background: "#1a1a28", border: "1px solid #2a2a3e",
              borderRadius: 5, padding: "2px 8px" }}>
              ✎ Editing saved
            </span>
          )}
          {done && (
            <>
              {saveStatus === "saved" && (
                <span style={{ color: "var(--green)", fontSize: 11, fontWeight: 600 }}>✓ Saved</span>
              )}
              {saveStatus === "error" && (
                <span style={{ color: "var(--red)", fontSize: 11 }}>Save failed</span>
              )}
              <button
                onClick={() => handleSave()}
                style={{
                  background: "#1a1a28", border: "1px solid #2a2a3e",
                  color: "#888", padding: "6px 13px", borderRadius: 7,
                  fontSize: 12, fontWeight: 600, cursor: "pointer",
                }}
              >
                💾 Save
              </button>
              <button
                onClick={handleDownloadPDF}
                disabled={pdfLoading}
                style={{
                  background: pdfLoading ? "#1a1a2e" : "#e63946",
                  border: "none", color: "#fff",
                  padding: "6px 14px", borderRadius: 7,
                  fontSize: 12, fontWeight: 700, cursor: pdfLoading ? "wait" : "pointer",
                  display: "flex", alignItems: "center", gap: 6,
                }}
              >
                {pdfLoading ? "⟳ Generating..." : "↓ Download PDF"}
              </button>
            </>
          )}
          <button
            onClick={handleDraft}
            disabled={!selectedGrant || !resolvedProposal || loading}
            style={{
              background: selectedGrant && resolvedProposal && !loading ? "var(--accent)" : "#1a1a2e",
              border: "none",
              color: selectedGrant && resolvedProposal && !loading ? "#fff" : "#444",
              padding: "6px 14px", borderRadius: 7,
              fontSize: 12, fontWeight: 700,
              cursor: selectedGrant && resolvedProposal && !loading ? "pointer" : "not-allowed",
            }}
          >
            {loading ? "Writing…" : hasSections ? "↺ Redraft" : "✦ Draft"}
          </button>
        </div>
      </div>

      {/* ── Body ────────────────────────────────────────── */}
      <div style={{ display: "flex", flex: 1 }}>

        {/* Left panel — sections list */}
        <div style={{
          width: 210, flexShrink: 0, background: "#0f0f1a",
          borderRight: "1px solid #1e1e2e",
          display: "flex", flexDirection: "column",
          position: "sticky", top: 112, height: "calc(100vh - 112px)", overflowY: "auto",
        }}>
          {/* Saved Proposal selector */}
          <div style={{ padding: "14px 14px 10px", borderBottom: "1px solid #1e1e2e" }}>
            <p style={{ color: "#333", fontSize: 9, fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.1em", margin: "0 0 7px" }}>Proposal</p>
            <select
              value={selectedProposalId}
              onChange={e => {
                setSelectedProposalId(e.target.value);
                sessionStorage.setItem("upload_draft_id", e.target.value);
              }}
              style={{
                width: "100%", background: "#1a1a28", border: "1px solid #2a2a3e",
                color: selectedProposalId ? "#ddd" : "#444",
                padding: "7px 8px", borderRadius: 6,
                fontSize: 11, cursor: "pointer", outline: "none",
              }}
            >
              <option value="">From sessionStorage…</option>
              {proposals.map(p => (
                <option key={p.id} value={p.id}>
                  {p._type === "build" ? "✦ " : "✍ "}
                  {p.title.length > 30 ? p.title.slice(0, 30) + "…" : p.title}
                </option>
              ))}
            </select>
            {activeProposal && (
              <p style={{ color: "#444", fontSize: 9, margin: "4px 0 0", lineHeight: 1.5 }}>
                {activeProposal.proposal_context?.organization_name || ""}
                {activeProposal.matches_id?.length
                  ? ` · ${activeProposal.matches_id.length} matches`
                  : ""}
              </p>
            )}
          </div>

          {/* Grant picker */}
          <div style={{ padding: "14px 14px 10px", borderBottom: "1px solid #1e1e2e" }}>
            <p style={{ color: "#333", fontSize: 9, fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.1em", margin: "0 0 7px" }}>Grant</p>
            <select
              value={selectedGrantId}
              onChange={e => { setSelectedGrantId(e.target.value); session.reset(); setEditedContent({}); setActiveTab(null); }}
              style={{
                width: "100%", background: "#1a1a28", border: "1px solid #2a2a3e",
                color: selectedGrantId ? "#ddd" : "#444",
                padding: "7px 8px", borderRadius: 6,
                fontSize: 11, cursor: "pointer", outline: "none",
              }}
            >
              <option value="">Choose grant…</option>
              {grants.map(g => (
                <option key={g.grant_id} value={g.grant_id}>
                  {g.title.length > 36 ? g.title.slice(0, 36) + "…" : g.title}
                </option>
              ))}
            </select>
          </div>

          {/* Section list */}
          <div style={{ padding: "10px 8px", flex: 1 }}>
            {!hasSections && !loading && (
              <p style={{ color: "#2a2a3e", fontSize: 11, padding: "16px 8px", lineHeight: 1.6 }}>
                {selectedGrant && proposal ? 'Click "Draft" to begin' : "Select a grant above"}
              </p>
            )}
            {loading && !hasSections && (
              <p style={{ color: "var(--accent)", fontSize: 11, padding: "16px 8px" }}>⟳ Writing…</p>
            )}
            {sectionOrder.map(key => (
              <div
                key={key}
                onClick={() => scrollToSection(key)}
                style={{
                  display: "flex", alignItems: "center", gap: 9,
                  padding: "8px 10px", borderRadius: 7, cursor: "pointer",
                  background: activeTab === key ? "#1e1e30" : "transparent",
                  borderLeft: activeTab === key ? "2px solid var(--accent)" : "2px solid transparent",
                  marginBottom: 1, transition: "all 0.12s",
                }}
              >
                <span style={{ fontSize: 9, fontWeight: 800, color: activeTab === key ? "var(--accent)" : "#333", fontFamily: "monospace", flexShrink: 0 }}>
                  {activeSection === key ? "⟳" : SECTION_ICONS[key]}
                </span>
                <div style={{ minWidth: 0 }}>
                  <p style={{ fontSize: 11, fontWeight: activeTab === key ? 700 : 400, color: activeTab === key ? "#e0e0f0" : "#555", margin: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {getSectionTitle(key, sections[key])}
                  </p>
                  {wordCounts[key] && <p style={{ fontSize: 9, color: "#333", margin: 0 }}>{wordCounts[key]}w</p>}
                </div>
              </div>
            ))}
            {loading && hasSections && (
              <div style={{ display: "flex", alignItems: "center", gap: 9, padding: "8px 10px" }}>
                <span style={{ fontSize: 9, color: "var(--accent)" }}>⟳</span>
                <p style={{ fontSize: 11, color: "var(--accent)", margin: 0 }}>Writing…</p>
              </div>
            )}
          </div>

          {done && (
            <div style={{ padding: "10px 14px", borderTop: "1px solid #1e1e2e" }}>
              <div style={{ background: "#0d2e1a", borderRadius: 7, padding: "8px 10px" }}>
                <p style={{ color: "var(--green)", fontSize: 10, fontWeight: 700, margin: "0 0 1px" }}>✓ Complete</p>
                <p style={{ color: "#2d5a3d", fontSize: 10, margin: 0 }}>{totalWords.toLocaleString()} words</p>
              </div>
            </div>
          )}
        </div>

        {/* Center — Word-like editor */}
        <div ref={scrollContainerRef} style={{ flex: 1, background: "#2a2a3a", overflowY: "auto", display: "flex", flexDirection: "column", alignItems: "center", padding: "32px 0 80px" }}>

          {/* Formatting toolbar */}
          {activeTab && sections[activeTab] && !previewSections[activeTab] && (
            <div style={{
              width: 760, marginBottom: 8,
              background: "#13131f", border: "1px solid #2a2a3e",
              borderRadius: 8, padding: "6px 12px",
              display: "flex", alignItems: "center", gap: 2,
            }}>
              {[
                { label: "B", title: "Bold",   fmt: "bold",   style: { fontWeight: 900 } },
                { label: "H2", title: "Heading", fmt: "h2",   style: { fontSize: 10 } },
                { label: "• List", title: "Bullet list", fmt: "bullet", style: {} },
                { label: "Table", title: "Insert table", fmt: "table", style: {} },
              ].map(btn => (
                <button
                  key={btn.fmt}
                  title={btn.title}
                  onMouseDown={e => { e.preventDefault(); handleFormat(btn.fmt); }}
                  style={{
                    background: "none", border: "none",
                    color: "#888", padding: "4px 10px", borderRadius: 5,
                    fontSize: 12, cursor: "pointer", fontFamily: "monospace",
                    ...btn.style,
                  }}
                  onMouseEnter={e => e.target.style.background = "#1e1e2e"}
                  onMouseLeave={e => e.target.style.background = "none"}
                >
                  {btn.label}
                </button>
              ))}
              <div style={{ width: 1, height: 16, background: "#2a2a3e", margin: "0 4px" }} />
              <button
                onClick={() => navigator.clipboard.writeText(activeContentValue)}
                style={{ background: "none", border: "none", color: "#555", padding: "4px 10px", borderRadius: 5, fontSize: 11, cursor: "pointer" }}
                onMouseEnter={e => e.target.style.background = "#1e1e2e"}
                onMouseLeave={e => e.target.style.background = "none"}
              >
                Copy section
              </button>
              <span style={{ marginLeft: "auto", color: "#333", fontSize: 10 }}>
                {wordCounts[activeTab] || 0} words
              </span>
            </div>
          )}

          {/* Gated Review Overlay */}
          {session.gate !== "none" && session.gate !== "draft_review" && session.gate !== "final_save" && session.gate !== "complete" && !session.loading && (
            <div style={{
              width: 760, background: "#fff", borderRadius: 12, padding: "40px",
              boxShadow: "0 10px 40px rgba(0,0,0,0.5)", color: "#1a1a2e"
            }}>
              {session.gate === "gap_review" && (
                <div>
                  <h3 style={{ margin: "0 0 10px", fontSize: 18, fontWeight: 800 }}>Gap Analysis</h3>
                  <p style={{ color: "#666", fontSize: 13, marginBottom: 20 }}>
                    I've identified the following missing information required for a high-quality proposal:
                  </p>
                  <ul style={{ paddingLeft: 20, marginBottom: 24 }}>
                    {(
                      [
                        ...(session.data.analysis?.missing_content || []),
                        ...(session.data.analysis?.weak_evidence || []),
                        ...(session.data.analysis?.wrong_vocabulary || []),
                        ...(session.data.analysis?.misalignment || [])
                      ]
                    ).map((gap, i) => (
                      <li key={i} style={{ color: "#333", fontSize: 13, marginBottom: 8 }}>
                        <strong>{(gap.section || "General").replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())}:</strong> {gap.description}
                      </li>
                    ))}
                    {!session.data.analysis?.missing_content?.length &&
                     !session.data.analysis?.weak_evidence?.length &&
                     !session.data.analysis?.wrong_vocabulary?.length &&
                     !session.data.analysis?.misalignment?.length && (
                      <li style={{ color: "#888", fontSize: 13, listStyle: "none", marginLeft: -20 }}>
                        No significant gaps were identified. We'll proceed with general polish and vocabulary alignment.
                      </li>
                    )}
                  </ul>
                  <div style={{ marginBottom: 20 }}>
                    <label htmlFor="draft-user-instructions" style={{
                      display: "block", fontSize: 14, fontWeight: 700,
                      color: "#222", marginBottom: 6,
                    }}>
                      Instructions for this rewrite <span style={{ color: "#888", fontWeight: 400 }}>(optional)</span>
                    </label>
                    <p style={{ color: "#666", fontSize: 12, margin: "0 0 8px" }}>
                      Say what to emphasize, avoid, or clarify. We’ll use these as writing preferences while preserving verified facts and grant requirements.
                    </p>
                    <textarea
                      id="draft-user-instructions"
                      value={userInstructions}
                      onChange={e => setUserInstructions(e.target.value)}
                      maxLength={2000}
                      placeholder="For example: Avoid promising specific outcomes we haven't measured. Emphasize our existing youth mentorship activities."
                      disabled={session.loading}
                      style={{
                        width: "100%", minHeight: 100, resize: "vertical",
                        boxSizing: "border-box", padding: 12, borderRadius: 8,
                        border: "1px solid #d8d8e2", background: "#f8f8fc",
                        color: "#222", fontSize: 13, lineHeight: 1.5,
                      }}
                    />
                    <div style={{ color: "#888", fontSize: 11, textAlign: "right", marginTop: 4 }}>
                      {userInstructions.length}/2000
                    </div>
                  </div>
                  <button 
                    onClick={() => handleAdvance({
                      confirmed_gaps: [],
                      sections_to_rewrite: session.data.analysis?.sections_to_rewrite || [],
                      user_additions: userInstructions,
                    })}
                    disabled={session.loading}
                    style={{ background: "var(--accent)", border: "none", color: "#fff", padding: "12px 24px", borderRadius: 8, fontSize: 14, fontWeight: 700, cursor: "pointer", width: "100%" }}
                  >
                    {session.loading ? "Preparing draft…" : "Confirm & Start Drafting"}
                  </button>
                  {error && (
                    <p role="alert" style={{ color: "#b91c1c", fontSize: 12, margin: "10px 0 0" }}>
                      Drafting could not continue: {error}
                    </p>
                  )}
                </div>
              )}

              {session.gate === "slot_filling" && (
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
                    <span style={{ background: "var(--accent)", color: "#fff", borderRadius: 20, padding: "4px 12px", fontSize: 10, fontWeight: 800 }}>
                      QUESTION
                    </span>
                  </div>
                  <h3 style={{ margin: "0 0 20px", fontSize: 18, fontWeight: 700 }}>
                    {Object.values(session.data.slots || {}).find(s => !s.filled)?.question || "Tell me more about your project..."}
                  </h3>
                  <textarea
                    autoFocus
                    placeholder="Type your answer here..."
                    style={{
                      width: "100%", minHeight: 120, background: "#f8f8fc", border: "2px solid #eef",
                      borderRadius: 12, padding: "16px", fontSize: 14, outline: "none", boxSizing: "border-box", marginBottom: 16
                    }}
                    onKeyDown={e => {
                        if (e.key === "Enter" && !e.shiftKey) {
                            e.preventDefault();
                            handleAdvance({ answer: e.target.value });
                            e.target.value = "";
                        }
                    }}
                  />
                  <button 
                    onClick={(e) => {
                        const ta = e.target.previousSibling;
                        handleAdvance({ answer: ta.value });
                        ta.value = "";
                    }}
                    style={{ background: "var(--accent)", border: "none", color: "#fff", padding: "12px 24px", borderRadius: 8, fontSize: 14, fontWeight: 700, cursor: "pointer", width: "100%" }}
                  >
                    Next Question
                  </button>
                </div>
              )}

              {session.gate === "slot_confirm" && (
                <div>
                  <h3 style={{ margin: "0 0 10px", fontSize: 18, fontWeight: 800 }}>Confirm Details</h3>
                  <p style={{ color: "#666", fontSize: 13, marginBottom: 20 }}>
                    Please review the information collected before I regenerate the proposal:
                  </p>
                  <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: 24 }}>
                    <tbody>
                      {Object.entries(session.data.slots || {}).map(([k, s]) => (
                        <tr key={k} style={{ borderBottom: "1px solid #eee" }}>
                          <td style={{ padding: "10px 0", fontWeight: 700, fontSize: 12, color: "#555", width: "35%" }}>{k}</td>
                          <td style={{ padding: "10px 0", fontSize: 12, color: "#777" }}>{s.value || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <button 
                    onClick={() => handleAdvance({ confirmed: true })}
                    style={{ background: "var(--accent)", border: "none", color: "#fff", padding: "12px 24px", borderRadius: 8, fontSize: 14, fontWeight: 700, cursor: "pointer", width: "100%" }}
                  >
                    Everything Looks Good — Draft Now
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Empty state (when no session or drafting) */}
          {session.gate === "none" && !session.loading && (
            <div style={{ width: 760, background: "#fff", borderRadius: 2, padding: "100px 80px", textAlign: "center", boxShadow: "0 4px 32px rgba(0,0,0,0.4)" }}>
              <p style={{ fontSize: 40, marginBottom: 16 }}>✍</p>
              <p style={{ fontWeight: 800, color: "#1a1a2e", fontSize: 22, marginBottom: 8 }}>
                {!resolvedProposal ? "Upload or select a saved proposal" : !selectedGrant ? "Select a grant to begin" : "Ready to draft"}
              </p>
              <p style={{ color: "#888", fontSize: 14, maxWidth: 340, margin: "0 auto 24px" }}>
                {!resolvedProposal ? "Go to Grants to upload a proposal, or pick a saved one below." : "Choose a target grant from the left panel and click Draft."}
              </p>
              {!proposal && (
                <button onClick={() => navigate("/grants")} style={{ background: "#7c6fef", border: "none", color: "#fff", padding: "12px 28px", borderRadius: 8, fontSize: 14, fontWeight: 700, cursor: "pointer" }}>
                  Upload Proposal
                </button>
              )}
            </div>
          )}

          {/* Loading state */}
          {session.loading && streamSectionOrder.length === 0 && (
            <div style={{ width: 760, background: "#fff", borderRadius: 12, padding: "80px", textAlign: "center", boxShadow: "0 10px 40px rgba(0,0,0,0.5)" }}>
              <p style={{ color: "var(--accent)", fontSize: 18, fontWeight: 700 }}>
                {Object.keys(streamedSections).length
                  ? "Drafting your updated proposal…"
                  : session.gate === "gap_analysis" ? "Analyzing gaps..." : "Processing..."}
              </p>
              <p style={{ color: "#bbb", fontSize: 13, marginTop: 12 }}>
                {Object.keys(streamedSections).length
                  ? "Your draft will appear below as each section is written."
                  : "This helps us build a more persuasive proposal"}
              </p>
            </div>
          )}

          {session.loading && streamSectionOrder.length > 0 && (
            <div style={{
              width: 760, marginTop: 14, background: "#fff", borderRadius: 12,
              padding: "28px 40px", boxShadow: "0 10px 40px rgba(0,0,0,0.35)",
            }}>
              {streamSectionOrder.map(key => {
                const content = streamedSections[key] || "";
                return (
                <section key={key} style={{ marginBottom: 24 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
                    <h3 style={{ color: "#1a1a2e", font: "700 16px Georgia, serif", margin: 0 }}>
                      {key.replace(/_/g, " ").replace(/\b\w/g, char => char.toUpperCase())}
                    </h3>
                    <span style={{
                      color: content ? "#765fe8" : "#888",
                      background: content ? "#f0edff" : "#f3f3f6",
                      borderRadius: 20, padding: "4px 9px",
                      fontSize: 10, fontWeight: 700,
                    }}>
                      {content ? "Drafting" : "Preparing"}
                    </span>
                  </div>
                  {content ? (
                    <p aria-live="polite" style={{
                      color: "#333", font: "14px/1.9 Georgia, serif",
                      whiteSpace: "pre-wrap", margin: 0,
                    }}>
                      {content}<span style={{ color: "#7c6fef" }} aria-hidden="true">▍</span>
                    </p>
                  ) : (
                    <div style={{ display: "flex", alignItems: "center", gap: 10, minHeight: 34 }}>
                      <span aria-label="Waiting for section draft" style={{
                        width: 18, height: 18, boxSizing: "border-box",
                        border: "2px solid #e5e1fb", borderTopColor: "#7c6fef",
                        borderRadius: "50%", animation: "draft-section-spin 0.8s linear infinite",
                      }} />
                      <span style={{ color: "#999", fontSize: 13 }}>Preparing this section…</span>
                    </div>
                  )}
                </section>
                );
              })}
              <style>{`
                @keyframes draft-section-spin {
                  to { transform: rotate(360deg); }
                }
              `}</style>
            </div>
          )}

          {/* The Document — white page */}
          {(session.gate === "draft_review" || session.gate === "final_save" || session.gate === "complete")
            && compareMode && (
              <div style={{
                width: "min(1200px, calc(100% - 32px))",
                background: "#fff", borderRadius: 12, overflow: "hidden",
                boxShadow: "0 10px 50px rgba(0,0,0,0.5)", marginBottom: 24,
              }}>
                <div style={{
                  background: "#13131f", padding: "18px 28px",
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                }}>
                  <div>
                    <p style={{ color: "#7c6fef", fontSize: 10, fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.1em", margin: "0 0 3px" }}>
                      Full proposal comparison
                    </p>
                    <p style={{ color: "#fff", fontWeight: 700, fontSize: 14, margin: 0 }}>
                      {selectedGrant?.title || "Grant Proposal"}
                    </p>
                  </div>
                  <div style={{ display: "flex", gap: 12, color: "#aaa", fontSize: 11 }}>
                    <span><span style={{ background: "#dcfce7", color: "#166534", padding: "2px 5px" }}>Green</span> added</span>
                    <span><span style={{ background: "#fee2e2", color: "#991b1b", padding: "2px 5px", textDecoration: "line-through" }}>Red</span> removed</span>
                  </div>
                </div>
                <div style={{
                  display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
                  alignItems: "start",
                }}>
                  {[
                    { label: "Original proposal", variant: "original" },
                    { label: "Revised proposal", variant: "revised" },
                  ].map(column => (
                    <div key={column.variant} style={{
                      minWidth: 0,
                      borderRight: column.variant === "original" ? "1px solid #e8e8f0" : "none",
                    }}>
                      <div style={{
                        position: "sticky", top: 0, zIndex: 2,
                        background: "#f7f7fb", borderBottom: "1px solid #e8e8f0",
                        padding: "12px 24px", color: "#343247", fontSize: 12, fontWeight: 800,
                      }}>
                        {column.label}
                      </div>
                      <div style={{ padding: "4px 24px 28px" }}>
                        <header style={{
                          padding: "22px 0 18px", marginBottom: 4,
                          borderBottom: "2px solid #e6e4ef",
                        }}>
                          <p style={{
                            margin: "0 0 8px", color: "#7066ad", font: "700 9px/1.4 Arial, sans-serif",
                            letterSpacing: "0.12em", textTransform: "uppercase",
                          }}>
                            ImpactLink · Grant proposal
                          </p>
                          <h1 style={{
                            margin: "0 0 8px", color: "#19192c",
                            font: "700 25px/1.25 Georgia, serif",
                          }}>
                            {selectedGrant?.title || "Grant Proposal"}
                          </h1>
                          {(selectedGrant?.agency || proposal?.organization_name) && (
                            <p style={{
                              margin: 0, color: "#6b6b7b", font: "12px/1.5 Arial, sans-serif",
                            }}>
                              {[selectedGrant?.agency, proposal?.organization_name].filter(Boolean).join(" · ")}
                            </p>
                          )}
                        </header>
                        {sectionOrder.map((key, index) => {
                          const original = originalSections[key]
                            ?? resolvedProposal?.sections?.[key]?.content
                            ?? resolvedProposal?.sections?.[key]
                            ?? sections[key]?.content
                            ?? "";
                          const draftedContent = sections[key]?.content ?? original;
                          const revised = editedContent[key] ?? draftedContent;
                          const hasManualChanges = revised !== draftedContent;
                          const draftedDiffTokens = compareSectionDiffs[key];
                          const revisionTokens = hasManualChanges
                            ? composeRevisedDiffTokens(
                              draftedDiffTokens,
                              createTextDiff(draftedContent, revised),
                              draftedContent,
                              revised,
                            )
                            : draftedDiffTokens;
                          return (
                            <section
                              key={key}
                              id={column.variant === "revised" ? `draft-section-${key}` : undefined}
                              data-section-key={column.variant === "revised" ? key : undefined}
                              ref={column.variant === "revised"
                                ? element => { sectionRefs.current[key] = element; }
                                : undefined}
                              style={{
                                padding: "22px 0 18px",
                                borderBottom: index < sectionOrder.length - 1 ? "1px solid #ececf3" : "none",
                                scrollMarginTop: 56,
                              }}
                            >
                              <div style={{
                                display: "flex", alignItems: "center",
                                justifyContent: "space-between", gap: 12,
                                marginBottom: key !== "proposal" && key !== "uploaded_content" ? 14 : 0,
                              }}>
                                {key !== "proposal" && key !== "uploaded_content" ? (
                                  <h2 style={{
                                    font: "700 17px/1.35 Georgia, serif", color: "#1a1a2e",
                                    margin: 0,
                                  }}>
                                    {SECTION_ICONS[key] || String(index + 1).padStart(2, "0")}
                                    {"  "}
                                    {getSectionTitle(key, sections[key])}
                                  </h2>
                                ) : <span />}
                                </div>
                                {column.variant === "original" ? (
                                  <FormattedProposalContent
                                    tokens={draftedDiffTokens}
                                    variant="original"
                                    fallback={original}
                                    sectionTitle={getSectionTitle(key, sections[key])}
                                  />
                                ) : (
                                  <CompareEditableSection
                                    tokens={revisionTokens}
                                    value={revised}
                                    sectionTitle={getSectionTitle(key, sections[key])}
                                    onChange={value => handleEdit(key, value)}
                                  />
                                )}
                            </section>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          {(session.gate === "draft_review" || session.gate === "final_save" || session.gate === "complete")
            && !compareMode && sectionOrder.map(key => (
            <div
              key={key}
              id={`draft-section-${key}`}
              data-section-key={key}
              ref={element => { sectionRefs.current[key] = element; }}
              onMouseDown={() => setActiveTab(key)}
              style={{
              width: 760,
              background: "#ffffff",
              borderRadius: 12,
              boxShadow: "0 10px 50px rgba(0,0,0,0.5)",
              overflow: "hidden",
              marginBottom: 24,
              scrollMarginTop: 16,
            }}>
              {/* Document header strip */}
              <div style={{ background: "#13131f", padding: "14px 56px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div>
                  <p style={{ color: "#7c6fef", fontSize: 10, fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.1em", margin: "0 0 3px" }}>Grant Proposal</p>
                  <p style={{ color: "#fff", fontWeight: 700, fontSize: 14, margin: 0 }}>{selectedGrant?.title || "Proposal"}</p>
                </div>
                <div style={{ textAlign: "right" }}>
                  <p style={{ color: "#555", fontSize: 10, margin: "0 0 2px" }}>{selectedGrant?.agency}</p>
                  <p style={{ color: "#333", fontSize: 10, margin: 0 }}>{new Date().toLocaleDateString()}</p>
                </div>
              </div>

              {/* Section header */}
              {key !== "proposal" && key !== "uploaded_content" && (
                <div style={{ padding: "32px 56px 0" }}>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 14, marginBottom: 20 }}>
                    <span style={{ fontSize: 11, fontWeight: 900, color: "#c8c5f8", fontFamily: "monospace", letterSpacing: "0.05em" }}>
                      {SECTION_ICONS[key] || "00"}
                    </span>
                    <h2 style={{ fontSize: 18, fontWeight: 800, color: "#1a1a2e", margin: 0, letterSpacing: "-0.02em", fontFamily: "Georgia, serif" }}>
                      {getSectionTitle(key, sections[key])}
                    </h2>
                  </div>
                  <div style={{ height: 1, background: "#e8e8f4", marginBottom: 28 }} />
                </div>
              )}

              {/* Editable content */}
              <div style={{ padding: "0 56px 48px" }}>
                <div style={{
                  display: "flex", justifyContent: "flex-end", gap: 6, marginBottom: 8,
                }}>
                  {[
                    { label: "Edit text", preview: false },
                    { label: "Formatted preview", preview: true },
                  ].map(option => (
                    <button
                      key={option.label}
                      type="button"
                      aria-pressed={Boolean(previewSections[key]) === option.preview}
                      onClick={() => setPreviewSections(previous => ({
                        ...previous,
                        [key]: option.preview,
                      }))}
                      style={{
                        border: "1px solid #e2e1eb", borderRadius: 5,
                        background: Boolean(previewSections[key]) === option.preview ? "#f0edff" : "#fff",
                        color: "#49465e", padding: "5px 8px", fontSize: 10, cursor: "pointer",
                      }}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
                {previewSections[key] ? (
                  <div style={{
                    minHeight: 240, padding: "10px 0", color: "#1a1a2e",
                    font: "13px/1.8 Georgia, serif",
                  }}>
                    <FormattedProposalContent
                      variant="revised"
                      fallback={editedContent[key] ?? sections[key]?.content ?? originalSections[key] ?? ""}
                      sectionTitle={getSectionTitle(key, sections[key])}
                    />
                  </div>
                ) : (
                  <textarea
                    ref={element => { textareaRefs.current[key] = element; }}
                    value={editedContent[key] ?? sections[key]?.content ?? originalSections[key] ?? ""}
                    onFocus={() => setActiveTab(key)}
                    onChange={e => handleEdit(key, e.target.value)}
                    spellCheck
                    style={{
                      width: "100%", minHeight: 420,
                      border: "none", outline: "none",
                      resize: "vertical", background: "transparent",
                      font: "13px/1.8 Georgia, 'Times New Roman', serif",
                      color: "#1a1a2e", caretColor: "#7c6fef",
                      boxSizing: "border-box", whiteSpace: "pre-wrap",
                    }}
                    placeholder="Content will appear here once drafted…"
                  />
                )}
              </div>

              <div style={{ background: "#f8f8fc", borderTop: "1px solid #eeeef8", padding: "10px 56px", color: "#888", fontSize: 11 }}>
                {wordCounts[key] || 0} words
              </div>
            </div>
          ))}

          {/* Writing next section indicator */}
          {loading && hasSections && (
            <div style={{ width: 760, marginTop: 12, background: "#13131f", border: "1px dashed #2a2a4e", borderRadius: 8, padding: "16px 24px", display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ color: "var(--accent)", fontSize: 16 }}>⟳</span>
              <p style={{ color: "var(--accent)", fontSize: 13, margin: 0, fontWeight: 600 }}>Writing next section…</p>
            </div>
          )}

          {/* Done banner */}
          {done && (
            <div style={{
              width: 760, marginTop: 16,
              background: "#0d2e1a", border: "1px solid #166534",
              borderRadius: 8, padding: "16px 24px",
              display: "flex", alignItems: "center", justifyContent: "space-between",
            }}>
              <div>
                <p style={{ fontWeight: 700, color: "var(--green)", fontSize: 14, margin: "0 0 2px" }}>✓ All {sectionOrder.length} sections complete</p>
                <p style={{ color: "#2d5a3d", fontSize: 12, margin: 0 }}>Tailored for {selectedGrant?.agency} · {totalWords.toLocaleString()} words</p>
              </div>
              <button
                onClick={handleDownloadPDF}
                disabled={pdfLoading}
                style={{ background: "#e63946", border: "none", color: "#fff", padding: "10px 20px", borderRadius: 8, fontSize: 13, fontWeight: 700, cursor: "pointer" }}
              >
                {pdfLoading ? "⟳ Generating…" : "↓ Download PDF"}
              </button>
            </div>
          )}

          {error && (
            <div style={{ width: 760, marginTop: 12, background: "#2d0f0f", border: "1px solid #7f1d1d", borderRadius: 8, padding: "14px 20px", color: "var(--red)", fontSize: 13 }}>
              ⚠ {error}
            </div>
          )}
        </div>

        {/* Right panel — funder context */}
        {selectedGrant && (
          <div style={{
            width: 200, flexShrink: 0, background: "#0f0f1a",
            borderLeft: "1px solid #1e1e2e", padding: "16px 14px",
            position: "sticky", top: 112, height: "calc(100vh - 112px)", overflowY: "auto",
          }}>
            <p style={{ color: "#2a2a3e", fontSize: 9, fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.1em", margin: "0 0 10px" }}>Funder</p>
            <p style={{ color: "var(--accent)", fontWeight: 700, fontSize: 12, margin: "0 0 3px" }}>{selectedGrant.agency}</p>
            <p style={{ color: "#444", fontSize: 11, margin: "0 0 10px", lineHeight: 1.5 }}>
              {selectedGrant.title.slice(0, 70)}{selectedGrant.title.length > 70 ? "…" : ""}
            </p>

            <div style={{ background: "#1a1a28", borderRadius: 6, padding: "8px 10px", marginBottom: 12 }}>
              <p style={{ color: "#444", fontSize: 9, fontWeight: 700, textTransform: "uppercase", margin: "0 0 3px" }}>
                Match score
              </p>
              <p style={{ color: "var(--accent)", fontWeight: 800, fontSize: 18, margin: "0 0 4px" }}>
                {matchComparison.status === "updated"
                  ? `${matchComparison.before}% → ${matchComparison.after}%`
                  : `${selectedGrant.similarity_score}%`}
              </p>
              <p style={{ color: "#666", fontSize: 9, margin: 0 }}>
                {matchComparison.status === "updated"
                  ? "Original proposal → new draft"
                  : matchComparison.status === "updating"
                    ? "Recalculating for new draft…"
                    : matchComparison.status === "unavailable"
                      ? "New draft match score unavailable"
                      : "Original proposal match"}
              </p>
            </div>

            {selectedGrant.close_date && (
              <p style={{ color: "var(--red)", fontSize: 10, fontWeight: 700, marginBottom: 12 }}>⏰ Due {selectedGrant.close_date}</p>
            )}

            <div style={{ borderTop: "1px solid #1e1e2e", paddingTop: 12, marginBottom: 12 }}>
              <p style={{ color: "#2a2a3e", fontSize: 9, fontWeight: 800, textTransform: "uppercase", letterSpacing: "0.1em", margin: "0 0 7px" }}>Focus Areas</p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
                {(Array.isArray(selectedGrant.focus_areas)
                  ? selectedGrant.focus_areas
                  : (selectedGrant.focus_areas || "").split(",").map(f => f.trim()).filter(Boolean)
                ).slice(0, 5).map(f => (
                  <span key={f} style={{ background: "#1e1e2e", color: "#555", border: "1px solid #2a2a3e", borderRadius: 3, padding: "1px 5px", fontSize: 9 }}>{f}</span>
                ))}
              </div>
            </div>

            {selectedGrant.application_tip && (
              <div style={{ background: "#1a1a28", borderRadius: 6, padding: "10px" }}>
                <p style={{ color: "#2a2a3e", fontSize: 9, fontWeight: 800, textTransform: "uppercase", margin: "0 0 5px" }}>💡 Tip</p>
                <p style={{ color: "#555", fontSize: 10, lineHeight: 1.6, margin: 0 }}>{selectedGrant.application_tip}</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}