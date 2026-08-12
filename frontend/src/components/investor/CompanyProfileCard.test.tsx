import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CompanyProfileCard } from "./CompanyProfileCard";
import type { CompanyDoc } from "../../types";

const BASE_COMPANY: CompanyDoc = {
  id: "COOP.NR",
  ticker: "COOP.NR",
  name: "Co-operative Bank",
  short: "COOP",
  sector: "Banking",
  color: "#34d399",
  icon: "🏦",
  csv: "COOP_NR_raw.csv",
  description:
    "Co-operative Bank of Kenya is jointly owned by Kenya's vast cooperative movement and retail shareholders, making it one of the country's top-three banks by deposits. It is known for its strong rural branch network.",
  current_price: 12.5,
  change_pct_today: 0.8,
  signal: "BUY",
  price_history: [],
  price_preview: [],
  price_date: "2026-07-24",
  last_updated: "2026-07-24",
};

const SHORT_DESC_COMPANY: CompanyDoc = {
  ...BASE_COMPANY,
  ticker: "BOC.NR",
  description: "Short description.",
};

const NO_DESC_COMPANY: CompanyDoc = { ...BASE_COMPANY, description: undefined };

describe("CompanyProfileCard", () => {
  it("renders the company name and sector", () => {
    render(<CompanyProfileCard company={BASE_COMPANY} />);
    expect(screen.getByText("Co-operative Bank")).toBeInTheDocument();
    // Sector appears inline with the profile subheader ("About COOP · Banking")
    // when there's no IR-extracted industry to prefer.
    expect(screen.getByText(/Banking/)).toBeInTheDocument();
  });

  it("shows CEO and headquarters from static profile", () => {
    render(<CompanyProfileCard company={BASE_COMPANY} />);
    expect(screen.getByText("Dr. Gideon Muriuki")).toBeInTheDocument();
    expect(screen.getByText("Nairobi, Kenya")).toBeInTheDocument();
  });

  it("shows em-dash for null profile fields", () => {
    render(<CompanyProfileCard company={SHORT_DESC_COMPANY} />);
    // BOC.NR has ceo: null
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThan(0);
  });

  it("truncates description longer than TRUNCATE_LEN chars and shows Read more button", () => {
    const long = "A".repeat(400);
    render(<CompanyProfileCard company={{ ...BASE_COMPANY, description: long }} />);
    expect(screen.getByRole("button", { name: /read more/i })).toBeInTheDocument();
    expect(screen.queryByText(long)).not.toBeInTheDocument();
  });

  it("expands description when Read more is clicked", async () => {
    const user = userEvent.setup();
    const long = "A".repeat(400);
    render(<CompanyProfileCard company={{ ...BASE_COMPANY, description: long }} />);
    await user.click(screen.getByRole("button", { name: /read more/i }));
    expect(screen.getByText(long)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /show less/i })).toBeInTheDocument();
  });

  it("renders without crashing when description is undefined", () => {
    render(<CompanyProfileCard company={NO_DESC_COMPANY} />);
    expect(screen.getByText("Co-operative Bank")).toBeInTheDocument();
  });
});
