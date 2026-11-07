import { proposalContext, stageProposalMatch } from "../services/proposals";
import { useEffect, useState, useRef } from "react";
import { useSearchParams, useNavigate, useLocation } from "react-router-dom";
import { Nav } from "../components";
import useGrants from "../hooks/useGrants";
import { useAuth } from "../context/AuthContext";
import useWorkStore from "../hooks/useWorkStore";
import useProposalSession from "../hooks/useProposalSession";
import api, { saveSessionChecklist } from "../services/api";
import { ApplicationRequirementsEditor, ApplicationReview } from "../components/ApplicationRequirements";
import AiPrivacyNotice from "../components/AiPrivacyNotice";
import { createProposalPdf } from "../utils/proposalPdf";
import "./Draft.css";
import { applicationCheck, aiPolicyCheck, emptyApplicationSpec } from "../utils/application";
import { matchFingerprint } from "../utils/matchAssessment";

const GAP_GROUPS = { missing_content: "Missing content", weak_evidence: "Evidence to strengthen", wrong_vocabulary: "Terminology", misalignment: "Funder alignment", missing_sections: "Missing application answers", requested_changes: "Requested changes" };

function GapSummary({ analysis }) {
  if (!analysis) return <section className="draft-card" aria-label="Gap analysis"><h2>Gap analysis</h2><p>No gap analysis was saved with this revision.</p></section>;
  const groups = Object.entries(GAP_GROUPS).filter(([key]) => analysis[key]?.length);
  return <section className="draft-card" aria-label="Gap analysis"><h2>Review the gaps</h2>
    <p>Review these findings, choose the areas to change, then click Draft. Other sections are preserved.</p>
    {!groups.length && <p>{analysis.status === "unavailable" ? "Gap analysis could not be completed. Return to setup and try again." : "No specific gaps were recorded."}</p>}
    {groups.map(([key, label]) => <div key={key}><h3 style={{ fontSize: 13, margin: "14px 0 6px" }}>{label}</h3><ul style={{ paddingLeft: 20 }}>{analysis[key].map((gap, i) => <li key={i} style={{ marginBottom: 8, fontSize: 13, lineHeight: 1.7 }}><strong>{getSectionTitle(gap.section || "proposal")}</strong>{gap.severity && ` · ${gap.severity}`} — {gap.description}</li>)}</ul></div>)}
  </section>;
}

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

function getSectionTitle(key, section) {
  if (key === "uploaded_content") return "Proposal";
  return section?.title || key.replace(/_/g, " ").replace(/\b\w/g, char => char.toUpperCase());
}

function normalizeSectionMap(sectionMap) {
  const normalized = Object.fromEntries(Object.entries(sectionMap || {}).map(([key, value]) => [key, typeof value === "string" ? { title: getSectionTitle(key), content: value } : { ...value }]));
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
            data-change={token.type === "add" ? "add" : undefined}
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
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const loadId = searchParams.get("load");
  const { profile } = useAuth();
  const { grants, proposal } = useGrants();
  const { drafts, proposals, saveDraft, updateDraft, loading: workLoading } = useWorkStore();
  const session = useProposalSession();
  const [proposalId, setProposalId] = useState("");
  const [grantId, setGrantId] = useState(searchParams.get("grant") || "");
  const [grant, setGrant] = useState(null);
  const [spec, setSpec] = useState(emptyApplicationSpec);
  const [prefilling, setPrefilling] = useState(false);
  const [prefill, setPrefill] = useState(null);
  const [setupError, setSetupError] = useState("");
  const [instructions, setInstructions] = useState("");
  const [revisionName, setRevisionName] = useState("");
  const [edited, setEdited] = useState({});
  const [streamed, setStreamed] = useState({});
  const [streamOrder, setStreamOrder] = useState([]);
  const [compare, setCompare] = useState(false);
  const [editingDraft, setEditingDraft] = useState(false);
  const [selectedAreas, setSelectedAreas] = useState([]);
  const [draftStarting, setDraftStarting] = useState(false);
  const [saveStatus, setSaveStatus] = useState("");
  const [saveError, setSaveError] = useState("");
  const [pdfLoading, setPdfLoading] = useState(false);
  const [launching, setLaunching] = useState(false);
  const [matchAssessment, setMatchAssessment] = useState(null);
  const [matching, setMatching] = useState(false);
  const [matchError, setMatchError] = useState("");
  const [originalAssessment, setOriginalAssessment] = useState(null);
  const [originalMatching, setOriginalMatching] = useState(false);
  const [originalMatchError, setOriginalMatchError] = useState("");
  const originalAssessmentRef = useRef(null);
  const originalMatchRequest = useRef(0);
  const originalAutoMatch = useRef(null);
  const originalSavedKey = useRef(null);
  const latestOriginalKey = useRef(null);
  const matchAssessmentRef = useRef(null);
  const matchRequest = useRef(0);
  const autoMatch = useRef(null);
  const latestMatchKey = useRef(null);
  const [activeTab, setActiveTab] = useState(null);
  const textareaRefs = useRef({});
  const prefillRequest = useRef(0);
  const sourceSnapshot = useRef(null);
  const revisionId = useRef(null);
  const saveQueue = useRef(Promise.resolve());
  const autosaved = useRef(null);
  const reviewSelection = useRef(null);
  const restored = useRef(null);
  const loaded = useRef(null);
  const sections = normalizeSectionMap(session.data.sections);
  const sourceItem = proposals.find(item => item.id === proposalId);
  const context = sourceItem ? proposalContext(sourceItem, profile || {}) : proposal;
  const loadedDraft = drafts.find(item => item.id === loadId);
  const writingPage = location.pathname.endsWith("/write") || Boolean(loadId && loadedDraft?.grant_id);
  const ready = ["draft_review", "final_save", "complete"].includes(session.gate) && Object.keys(sections).length > 0;
  const effectiveGrant = session.data.grant || grant || loadedDraft?.grant;
  const sourceTitle = sourceItem?.title || context?.project_title || "Original proposal";
  const defaultName = `${sourceTitle} - ${grant?.title || "Grant revision"}`;
  const title = sourceSnapshot.current?.title || revisionName || defaultName;
  const currentSections = Object.fromEntries(Object.entries(sections).map(([key, item]) => [key, { ...item, content: edited[key] ?? item.content ?? "" }]));
  const check = applicationCheck(spec, currentSections);
  const analysisUnavailable = session.data.analysis?.status === "unavailable";
  const matchGrantId = effectiveGrant?.grant_id || grantId;
  const matchProposal = sourceSnapshot.current && ready ? proposalContext({
    title: sourceSnapshot.current.source_title,
    proposal_context: sourceSnapshot.current.context, application_spec: spec, sections: currentSections,
  }, profile || {}) : null;
  const matchKey = matchProposal && matchGrantId ? matchFingerprint(matchGrantId, matchProposal) : null;
  latestMatchKey.current = matchKey;
  const freshMatch = Boolean(matchAssessment && matchAssessment.fingerprint === matchKey);
  const originalProposal = sourceSnapshot.current ? proposalContext({
    title: sourceSnapshot.current.source_title, proposal_context: sourceSnapshot.current.context,
    application_spec: spec, sections: sourceSnapshot.current.originals,
  }, profile || {}) : null;
  const originalKey = originalProposal && matchGrantId ? matchFingerprint(matchGrantId, originalProposal) : null;
  latestOriginalKey.current = originalKey;
  const freshOriginalMatch = Boolean(originalAssessment && originalAssessment.fingerprint === originalKey);

  useEffect(() => () => { matchRequest.current += 1; originalMatchRequest.current += 1; }, []);

  useEffect(() => {
    if (!proposalId && proposals.length) {
      const preferred = loadId || sessionStorage.getItem("upload_draft_id");
      setProposalId(proposals.some(item => item.id === preferred) ? preferred : proposals[0].id);
    }
  }, [proposalId, proposals, loadId]);

  useEffect(() => {
    if (writingPage || !grantId || session.loading) return undefined;
    const request = ++prefillRequest.current;
    let active = true;
    setPrefilling(true); setPrefill(null); setSetupError(""); setSpec(emptyApplicationSpec());
    const cached = grants.find(item => String(item.grant_id) === String(grantId));
    setGrant(cached || null);
    (async () => {
      try {
        const response = await api.get(`/api/grants/${encodeURIComponent(grantId)}`);
        const selected = response.data.grant || response.data;
        if (!active || request !== prefillRequest.current) return;
        setGrant(selected);
        const result = selected.application_spec
          ? { application_spec: selected.application_spec, evidence: [], warnings: ["Requirements already recorded for this grant. Review before redrafting."] }
          : (await api.post(`/api/grants/${encodeURIComponent(grantId)}/application-requirements`)).data;
        if (!active || request !== prefillRequest.current) return;
        setSpec({ ...emptyApplicationSpec(), ...result.application_spec });
        setPrefill(result);
      } catch (error) {
        if (active && request === prefillRequest.current) setSetupError("Could not prefill the grant requirements. You can enter the missing information below.");
      } finally { if (active && request === prefillRequest.current) setPrefilling(false); }
    })();
    return () => { active = false; };
    // Changes to the target grant start a new setup; manual edits do not refetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [grantId, writingPage]);

  useEffect(() => {
    if (session.data.application_spec) setSpec(session.data.application_spec);
    if (session.data.grant) setGrant(session.data.grant);
  }, [session.data.application_spec, session.data.grant]);

  useEffect(() => {
    if (!writingPage || loadId) return;
    const id = searchParams.get("session");
    if (!id || restored.current === id || session.sessionId === id) return;
    restored.current = id;
    session.restore(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [writingPage, loadId, searchParams, session.sessionId]);

  useEffect(() => {
    if (!writingPage || sourceSnapshot.current || !session.data.grant) return;
    const info = session.data.grant.revision_context || {};
    sourceSnapshot.current = {
      title: info.title || "Recovered revision", source_title: info.source_title || "Original proposal",
      source_proposal_id: info.source_proposal_id || null,
      originals: normalizeSectionMap(session.data.original_sections), context: {},
    };
    setRevisionName(sourceSnapshot.current.title);
    setInstructions(info.instructions || "");
  }, [writingPage, session.data.grant, session.data.original_sections]);

  useEffect(() => {
    if (!loadId || !loadedDraft || loaded.current === loadId) return;
    loaded.current = loadId;
    setProposalId(loadedDraft.source_proposal_id || loadedDraft.id);
    if (!loadedDraft.grant_id) return;
    revisionId.current = loadedDraft.id;
    matchAssessmentRef.current = loadedDraft.match_assessment || null;
    setMatchAssessment(matchAssessmentRef.current);
    originalAssessmentRef.current = loadedDraft.original_match_assessment || null;
    originalSavedKey.current = originalAssessmentRef.current?.fingerprint || null;
    setOriginalAssessment(originalAssessmentRef.current);
    setGrantId(String(loadedDraft.grant_id));
    setGrant(loadedDraft.grant || { grant_id: loadedDraft.grant_id, title: loadedDraft.grant_title });
    setSpec(loadedDraft.application_spec || emptyApplicationSpec());
    sourceSnapshot.current = {
      title: loadedDraft.title, source_title: loadedDraft.source_title || "Original proposal",
      source_proposal_id: loadedDraft.source_proposal_id || null,
      originals: normalizeSectionMap(loadedDraft.original_sections), context: loadedDraft.proposal_context || {},
    };
    session.setData({ sections: loadedDraft.sections || {}, diffs: loadedDraft.diffs || {}, grant: loadedDraft.grant, analysis: loadedDraft.analysis || null });
    session.setGate("complete");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadId, loadedDraft]);

  useEffect(() => {
    if (!ready) return;
    setEdited(Object.fromEntries(Object.entries(sections).map(([key, value]) => [key, value.content || ""])));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.data.sections, ready]);

  const saveRevision = (checklistSpec = spec, assessmentOverride = matchAssessmentRef.current) => {
    const snapshot = sourceSnapshot.current;
    if (!snapshot || !Object.keys(currentSections).length) return Promise.resolve(null);
    const metadata = {
      title: snapshot.title, source_title: snapshot.source_title,
      source_proposal_id: snapshot.source_proposal_id, grant_title: effectiveGrant?.title || "",
      grant_id: String(effectiveGrant?.grant_id || grantId), agency: effectiveGrant?.agency || "",
      grant: { ...effectiveGrant, application_spec: checklistSpec }, application_spec: checklistSpec, original_sections: snapshot.originals,
      sections: currentSections, section_order: Object.keys(currentSections), diffs: comparisonDiffs,
      session_id: session.sessionId,
      analysis: session.data.analysis || loadedDraft?.analysis || null,
      match_assessment: assessmentOverride,
      original_match_assessment: originalAssessmentRef.current,
      matched_grants: assessmentOverride?.fingerprint === matchKey && assessmentOverride.match ? [assessmentOverride.match] : [],
      proposal_context: proposalContext({ title: snapshot.title, application_spec: checklistSpec, proposal_context: snapshot.context, sections: currentSections }, profile || {}),
    };
    if (originalAssessmentRef.current) originalSavedKey.current = originalAssessmentRef.current.fingerprint;
    const operation = saveQueue.current.catch(() => {}).then(async () => {
      const saved = revisionId.current
        ? await updateDraft(revisionId.current, currentSections, null, metadata)
        : await saveDraft(metadata);
      if (!saved) throw new Error("Could not save the revised proposal. Your original has not been changed.");
      revisionId.current = saved.id;
      setSaveStatus("Saved"); setSaveError("");
      return saved;
    });
    saveQueue.current = operation;
    return operation;
  };

  const saveChecklist = async nextSpec => {
    const id = session.sessionId || loadedDraft?.session_id;
    if (id) await saveSessionChecklist(id, nextSpec);
    const saved = await saveRevision(nextSpec);
    if (!saved) throw new Error("No revised proposal is available to save. Please reopen the draft and retry.");
    return saved;
  };

  useEffect(() => {
    if (session.sessionId && !revisionId.current) {
      const saved = drafts.find(item => item.session_id === session.sessionId);
      if (saved) revisionId.current = saved.id;
    }
  }, [drafts, session.sessionId]);

  useEffect(() => {
    if (workLoading || !ready || loadId || !session.sessionId || autosaved.current === session.sessionId || !sourceSnapshot.current) return;
    if (session.data.application_spec && spec !== session.data.application_spec) return;
    autosaved.current = session.sessionId;
    saveRevision().catch(error => setSaveError(error.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, session.sessionId, session.data.application_spec, spec, loadId, workLoading]);

  const refreshMatch = async () => {
    if (!matchProposal || !matchGrantId || !ready || matching) return;
    const request = ++matchRequest.current;
    const fingerprint = matchKey;
    setMatching(true); setMatchError("");
    try {
      const response = await api.post("/api/match", {
        proposal: matchProposal, grant_id: String(matchGrantId), top_k: 1, target_only: true,
        eligibility_context: matchProposal.eligibility_context,
      });
      if (request !== matchRequest.current || latestMatchKey.current !== fingerprint) return;
      if (!Array.isArray(response.data?.matches)) throw new Error("The match service returned no assessment. Please retry.");
      const result = {
        fingerprint, grant_id: String(matchGrantId), checked_at: new Date().toISOString(),
        match: response.data.matches.find(item => String(item.grant_id) === String(matchGrantId)) || null,
      };
      matchAssessmentRef.current = result; setMatchAssessment(result);
      await saveRevision(spec, result);
    } catch (error) {
      if (request === matchRequest.current && latestMatchKey.current === fingerprint) setMatchError(error.response?.data?.detail || error.message || "Could not refresh the match. Please retry.");
    } finally { if (request === matchRequest.current) setMatching(false); }
  };

  useEffect(() => {
    const identity = loadId || session.sessionId;
    if (!ready || !matchKey || !identity || autoMatch.current === identity || workLoading) return;
    autoMatch.current = identity;
    if (!freshMatch) refreshMatch();
    // One automatic assessment per completed revision; manual edits mark it stale.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, matchKey, loadId, session.sessionId, workLoading]);

  const refreshOriginalMatch = async () => {
    if (!originalProposal || !matchGrantId || originalMatching) return;
    const request = ++originalMatchRequest.current;
    const fingerprint = originalKey;
    originalAutoMatch.current = fingerprint;
    setOriginalMatching(true); setOriginalMatchError("");
    try {
      const response = await api.post("/api/match", {
        proposal: originalProposal, grant_id: String(matchGrantId), top_k: 1, target_only: true,
        eligibility_context: originalProposal.eligibility_context,
      });
      if (request !== originalMatchRequest.current || latestOriginalKey.current !== fingerprint) return;
      if (!Array.isArray(response.data?.matches)) throw new Error("The original match could not be assessed. Please retry.");
      const result = { fingerprint, grant_id: String(matchGrantId), checked_at: new Date().toISOString(), match: response.data.matches.find(item => String(item.grant_id) === String(matchGrantId)) || null };
      originalAssessmentRef.current = result; setOriginalAssessment(result);
    } catch (error) {
      if (request === originalMatchRequest.current && latestOriginalKey.current === fingerprint) setOriginalMatchError(error.response?.data?.detail || error.message || "Could not assess the original proposal.");
    } finally { if (request === originalMatchRequest.current) setOriginalMatching(false); }
  };

  useEffect(() => {
    if (!writingPage || session.gate !== "gap_review" || analysisUnavailable || !originalKey || freshOriginalMatch || originalAutoMatch.current === originalKey) return;
    if (session.data.application_spec && spec !== session.data.application_spec) return;
    refreshOriginalMatch();
    // Assess the source proposal while gaps are reviewed; never start drafting.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [writingPage, session.gate, originalKey, freshOriginalMatch, analysisUnavailable, spec, session.data.application_spec]);

  useEffect(() => {
    if (!ready || !freshOriginalMatch || originalSavedKey.current === originalKey) return;
    saveRevision().catch(error => setSaveError(error.message));
    // Persist a baseline that finishes after the initial revision save.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, freshOriginalMatch, originalKey, originalAssessment]);

  const runRewrite = async () => {
    if (!session.sessionId || session.gate !== "gap_review" || session.loading || session.data.running || draftStarting || analysisUnavailable) return;
    const keys = [...selectedAreas];
    setDraftStarting(true);
    setStreamOrder(keys); setStreamed({});
    try {
      await session.advanceStream({ confirmed_gaps: [], sections_to_rewrite: keys, user_additions: instructions },
        (key, text) => setStreamed(previous => ({ ...previous, [key]: (previous[key] || "") + text })));
      setCompare(false); setEditingDraft(false);
    } catch (_) { /* The session hook displays the recoverable error below. */ }
    finally { setDraftStarting(false); }
  };

  useEffect(() => {
    if (session.gate !== "gap_review" || !session.data.analysis || reviewSelection.current === session.sessionId) return;
    reviewSelection.current = session.sessionId;
    setSelectedAreas(session.data.analysis.sections_to_rewrite || []);
  }, [session.gate, session.data.analysis, session.sessionId]);

  const startRedraft = async () => {
    if (!context || !grant || prefilling || !aiPolicyCheck(spec).ai_drafting_allowed || busy) return;
    const originals = normalizeSectionMap(Object.keys(sourceItem?.sections || {}).length ? sourceItem.sections : context.sections);
    if (!Object.keys(originals).length && context.raw_text) originals.proposal = { title: "Proposal", content: context.raw_text };
    if (!Object.values(originals).some(item => item.content?.trim())) { setSetupError("Choose a proposal with text to rewrite."); return; }
    const name = revisionName.trim() || defaultName;
    const revisionContext = { title: name, source_title: sourceTitle, source_proposal_id: sourceItem?.id || null, instructions };
    sourceSnapshot.current = { ...revisionContext, originals, context };
    revisionId.current = null; autosaved.current = null;
    reviewSelection.current = null; setSelectedAreas([]); setEditingDraft(false);
    matchRequest.current += 1; autoMatch.current = null; matchAssessmentRef.current = null;
    setMatchAssessment(null); setMatching(false); setMatchError("");
    originalMatchRequest.current += 1; originalAutoMatch.current = null; originalSavedKey.current = null;
    originalAssessmentRef.current = null; setOriginalAssessment(null); setOriginalMatching(false); setOriginalMatchError("");
    setEdited({}); setStreamed({}); setStreamOrder([]); setCompare(false); setSaveStatus(""); setSaveError("");
    session.reset(); setLaunching(true);
    navigate("/draft/write");
    try {
      const id = await session.start("improve", { ...grant, application_spec: spec, revision_context: revisionContext }, profile || {}, originals);
      navigate(`/draft/write?session=${encodeURIComponent(id)}`, { replace: true });
    } catch (_) { /* Session hook provides details and a back-to-setup action. */ }
    finally { setLaunching(false); }
  };

  const findGrants = async () => {
    try {
      const saved = await saveRevision();
      if (saved) navigate(stageProposalMatch({ ...saved, _type: "draft" }, profile || {}));
    } catch (error) { setSaveError(error.message); }
  };
  const download = async () => {
    setPdfLoading(true);
    try {
      await loadJsPDF();
      createProposalPdf(window.jspdf.jsPDF, { title, agency: effectiveGrant?.agency, organization: profile?.org_name, sections: currentSections, sectionOrder: Object.keys(currentSections) }).save(`${title.replace(/[^a-z0-9 -]/gi, "").slice(0, 100)}.pdf`);
    } catch (_) { setSaveError("Could not export PDF. Please retry."); }
    finally { setPdfLoading(false); }
  };
  const format = kind => {
    const element = textareaRefs.current[activeTab];
    if (!element) return;
    const result = applyFormat(element, kind);
    if (result) setEdited(previous => ({ ...previous, [activeTab]: result.newText }));
  };
  const originals = sourceSnapshot.current?.originals || {};
  const comparisonDiffs = ready ? Object.fromEntries([...new Set([...Object.keys(originals), ...Object.keys(currentSections)])].map(key => {
    const originalText = originals[key]?.content || "";
    const revisedText = currentSections[key]?.content || "";
    const stored = session.data.diffs?.[key];
    const valid = Array.isArray(stored) && stored.filter(token => token.type !== "add").map(token => token.text).join("") === originalText && stored.filter(token => token.type !== "remove").map(token => token.text).join("") === revisedText;
    return [key, valid ? stored : createTextDiff(originalText, revisedText)];
  })) : {};
  const busy = launching || draftStarting || session.loading || Boolean(session.data.running);
  const reviewingGaps = session.gate === "gap_review" && !busy;

  return <div className="draft-workspace"><Nav />
    {!writingPage ? <main className="draft-setup il-form">
      <header><p className="draft-eyebrow">DRAFT ASSISTANT</p><h1>Tailor your proposal to a grant</h1><p>Choose your proposal and target grant. Review what we can find, fill in missing requirements, then redraft.</p></header>
      <section className="draft-card draft-selection" aria-label="Proposal and grant selection">
        <label>Proposal<select aria-label="Proposal" value={proposalId} disabled={busy} onChange={event => { setProposalId(event.target.value); setRevisionName(""); }}>
          <option value="">{proposals.length ? "Choose a saved proposal" : "Use your uploaded proposal"}</option>
          {proposals.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}
        </select></label>
        <label>Target grant<select aria-label="Target grant" value={grantId} disabled={busy} onChange={event => { setGrantId(event.target.value); setGrant(null); setSpec(emptyApplicationSpec()); setRevisionName(""); }}>
          <option value="">Choose a grant</option>
          {grants.map(item => <option key={item.grant_id} value={item.grant_id}>{item.title}</option>)}
          {grantId && !grants.some(item => String(item.grant_id) === String(grantId)) && <option value={grantId}>{grant?.title || "Loading selected grant..."}</option>}
        </select></label>
      </section>
      {!context && <p>Upload a proposal on the <button type="button" onClick={() => navigate("/grants")}>Grants page</button> first, or select a saved proposal.</p>}
      <section className="draft-card" aria-label="Automatic grant prefill">
        <h2>{prefilling ? "Reading the selected grant..." : "From the grant record"}</h2>
        <p>Only information present in the stored grant text can be filled automatically. Exact portal questions, limits, documents and AI policies may be missing; blank fields do not mean the funder has no requirements.</p>
        {prefilling && <button type="button" onClick={() => { prefillRequest.current += 1; setPrefilling(false); }}>Enter requirements manually</button>}
        {prefill && <p role="status">Prefilled {prefill.application_spec?.sections?.length || 0} questions and {prefill.application_spec?.attachments?.length || 0} attachment entries. Review the fields below before redrafting.</p>}
        {(prefill?.evidence || []).map((item, index) => <blockquote key={index}><strong>{item.field}</strong><p>{item.quote}</p></blockquote>)}
        {(prefill?.warnings || []).map((warning, index) => <p key={index}>{warning}</p>)}
        {setupError && <p role="alert">{setupError}</p>}
      </section>
      <ApplicationRequirementsEditor value={spec} onChange={setSpec} grant={grant} collapsible={false} showPrefill={false} disabled={prefilling || busy} existingSections={Object.entries(normalizeSectionMap(sourceItem?.sections || context?.sections)).map(([key, item]) => ({ key, title: item.title || key }))} />
      <section className="draft-card">
        <h2>Your rewrite preferences</h2>
        <label>New draft name<input aria-label="New draft name" value={revisionName || defaultName} onChange={event => setRevisionName(event.target.value)} maxLength={400} /></label>
        <label>Instructions for this rewrite<textarea aria-label="Instructions for this rewrite" value={instructions} onChange={event => setInstructions(event.target.value)} maxLength={2000} rows={4} placeholder="What should we emphasize, avoid or clarify?" /></label>
        <p>The rewrite is saved separately. Your original proposal is preserved.</p>
      </section>
      <div className="draft-start"><button type="button" className="il-primary" disabled={!context || !grant || !grantId || prefilling || busy || !aiPolicyCheck(spec).ai_drafting_allowed} onClick={startRedraft}>Review gaps</button></div>
      {busy && <p>A rewrite is already running. <button onClick={() => navigate(`/draft/write?session=${encodeURIComponent(session.sessionId || "")}`)}>View writing progress</button></p>}
      <AiPrivacyNotice />
    </main> : <main className="draft-writing">
      <header className="draft-writing-header"><div><p className="draft-eyebrow">{ready ? "REVISED PROPOSAL" : reviewingGaps ? "REVIEW BEFORE DRAFTING" : "PREPARING YOUR REVISION"}</p><h1>{title}</h1></div>
        {ready && !busy && <div className="draft-actions">
          <button aria-pressed={!compare && !editingDraft} onClick={() => { setCompare(false); setEditingDraft(false); }}>View draft</button>
          <button aria-pressed={!compare && editingDraft} onClick={() => { setCompare(false); setEditingDraft(true); }}>Edit draft</button>
          <button aria-pressed={compare} onClick={() => { setCompare(true); setEditingDraft(false); }}>Compare versions</button>
          <button onClick={() => saveRevision().catch(error => setSaveError(error.message))}>Save draft</button>
          <button disabled={pdfLoading || !check.can_finalize_text} onClick={download}>Download PDF</button>
          <button className="draft-primary" onClick={findGrants}>Find grants</button>
        </div>}
      </header>
      {reviewingGaps && <>
        <section className="draft-card draft-match" aria-label="Original grant match"><div className="draft-match-heading"><h2>Original match · {effectiveGrant?.title || "Selected grant"}</h2><button disabled={originalMatching} onClick={refreshOriginalMatch}>{originalMatching ? "Checking original…" : "Refresh original match"}</button></div>
          {originalMatching ? <p role="status">Assessing the original proposal before changes…</p> : freshOriginalMatch ? originalAssessment.match ? <><p className="draft-match-score">{originalAssessment.match.similarity_score ?? "—"}<span> / 100</span></p><p>Based on the original proposal, before this revision.</p><p>{originalAssessment.match.match_explanation}</p></> : <p>No original match score is available under the current eligibility filters.</p> : <p>The original proposal's match will appear here before drafting.</p>}
          {originalMatchError && <p role="alert">{originalMatchError}</p>}
        </section>
        <GapSummary analysis={session.data.analysis} />
        {!analysisUnavailable && <section className="draft-card" aria-label="Drafting scope"><h2>Choose the areas to change</h2>
          <p>Only the selected areas and their identified gaps will be edited. Existing tables and unaffected text are retained.</p>
          {(session.data.analysis?.sections_to_rewrite || []).map(key => <label key={key} style={{ display: "flex", alignItems: "center", gap: 10, margin: "10px 0", fontSize: 13 }}><input type="checkbox" checked={selectedAreas.includes(key)} onChange={event => setSelectedAreas(previous => event.target.checked ? [...previous, key] : previous.filter(item => item !== key))} />{getSectionTitle(key, sections[key] || originals[key])}</label>)}
          <label>Additional drafting instructions<textarea aria-label="Additional drafting instructions" rows={3} maxLength={2000} value={instructions} onChange={event => setInstructions(event.target.value)} /></label>
          <div className="draft-start"><button className="draft-primary" disabled={busy || Boolean(session.error)} onClick={runRewrite}>{selectedAreas.length ? "Draft" : "Keep original draft"}</button></div>
        </section>}
      </>}
      {ready && <section className="draft-card draft-match" aria-label="Updated grant match">
        <div className="draft-match-heading"><h2>Updated match · {effectiveGrant?.title || "Selected grant"}</h2><button disabled={matching || busy} onClick={refreshMatch}>{matching ? "Updating match…" : "Refresh match"}</button></div>
        {matching ? <p role="status">Checking the revised proposal against this grant…</p> : freshMatch ? matchAssessment.match ? <>
          <p className="draft-match-score">{matchAssessment.match.similarity_score ?? "—"}<span> / 100</span></p>
          {freshOriginalMatch && originalAssessment.match && <p>Original proposal: <strong>{originalAssessment.match.similarity_score} / 100</strong></p>}
          <p>{matchAssessment.match.score_method === "semantic_similarity" || matchAssessment.match.fit_level === "unknown" ? "Semantic similarity estimate" : "AI project-fit estimate"} · based on the revised proposal.</p>
          <p>{matchAssessment.match.match_explanation}</p>
          {matchAssessment.match.application_tip && <p><strong>Application tip:</strong> {matchAssessment.match.application_tip}</p>}
          {matchAssessment.match.eligibility_check?.status && <p>Eligibility check: {matchAssessment.match.eligibility_check.status.replace(/_/g, " ")}</p>}
          <p>This estimate does not verify eligibility or predict funding success.</p>
        </> : <p>No match score is available for the selected grant under the current eligibility filters.</p> : <p>{matchAssessment ? "The proposal or application details changed since this score was calculated. Refresh the match to assess the current version." : "The revised proposal will be checked against the selected grant."}</p>}
        {matchError && <p role="alert">{matchError}</p>}
      </section>}
      {analysisUnavailable && <section role="alert" className="draft-card"><p>Gap analysis could not be completed. No automatic rewrite was started.</p><button onClick={() => navigate("/draft")}>Back to setup</button></section>}
      {!ready && !busy && !session.sessionId && !searchParams.get("session") ? <section className="draft-card"><p>No active rewrite is selected.</p><button onClick={() => navigate("/draft")}>Back to setup</button></section> : !ready && !reviewingGaps && !analysisUnavailable && <section aria-label="Writing progress" className="draft-progress"><span className="draft-spinner" />{session.progress || (session.gate === "gap_review" ? "Drafting the selected areas..." : "Analyzing your proposal and the grant requirements...")}</section>}
      {!ready && !reviewingGaps && streamOrder.map(key => <article className="draft-paper" key={key}><h2>{getSectionTitle(key)}</h2><div aria-live="polite" style={{ whiteSpace: "pre-wrap" }}>{streamed[key] || "Preparing this section..."}</div></article>)}
      {session.error && <section role="alert" className="draft-card"><p>{session.error}</p><button onClick={session.refresh} disabled={busy}>Check saved session status</button>{session.gate === "gap_review" && !busy && <button onClick={runRewrite}>Retry rewrite</button>}<button onClick={() => navigate("/draft")}>Back to setup</button></section>}
      {ready && !busy && <>
        <p className="draft-save-status" role="status">{saveStatus || "Saving the new revision..."}</p>
        {compare && <div className="draft-change-legend" aria-label="Change colors"><span className="draft-removed">Red: removed text</span><span className="draft-added">Green: added text</span></div>}
        {compare ? <section className="draft-comparison" aria-label="Proposal comparison">
          <article className="draft-paper"><h2>Original proposal</h2>{Object.entries(originals).map(([key, item]) => <section key={key}><h3>{getSectionTitle(key, item)}</h3><FormattedProposalContent tokens={comparisonDiffs[key]} fallback={item.content || ""} variant="original" sectionTitle={getSectionTitle(key, item)} /></section>)}</article>
          <article className="draft-paper"><h2>Revised proposal</h2>{Object.entries(currentSections).map(([key, item]) => {
            return <section key={key}><h3>{getSectionTitle(key, item)}</h3><CompareEditableSection tokens={comparisonDiffs[key]} value={item.content} sectionTitle={getSectionTitle(key, item)} onChange={text => setEdited(previous => ({ ...previous, [key]: text }))} /></section>;
          })}</article>
        </section> : editingDraft ? <>
          <div className="draft-format"><button onClick={() => format("bold")}>Bold</button><button onClick={() => format("h2")}>Heading</button><button onClick={() => format("bullet")}>List</button><button onClick={() => format("table")}>Table</button></div>
          {Object.entries(currentSections).map(([key, item]) => <article className="draft-paper" key={key}><h2>{getSectionTitle(key, item)}</h2><textarea aria-label={`Edit ${getSectionTitle(key, item)}`} ref={element => { textareaRefs.current[key] = element; }} onFocus={() => setActiveTab(key)} value={item.content} onChange={event => setEdited(previous => ({ ...previous, [key]: event.target.value }))} /></article>)}
        </> : <section aria-label="Revised proposal preview">{Object.entries(currentSections).map(([key, item]) => <article className="draft-paper" key={key}><h2>{getSectionTitle(key, item)}</h2><FormattedProposalContent tokens={comparisonDiffs[key]} fallback={item.content || ""} variant="revised" sectionTitle={getSectionTitle(key, item)} /></article>)}</section>}
        <ApplicationReview spec={spec} sections={currentSections} onChange={setSpec} onSave={saveChecklist} />
      </>}
      {saveError && <p role="alert">{saveError}</p>}
      <AiPrivacyNotice />
    </main>}
  </div>;
}
