import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NewsPanel } from "./NewsPanel";
import type { FinancialsDoc, NewsItem } from "../../types";

vi.mock("../../lib/firebase", () => ({ app: {}, db: {}, auth: {} }));

const mockFinancials: FinancialsDoc = {
  annual: [], dividends: [], corporate_actions: [],
  announcements: [
    { date: "2026-07-24", type: "financial_result", title: "H1 2026 Interim Results", url: "https://nse.co.ke/filing1.pdf" },
    { date: "2026-06-15", type: "dividend",         title: "Final dividend KES 0.55 declared", url: "https://nse.co.ke/filing2.pdf" },
    { date: "2026-04-02", type: "corporate_action", title: "CBK grants approval for digital credit", url: "" },
  ],
};

const scraperItems: NewsItem[] = [
  { id: "s1", date: "2026-07-20", title: "New branch opening in Mombasa", category: "general", body: "Full body text here.", url: null, source: "scraper" },
];

describe("NewsPanel", () => {
  it("renders announcement titles", () => {
    render(<NewsPanel financials={mockFinancials} newsItems={[]} />);
    expect(screen.getByText(/H1 2026 Interim Results/i)).toBeInTheDocument();
    expect(screen.getByText(/Final dividend KES 0.55/i)).toBeInTheDocument();
  });

  it("renders external link for announcement with URL", () => {
    render(<NewsPanel financials={mockFinancials} newsItems={[]} />);
    const links = screen.getAllByRole("link", { name: /View NSE filing/i });
    expect(links[0]).toHaveAttribute("target", "_blank");
    expect(links[0]).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("shows Read more toggle for item without URL", () => {
    render(<NewsPanel financials={mockFinancials} newsItems={scraperItems} />);
    expect(screen.getByText(/Read more/i)).toBeInTheDocument();
  });

  it("expands inline body on Read more click", async () => {
    const user = userEvent.setup();
    render(<NewsPanel financials={mockFinancials} newsItems={scraperItems} />);
    const btn = screen.getByText(/Read more/i);
    await user.click(btn);
    expect(screen.getByText("Full body text here.")).toBeInTheDocument();
  });

  it("filters by category tab", async () => {
    const user = userEvent.setup();
    render(<NewsPanel financials={mockFinancials} newsItems={[]} />);
    await user.click(screen.getByRole("button", { name: /Dividends/i }));
    expect(screen.getByText(/Final dividend KES 0.55/i)).toBeInTheDocument();
    expect(screen.queryByText(/H1 2026 Interim Results/i)).not.toBeInTheDocument();
  });

  it("deduplicates items with same date+title prefix", () => {
    const duplicate: NewsItem = { id: "d1", date: "2026-07-24", title: "H1 2026 Interim Results — more detail", category: "earnings", body: null, url: null, source: "scraper" };
    render(<NewsPanel financials={mockFinancials} newsItems={[duplicate]} />);
    const matches = screen.getAllByText(/H1 2026 Interim Results/i);
    expect(matches).toHaveLength(1);
  });
});
