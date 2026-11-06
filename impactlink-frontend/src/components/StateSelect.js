import "./FormControls.css";
const states = [["AL", "Alabama"], ["AK", "Alaska"], ["AZ", "Arizona"], ["AR", "Arkansas"], ["CA", "California"], ["CO", "Colorado"], ["CT", "Connecticut"], ["DE", "Delaware"], ["DC", "District of Columbia"], ["FL", "Florida"], ["GA", "Georgia"], ["HI", "Hawaii"], ["ID", "Idaho"], ["IL", "Illinois"], ["IN", "Indiana"], ["IA", "Iowa"], ["KS", "Kansas"], ["KY", "Kentucky"], ["LA", "Louisiana"], ["ME", "Maine"], ["MD", "Maryland"], ["MA", "Massachusetts"], ["MI", "Michigan"], ["MN", "Minnesota"], ["MS", "Mississippi"], ["MO", "Missouri"], ["MT", "Montana"], ["NE", "Nebraska"], ["NV", "Nevada"], ["NH", "New Hampshire"], ["NJ", "New Jersey"], ["NM", "New Mexico"], ["NY", "New York"], ["NC", "North Carolina"], ["ND", "North Dakota"], ["OH", "Ohio"], ["OK", "Oklahoma"], ["OR", "Oregon"], ["PA", "Pennsylvania"], ["RI", "Rhode Island"], ["SC", "South Carolina"], ["SD", "South Dakota"], ["TN", "Tennessee"], ["TX", "Texas"], ["UT", "Utah"], ["VT", "Vermont"], ["VA", "Virginia"], ["WA", "Washington"], ["WV", "West Virginia"], ["WI", "Wisconsin"], ["WY", "Wyoming"]];
export default function StateSelect({ value = "", onChange, disabled, label = "Project U.S. states" }) {
  const raw = String(value).split(/[,;|]/).map(item => item.trim()).filter(Boolean);
  const selected = [...new Set(raw.map(item => states.find(([code, name]) => [code.toLowerCase(), name.toLowerCase()].includes(item.toLowerCase()))?.[0] || item))];
  const current = selected[selected.length - 1] || "";
  return <div className="il-state-select">
    <select aria-label={label} value={current} disabled={disabled} onChange={event => { if (event.target.value && !selected.includes(event.target.value)) onChange([...selected, event.target.value].join(", ")); }}>
      <option value="">{selected.length ? "Add another state..." : "Select a state (or leave unspecified)"}</option>
      {states.filter(([code]) => !selected.includes(code) || code === current).map(([code, name]) => <option key={code} value={code}>{name}</option>)}
    </select>
    <div className="il-state-tags">{selected.map(code => <button type="button" disabled={disabled} key={code} aria-label={`Remove ${code}`} onClick={() => onChange(selected.filter(item => item !== code).join(", "))}>{states.find(([id]) => id === code)?.[1] || code} <span aria-hidden="true">x</span></button>)}</div>
  </div>;
}
