import { render, screen } from "@testing-library/react";
import GrantDetail from "./GrantDetail";
import api from "../services/api";
jest.mock("react-router-dom", () => ({ useParams: () => ({ id: "190509" }), useNavigate: () => jest.fn() }), { virtual: true });
jest.mock("../hooks/useGrants", () => () => ({ grants: [], loading: false }));
jest.mock("../services/api", () => ({ __esModule: true, default: { get: jest.fn() } }));
jest.mock("../components", () => ({ Nav: () => null, FitBadge: () => null, ScoreRing: () => null }));

test("a grant detail link loads from the database without browser-cached matches", async () => {
  api.get.mockResolvedValue({ data: { grant_id: "190509", title: "Urban Streams Restoration", agency: "Water Resources", description: "Restore urban creeks", eligibility: [] } });
  render(<GrantDetail />);
  expect(await screen.findByText("Urban Streams Restoration")).toBeInTheDocument();
  expect(api.get).toHaveBeenCalledWith("/api/grants/190509");
});
