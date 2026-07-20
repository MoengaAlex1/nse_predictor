import type { FC } from "react";

const sizes = { sm: "h-4 w-4", md: "h-8 w-8", lg: "h-12 w-12" };

export const Spinner: FC<{ size?: "sm" | "md" | "lg" }> = ({ size = "md" }) => (
  <div
    className={`${sizes[size]} animate-spin rounded-full border-2 border-rim border-t-accent`}
  />
);
