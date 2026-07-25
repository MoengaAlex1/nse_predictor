import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

vi.mock("../../context/ThemeContext", () => ({
  useTheme: () => ({ theme: "dark", setTheme: vi.fn(), resolvedTheme: "dark" }),
}));

import { MobileNav, MobileMenuButton } from "./MobileNav";

const wrap = (ui: React.ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>);

describe("MobileNav", () => {
  it("renders nothing when isOpen is false", () => {
    wrap(<MobileNav isOpen={false} onClose={vi.fn()} />);
    expect(screen.queryByText("Menu")).not.toBeInTheDocument();
  });

  it("renders nav links when isOpen is true", () => {
    wrap(<MobileNav isOpen={true} onClose={vi.fn()} />);
    expect(screen.getByText("Menu")).toBeInTheDocument();
    expect(screen.getByText("Markets")).toBeInTheDocument();
    expect(screen.getByText("Screener")).toBeInTheDocument();
  });

  it("calls onClose when the close button is clicked", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    wrap(<MobileNav isOpen={true} onClose={onClose} />);
    await user.click(screen.getByRole("button", { name: /close/i }));
    expect(onClose).toHaveBeenCalled();
  });
});

describe("MobileMenuButton", () => {
  it("calls onClick when pressed", async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(<MobileMenuButton onClick={onClick} />);
    await user.click(screen.getByRole("button", { name: /open menu/i }));
    expect(onClick).toHaveBeenCalled();
  });
});
