import type { FC, ReactNode } from "react";
import { Navbar } from "./Navbar";

export const PageShell: FC<{ children: ReactNode }> = ({ children }) => (
  <div className="min-h-screen bg-canvas text-ink">
    <Navbar />
    <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">{children}</main>
  </div>
);
