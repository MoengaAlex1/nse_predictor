import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Companies } from "./Companies";
import * as useCompaniesModule from "../hooks/useCompanies";
import type { CompanyDoc } from "../types";

vi.mock("../hooks/useCompanies");
vi.mock("../lib/auth", () => ({ initAuthListener: vi.fn(() => vi.fn()), logout: vi.fn() }));
vi.mock("../lib/firebase", () => ({ app: {}, db: {}, auth: {} }));
vi.mock("../store/useAuthStore", () => ({
  useAuthStore: vi.fn(() => ({ user: null, loading: false })),
}));

const mockCompanies: CompanyDoc[] = [
  {
    id: "SCOM_NR",
    ticker: "SCOM.NR",
    name: "Safaricom PLC",
    short: "SCOM",
    sector: "Telecom",
    color: "#38bdf8",
    icon: "📱",
    csv: "SCOM_NR_raw.csv",
    current_price: 33.05,
    change_pct_today: 1.2,
    signal: "BUY",
    price_preview: [],
    last_updated: "2026-07-15",
  },
  {
    id: "EQTY_NR",
    ticker: "EQTY.NR",
    name: "Equity Group Holdings",
    short: "EQTY",
    sector: "Banking",
    color: "#a78bfa",
    icon: "🏦",
    csv: "EQTY_NR_raw.csv",
    current_price: 55.0,
    change_pct_today: -0.5,
    signal: "HOLD",
    price_preview: [],
    last_updated: "2026-07-15",
  },
];

function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Companies page", () => {
  it("renders all companies when data loads", () => {
    vi.mocked(useCompaniesModule.useCompanies).mockReturnValue({
      data: mockCompanies,
      isLoading: false,
      isError: false,
    } as any);

    render(<Companies />, { wrapper: Wrapper });
    expect(screen.getByText("Safaricom PLC")).toBeInTheDocument();
    expect(screen.getByText("Equity Group Holdings")).toBeInTheDocument();
  });

  it("filters companies by search text", async () => {
    vi.mocked(useCompaniesModule.useCompanies).mockReturnValue({
      data: mockCompanies,
      isLoading: false,
      isError: false,
    } as any);

    const user = userEvent.setup();
    render(<Companies />, { wrapper: Wrapper });

    const input = screen.getByPlaceholderText("Search companies...");
    await user.type(input, "safar");

    expect(screen.getByText("Safaricom PLC")).toBeInTheDocument();
    expect(screen.queryByText("Equity Group Holdings")).not.toBeInTheDocument();
  });

  it("shows spinner while loading", () => {
    vi.mocked(useCompaniesModule.useCompanies).mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    } as any);

    render(<Companies />, { wrapper: Wrapper });
    expect(screen.queryByText("Safaricom PLC")).not.toBeInTheDocument();
  });
});
