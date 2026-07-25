import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

const setThemeMock = vi.fn();

vi.mock("../../context/ThemeContext", () => ({
  useTheme: () => ({
    theme: "dark",
    setTheme: setThemeMock,
    resolvedTheme: "dark",
  }),
}));

import { ThemeToggle } from "./ThemeToggle";

describe("ThemeToggle", () => {
  beforeEach(() => {
    setThemeMock.mockClear();
  });

  it("renders three theme buttons", () => {
    render(<ThemeToggle />);
    expect(screen.getByTitle("Light mode")).toBeInTheDocument();
    expect(screen.getByTitle("System theme")).toBeInTheDocument();
    expect(screen.getByTitle("Dark mode")).toBeInTheDocument();
  });

  it("calls setTheme with the correct value when a button is clicked", async () => {
    const user = userEvent.setup();
    render(<ThemeToggle />);
    await user.click(screen.getByTitle("Light mode"));
    expect(setThemeMock).toHaveBeenCalledWith("light");
  });
});
