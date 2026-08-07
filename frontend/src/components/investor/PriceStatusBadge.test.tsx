import { render, screen } from "@testing-library/react";
import { PriceStatusBadge } from "./PriceStatusBadge";

describe("PriceStatusBadge", () => {
  it("labels a live in-session price as provisional", () => {
    render(
      <PriceStatusBadge status="provisional" statusDate="2026-08-07" asOf="13:00" />,
    );
    const badge = screen.getByTestId("price-status-badge");
    expect(badge).toHaveAttribute("data-status", "provisional");
    expect(screen.getByText("Provisional")).toBeInTheDocument();
  });

  it("shows the snapshot time so the price is not mistaken for a close", () => {
    render(
      <PriceStatusBadge status="provisional" statusDate="2026-08-07" asOf="13:00" />,
    );
    expect(screen.getByText("13:00")).toBeInTheDocument();
    expect(screen.getByTestId("price-status-badge").title).toMatch(/as of 13:00 EAT/);
  });

  it("explains that a provisional price is not yet settled", () => {
    render(<PriceStatusBadge status="provisional" statusDate="2026-08-07" />);
    expect(screen.getByTestId("price-status-badge").title).toMatch(/not settled/i);
    expect(screen.getByTestId("price-status-badge").title).toMatch(/15:00 EAT close/);
  });

  it("labels a settled price as final and credits the NSE report", () => {
    render(<PriceStatusBadge status="final" statusDate="2026-08-07" />);
    const badge = screen.getByTestId("price-status-badge");
    expect(badge).toHaveAttribute("data-status", "final");
    expect(screen.getByText("Final")).toBeInTheDocument();
    expect(badge.title).toMatch(/official NSE daily report/);
    expect(badge.title).toMatch(/2026-08-07/);
  });

  it("omits the snapshot time once final, where it would be misleading", () => {
    render(<PriceStatusBadge status="final" statusDate="2026-08-07" asOf="13:00" />);
    expect(screen.queryByText("13:00")).not.toBeInTheDocument();
  });

  it("renders nothing when the pipeline has not labelled the price", () => {
    const { container } = render(<PriceStatusBadge status={null} statusDate={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("still renders when the status date is missing", () => {
    render(<PriceStatusBadge status="final" statusDate={null} />);
    expect(screen.getByText("Final")).toBeInTheDocument();
  });
});
