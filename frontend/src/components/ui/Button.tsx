import type { FC, ReactNode, ButtonHTMLAttributes } from "react";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost";
  size?: "sm" | "md" | "lg";
  children: ReactNode;
}

const variants = {
  primary:   "bg-accent hover:bg-accent/90 text-white",
  secondary: "bg-raised hover:bg-rim text-ink border border-rim",
  ghost:     "hover:bg-raised text-sub hover:text-ink",
};

const sizes = {
  sm: "px-3 py-1.5 text-sm",
  md: "px-4 py-2 text-sm",
  lg: "px-6 py-3 text-base",
};

export const Button: FC<Props> = ({
  variant = "primary",
  size = "md",
  children,
  className = "",
  ...rest
}) => (
  <button
    className={`inline-flex items-center justify-center rounded-lg font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-accent/50 disabled:opacity-50 disabled:cursor-not-allowed ${variants[variant]} ${sizes[size]} ${className}`}
    {...rest}
  >
    {children}
  </button>
);
