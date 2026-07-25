import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { NseLogo } from "./NseLogo";

describe("NseLogo", () => {
  it("renders NSE and Intelligence text", () => {
    render(<MemoryRouter><NseLogo /></MemoryRouter>);
    expect(screen.getByText("NSE")).toBeInTheDocument();
    expect(screen.getByText("Intelligence")).toBeInTheDocument();
  });

  it("links to / and has decorative SVG hidden from screen readers", () => {
    render(<MemoryRouter><NseLogo /></MemoryRouter>);
    const link = screen.getByRole("link", { name: /NSE Intelligence Home/i });
    expect(link).toHaveAttribute("href", "/");
    expect(link.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });
});
