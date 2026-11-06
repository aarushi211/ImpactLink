import { useState } from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import StateSelect from "./StateSelect";

function Picker({ initial = "" }) {
  const [value, setValue] = useState(initial);
  return <><StateSelect value={value} onChange={setValue} /><output data-testid="states">{value}</output></>;
}

test("states are explicit dropdown selections and support more than one location", () => {
  render(<Picker />);
  expect(screen.getByTestId("states")).toHaveTextContent("");
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "CA" } });
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "NY" } });
  expect(screen.getByTestId("states")).toHaveTextContent("CA, NY");
  fireEvent.click(screen.getByRole("button", { name: "Remove CA" }));
  expect(screen.getByTestId("states")).toHaveTextContent("NY");
});

test("existing full state names normalize without offering duplicate choices", () => {
  render(<Picker initial="California, CA" />);
  expect(screen.getAllByRole("button", { name: "Remove CA" })).toHaveLength(1);
  expect(screen.getByRole("combobox")).toHaveValue("CA");
  expect(screen.getAllByRole("option", { name: "California" })).toHaveLength(1);
});
