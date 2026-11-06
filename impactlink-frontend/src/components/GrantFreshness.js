export default function GrantFreshness({ grant, link = false }) {
  const source = { california: "California Grants Portal", grants_gov: "Grants.gov" }[grant.source];
  const checked = grant.last_verified_at ? new Date(grant.last_verified_at) : null;
  const validDate = checked && !Number.isNaN(checked.getTime());
  if (!source) return null;
  return <p style={{ color: "var(--text-muted)", fontSize: 12, margin: "8px 0" }}>
    {link && /^https:\/\//i.test(grant.source_url || "")
      ? <a href={grant.source_url} target="_blank" rel="noopener noreferrer">{source}</a> : source}
    {validDate ? ` · Checked ${checked.toLocaleDateString()}` : " · Not yet verified"}
  </p>;
}
