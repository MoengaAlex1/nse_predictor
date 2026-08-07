import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ValuationPanel } from "./ValuationPanel";
import type { CompanyDoc, FinancialsDoc } from "../../types";

vi.mock("../../lib/firebase", () => ({ app: {}, db: {}, auth: {} }));

const mockCompany: CompanyDoc = {
  id: "COOP_NR",
  ticker: "COOP.NR",
  name: "Co-operative Bank",
  short: "COOP",
  sector: "Banking",
  color: "#34d399",
  icon: "🏦",
  csv: "COOP_NR_raw.csv",
  current_price: 13.5,
  change_pct_today: 1.2,
  signal: "BUY",
  price_history: [],
  price_preview: [],
  price_date: "2026-07-24",
  last_updated: "2026-07-24",
};

const mockFinancials: FinancialsDoc = {
  annual: [
    {
      period: "FY2024",
      period_end: "2024-12-31",
      period_type: "annual",
      announcement_date: "2025-03-15",
      revenue_kes_mn: 48000,
      net_income_kes_mn: 9600,
      eps: 1.63,
      bvps: 12.85,
    },
    {
      period: "FY2023",
      period_end: "2023-12-31",
      period_type: "annual",
      announcement_date: "2024-03-10",
      revenue_kes_mn: 44000,
      net_income_kes_mn: 8500,
      eps: 1.41,
      bvps: 12.2,
    },
  ],
  dividends: [
    {
      announcement_date: "2025-04-01",
      ex_date: "2025-06-01",
      payment_date: "2025-07-01",
      amount_kes: 0.55,
      type: "final",
    },
  ],
  corporate_actions: [],
  announcements: [],
};

describe("ValuationPanel", () => {
  it("renders EPS from most recent annual result", () => {
    render(<ValuationPanel company={mockCompany} financials={mockFinancials} fundamentals={null} />);
    expect(screen.getByText("1.63")).toBeInTheDocument();
  });

  it("renders P/E computed from current_price / eps", () => {
    render(<ValuationPanel company={mockCompany} financials={mockFinancials} fundamentals={null} />);
    // 13.50 / 1.63 ≈ 8.3×
    expect(screen.getByText(/8\.[0-9]+×/)).toBeInTheDocument();
  });

  it("switches to Income tab on click", async () => {
    const user = userEvent.setup();
    render(<ValuationPanel company={mockCompany} financials={mockFinancials} fundamentals={null} />);
    await user.click(screen.getByRole("button", { name: /Income/i }));
    expect(screen.getByText(/Net Income/i)).toBeInTheDocument();
  });

  it("switches to Dividends tab on click", async () => {
    const user = userEvent.setup();
    render(<ValuationPanel company={mockCompany} financials={mockFinancials} fundamentals={null} />);
    await user.click(screen.getByRole("button", { name: /Dividends/i }));
    expect(screen.getByText(/0\.55/)).toBeInTheDocument();
  });

  it("shows sector comparison row for known sector", () => {
    render(<ValuationPanel company={mockCompany} financials={mockFinancials} fundamentals={null} />);
    expect(screen.getByText(/Banking sector median/i)).toBeInTheDocument();
  });

  it("renders nothing when financials have no annual results", () => {
    const { container } = render(
      <ValuationPanel
        company={mockCompany}
        financials={{ annual: [], dividends: [], corporate_actions: [] }}
        fundamentals={null}
      />,
    );
    expect(container.firstChild).toBeNull();
  });
});
