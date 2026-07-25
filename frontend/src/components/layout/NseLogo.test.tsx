import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { NseLogo } from "./NseLogo";

describe("NseLogo", () => {
  it("renders NSE and Intelligence text", () => {
    render(<MemoryRouter><NseLogo /></MemoryRouter>);
    expect(screen.getByText("NSE")).toBeInTheDocument();
    expect(screen.getByText("Intelligence")).toBeInTheDocument();
  });

  it("links to /", () => {
    render(<MemoryRouter><NseLogo /></MemoryRouter>);
    expect(screen.getByRole("link", { name: /NSE Intelligence Home/i })).toHaveAttribute("href", "/");
  });
});
