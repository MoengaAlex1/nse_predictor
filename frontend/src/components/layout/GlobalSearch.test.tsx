import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

const mockCompany = {
  // Post primary-key refactor these two differ: `id` is the Firestore doc id,
  // `ticker` is a display alias. Keep them distinct so the routing assertions
  // below actually prove which one each route receives.
  id: "SCOM", ticker: "SCOM.NR", short: "Safaricom", color: "#22c55e",
  icon: "📱", name: "Safaricom PLC", sector: "Telecommunication and Technology",
  current_price: 14.5, change_pct_today: 3.2, signal: "BUY" as const,
  price_history: [], price_preview: [], price_date: null, last_updated: null, csv: "",
};

const mockNavigate = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock("../../hooks/useCompanies", () => ({
  useCompanies: () => ({ data: [mockCompany], isLoading: false }),
}));

import { GlobalSearch } from "./GlobalSearch";

const wrap = (ui: React.ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>);

describe("GlobalSearch", () => {
  beforeEach(() => mockNavigate.mockClear());

  it("renders a search icon button initially", () => {
    wrap(<GlobalSearch />);
    expect(screen.getByTitle("Search companies")).toBeInTheDocument();
  });

  it("expands to an input when the icon is clicked", async () => {
    const user = userEvent.setup();
    wrap(<GlobalSearch />);
    await user.click(screen.getByTitle("Search companies"));
    expect(screen.getByPlaceholderText("Search companies…")).toBeInTheDocument();
  });

  it("shows matching results when query matches a ticker", async () => {
    const user = userEvent.setup();
    wrap(<GlobalSearch />);
    await user.click(screen.getByTitle("Search companies"));
    await user.type(screen.getByPlaceholderText("Search companies…"), "SCOM");
    expect(screen.getByText("Safaricom PLC")).toBeInTheDocument();
  });

  it("shows no match message for unknown query", async () => {
    const user = userEvent.setup();
    wrap(<GlobalSearch />);
    await user.click(screen.getByTitle("Search companies"));
    await user.type(screen.getByPlaceholderText("Search companies…"), "ZZZZ");
    expect(screen.getByText(/No companies match/i)).toBeInTheDocument();
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();
    wrap(<GlobalSearch />);
    await user.click(screen.getByTitle("Search companies"));
    await user.keyboard("{Escape}");
    expect(screen.queryByPlaceholderText("Search companies…")).not.toBeInTheDocument();
  });

  it("navigates to company on ArrowDown + Enter", async () => {
    const user = userEvent.setup();
    wrap(<GlobalSearch />);
    await user.click(screen.getByTitle("Search companies"));
    await user.type(screen.getByPlaceholderText("Search companies…"), "SCOM");
    await user.keyboard("{ArrowDown}");
    await user.keyboard("{Enter}");
    expect(mockNavigate).toHaveBeenCalledWith("/company/SCOM");
  });

  it("navigates to the doc id, not the display ticker, when a result is clicked", async () => {
    const user = userEvent.setup();
    wrap(<GlobalSearch />);
    await user.click(screen.getByTitle("Search companies"));
    await user.type(screen.getByPlaceholderText("Search companies…"), "SCOM");
    await user.click(screen.getByText("Safaricom PLC"));
    expect(mockNavigate).toHaveBeenCalledWith("/company/SCOM");
  });

  it("still routes the chart variant on the display ticker", async () => {
    const user = userEvent.setup();
    wrap(<GlobalSearch targetRoute="chart" />);
    await user.click(screen.getByTitle("Search companies"));
    await user.type(screen.getByPlaceholderText("Search companies…"), "SCOM");
    await user.click(screen.getByText("Safaricom PLC"));
    expect(mockNavigate).toHaveBeenCalledWith("/chart/SCOM.NR");
  });
});
