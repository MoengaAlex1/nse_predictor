import type { FC, ReactNode } from "react";

interface Props {
  children: ReactNode;
  className?: string;
}

export const Card: FC<Props> = ({ children, className = "" }) => (
  <div className={`rounded-xl bg-surface border border-rim p-4 ${className}`}>
    {children}
  </div>
);
