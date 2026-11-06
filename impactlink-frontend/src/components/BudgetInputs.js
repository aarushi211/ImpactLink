import "./FormControls.css";
let nextLine = 0;
const lineId = () => `cost-${Date.now()}-${++nextLine}`;
export const emptyCostInputs = () => ({ staff: [], direct_costs: [], indirect: { method: "unconfirmed", rate_pct: 0, base: "MTDC", reference: "", de_minimis_eligible: false, funder_cap_pct: null, funder_cap_base: "MTDC" }, unallowable_kinds: [] });
const kinds = { supplies: "Materials & supplies", services: "Services / contractors", travel: "Travel", equipment: "Equipment", capital: "Capital expenditures", rental: "Rental costs", tuition: "Tuition remission", scholarships: "Scholarships / fellowships", patient_care: "Patient care", participant_support: "Participant support", subaward: "Subaward" };
const style = { width: "100%", boxSizing: "border-box", padding: "9px 12px", borderRadius: 8, background: "#111120", color: "#ddd", border: "1px solid var(--border)" };

export default function BudgetInputs({ value, onChange, disabled }) {
  const update = (group, id, field, next) => onChange({ ...value, [group]: value[group].map(row => row.id === id ? { ...row, [field]: next } : row) });
  const remove = (group, id) => onChange({ ...value, [group]: value[group].filter(row => row.id !== id) });
  const indirect = (field, next) => onChange({ ...value, indirect: { ...value.indirect, [field]: next } });
  const input = (label, current, change, props = {}) => <label style={{ fontSize: 12, color: "#aaa" }}>{label}<input aria-label={label} style={style} value={current ?? ""} onChange={event => change(event.target.value)} {...props} /></label>;
  return <fieldset className="il-form" disabled={disabled} style={{ border: 0, borderTop: "1px solid var(--border)", padding: "20px 0 0", margin: "24px 0 0" }}>
    <legend style={{ color: "#999", fontSize: 11, fontWeight: 700, letterSpacing: ".06em", textTransform: "uppercase" }}>Cost assumptions</legend>
    <p style={{ color: "#aaa", fontSize: 12, lineHeight: 1.6 }}>Enter actual or researched salary and unit-cost estimates. FTE is each person's share of full-time effort. Fringe applies to project salary. Costs are calculated without filling the grant ceiling.</p>
    <h4 style={{ color: "#ddd" }}>Staff and fringe</h4>
    {value.staff.map((row, index) => <div key={row.id} style={{ borderBottom: "1px solid var(--border)", paddingBottom: 12, marginBottom: 12 }}>
      <div className="il-form-grid">
        {input(`Role ${index + 1}`, row.role, next => update("staff", row.id, "role", next))}
        {input(`Headcount ${index + 1}`, row.headcount, next => update("staff", row.id, "headcount", next === "" ? "" : Number(next)), { type: "number", min: 1, step: 1 })}
        {input(`Annual salary per person ${index + 1}`, row.annual_salary, next => update("staff", row.id, "annual_salary", next), { type: "number", min: 0, step: "0.01" })}
        {input(`FTE per person ${index + 1}`, row.fte_per_person, next => update("staff", row.id, "fte_per_person", next), { type: "number", min: "0.01", max: 1, step: "0.01" })}
        {input(`Project months ${index + 1}`, row.months, next => update("staff", row.id, "months", next), { type: "number", min: "0.01", max: 120, step: "0.5" })}
        {input(`Fringe rate (%) ${index + 1}`, row.fringe_rate_pct, next => update("staff", row.id, "fringe_rate_pct", next), { type: "number", min: 0, max: 100, step: "0.01" })}
      </div>
      <button onClick={() => remove("staff", row.id)} style={{ marginTop: 8 }}>Remove role {index + 1}</button>
    </div>)}
    <button onClick={() => onChange({ ...value, staff: [...value.staff, { id: lineId(), role: "", headcount: 1, annual_salary: "", fte_per_person: "1", months: "12", fringe_rate_pct: "0" }] })}>Add staff role</button>
    <h4 style={{ color: "#ddd" }}>Non-personnel direct costs</h4>
    {value.direct_costs.map((row, index) => <div key={row.id} style={{ borderBottom: "1px solid var(--border)", paddingBottom: 12, marginBottom: 12 }}>
      <div className="il-form-grid">
        {input(`Cost description ${index + 1}`, row.description, next => update("direct_costs", row.id, "description", next))}
        <label style={{ color: "#aaa", fontSize: 12 }}>Cost type<select aria-label={`Cost type ${index + 1}`} style={style} value={row.kind} onChange={event => {
          const kind = event.target.value;
          onChange({ ...value, direct_costs: value.direct_costs.map(item => item.id === row.id ? { ...item, kind, subaward_id: "", prior_subaward_amount: 0 } : item) });
        }}>{Object.entries(kinds).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
        {input(`Quantity ${index + 1}`, row.quantity, next => update("direct_costs", row.id, "quantity", next), { type: "number", min: "0.01", step: "0.01" })}
        {input(`Unit cost ${index + 1}`, row.unit_cost, next => update("direct_costs", row.id, "unit_cost", next), { type: "number", min: 0, step: "0.01" })}
        {row.kind === "subaward" && <>
          {input(`Subaward ID ${index + 1}`, row.subaward_id, next => update("direct_costs", row.id, "subaward_id", next))}
          {input(`Prior subaward amount ${index + 1}`, row.prior_subaward_amount, next => update("direct_costs", row.id, "prior_subaward_amount", next), { type: "number", min: 0, step: "0.01" })}
        </>}
      </div>
      <label style={{ color: "#aaa", display: "block", fontSize: 12, marginTop: 8 }}><input type="checkbox" checked={row.optional} onChange={event => update("direct_costs", row.id, "optional", event.target.checked)} />Optional activity; may be offered as a scope reduction</label>
      <button onClick={() => remove("direct_costs", row.id)} style={{ marginTop: 8 }}>Remove cost {index + 1}</button>
    </div>)}
    <button onClick={() => onChange({ ...value, direct_costs: [...value.direct_costs, { id: lineId(), description: "", kind: "services", quantity: "1", unit_cost: "", optional: false, subaward_id: "", prior_subaward_amount: 0 }] })}>Add direct cost</button>
    <h4 style={{ color: "#ddd" }}>Indirect costs</h4>
    <label style={{ color: "#aaa", fontSize: 12 }}>Rate method<select aria-label="Indirect rate method" style={style} value={value.indirect.method} onChange={event => {
      const method = event.target.value;
      onChange({ ...value, indirect: { ...value.indirect, method, rate_pct: method === "de_minimis" ? 15 : 0, base: method === "de_minimis" ? "MTDC" : value.indirect.base, de_minimis_eligible: false } });
    }}>
      <option value="unconfirmed">Not confirmed yet</option><option value="none">No indirect costs requested</option><option value="funder">Funder-defined rate</option><option value="negotiated">Negotiated rate (NICRA)</option><option value="de_minimis">Federal de minimis (up to 15% MTDC)</option>
    </select></label>
    {!["none", "unconfirmed"].includes(value.indirect.method) && <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 10, marginTop: 10 }}>
      {input("Indirect rate (%)", value.indirect.rate_pct, next => indirect("rate_pct", next), { type: "number", min: 0, max: value.indirect.method === "de_minimis" ? 15 : 100, step: "0.01" })}
      <label style={{ color: "#aaa", fontSize: 12 }}>Rate base<select aria-label="Indirect rate base" style={style} value={value.indirect.base} disabled={value.indirect.method === "de_minimis"} onChange={event => indirect("base", event.target.value)}><option value="MTDC">Modified total direct costs (MTDC)</option><option value="TDC">Total direct costs (TDC)</option></select></label>
    </div>}
    {value.indirect.method === "de_minimis" && <label style={{ color: "#aaa", fontSize: 12, display: "block", marginTop: 10 }}><input type="checkbox" checked={value.indirect.de_minimis_eligible} onChange={event => indirect("de_minimis_eligible", event.target.checked)} />I confirmed this federal award permits de minimis and this organization qualifies without a current negotiated indirect rate.</label>}
    {["funder", "negotiated"].includes(value.indirect.method) && input("Rate agreement / funder rule reference", value.indirect.reference, next => indirect("reference", next))}
    <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 10, marginTop: 10 }}>
      {input("Funder indirect cap (%) — blank if unconfirmed", value.indirect.funder_cap_pct, next => indirect("funder_cap_pct", next === "" ? null : next), { type: "number", min: 0, max: 99.99, step: "0.01" })}
      <label style={{ color: "#aaa", fontSize: 12 }}>Cap base<select aria-label="Funder cap base" style={style} value={value.indirect.funder_cap_base} onChange={event => indirect("funder_cap_base", event.target.value)}><option value="MTDC">MTDC</option><option value="TDC">Total direct costs</option><option value="total_cost">Total project cost including indirect</option></select></label>
    </div>
    <p style={{ color: "#aaa", fontSize: 12, lineHeight: 1.6 }}>MTDC excludes equipment, capital, rental, tuition, scholarships, patient care and participant support. Only the first $50,000 per subaward is included, accounting for prior amounts. Use the classification and base required by the award or rate agreement; salaries and fringe are not legal wage checks.</p>
    <label style={{ color: "#aaa", fontSize: 12 }}>Funder-prohibited cost types (select only confirmed exclusions)<select multiple aria-label="Funder-prohibited cost types" style={style} value={value.unallowable_kinds} onChange={event => onChange({ ...value, unallowable_kinds: Array.from(event.target.selectedOptions, option => option.value) })}>{Object.entries(kinds).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
  </fieldset>;
}
