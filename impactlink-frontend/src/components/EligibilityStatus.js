const labels = {
  potentially_eligible: "Basic eligibility checks passed",
  unverified: "Eligibility needs confirmation",
  ineligible: "Does not meet a recorded requirement",
};

export default function EligibilityStatus({ result, detailed = false }) {
  if (!result) return null;
  return (
    <div style={{ marginTop: 8, color: result.status === "ineligible" ? "#f87171" : result.status === "unverified" ? "#facc15" : "#4ade80", fontSize: 12 }}>
      <span>{labels[result.status] || labels.unverified}</span>
      {detailed && <ul style={{ paddingLeft: 18, lineHeight: 1.6 }}>{(result.checks || []).map(check => (
        <li key={check.criterion}>{check.message}</li>
      ))}</ul>}
    </div>
  );
}
