import { render, screen } from "@testing-library/react";
import { SignalBadge } from "./Badge";

describe("SignalBadge", () => {
  it("renders BUY text", () => {
    render(<SignalBadge signal="BUY" />);
    expect(screen.getByText("BUY")).toBeInTheDocument();
  });

  it("renders HOLD text", () => {
    render(<SignalBadge signal="HOLD" />);
    expect(screen.getByText("HOLD")).toBeInTheDocument();
  });

  it("renders SELL text", () => {
    render(<SignalBadge signal="SELL" />);
    expect(screen.getByText("SELL")).toBeInTheDocument();
  });
});
