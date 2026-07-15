import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { AuthGuard } from "./AuthGuard";
import * as storeModule from "../../store/useAuthStore";

vi.mock("../../store/useAuthStore", () => ({
  useAuthStore: vi.fn(),
}));

const mockUseAuthStore = vi.mocked(storeModule.useAuthStore);

describe("AuthGuard", () => {
  it("shows spinner when loading, not children or fallback", () => {
    mockUseAuthStore.mockReturnValue({
      user: null,
      loading: true,
      setUser: vi.fn(),
      setLoading: vi.fn(),
    } as any);
    render(
      <AuthGuard fallback={<div>Sign in</div>}>
        <div>Protected content</div>
      </AuthGuard>
    );
    expect(screen.queryByText("Protected content")).not.toBeInTheDocument();
    expect(screen.queryByText("Sign in")).not.toBeInTheDocument();
  });

  it("shows fallback when logged out", () => {
    mockUseAuthStore.mockReturnValue({
      user: null,
      loading: false,
      setUser: vi.fn(),
      setLoading: vi.fn(),
    } as any);
    render(
      <AuthGuard fallback={<div>Sign in</div>}>
        <div>Protected content</div>
      </AuthGuard>
    );
    expect(screen.getByText("Sign in")).toBeInTheDocument();
  });

  it("shows children when authenticated", () => {
    mockUseAuthStore.mockReturnValue({
      user: { uid: "abc" } as any,
      loading: false,
      setUser: vi.fn(),
      setLoading: vi.fn(),
    } as any);
    render(
      <AuthGuard fallback={<div>Sign in</div>}>
        <div>Protected content</div>
      </AuthGuard>
    );
    expect(screen.getByText("Protected content")).toBeInTheDocument();
    expect(screen.queryByText("Sign in")).not.toBeInTheDocument();
  });
});
