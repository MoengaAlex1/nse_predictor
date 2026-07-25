import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

vi.mock("../../context/ThemeContext", () => ({
  useTheme: () => ({
    theme: "dark",
    setTheme: vi.fn(),
    resolvedTheme: "dark",
  }),
}));

import { ThemeToggle } from "./ThemeToggle";

describe("ThemeToggle", () => {
  it("renders three theme buttons", () => {
    render(<ThemeToggle />);
    expect(screen.getByTitle("Light mode")).toBeInTheDocument();
    expect(screen.getByTitle("System theme")).toBeInTheDocument();
    expect(screen.getByTitle("Dark mode")).toBeInTheDocument();
  });
});
