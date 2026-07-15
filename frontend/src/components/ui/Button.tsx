import type { FC, ReactNode, ButtonHTMLAttributes } from "react";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost";
  size?: "sm" | "md" | "lg";
  children: ReactNode;
}

const variants = {
  primary: "bg-sky-500 hover:bg-sky-400 text-white",
  secondary: "bg-slate-700 hover:bg-slate-600 text-slate-200",
  ghost: "hover:bg-slate-700 text-slate-400 hover:text-slate-200",
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
    className={`inline-flex items-center justify-center rounded-lg font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-sky-400 disabled:opacity-50 disabled:cursor-not-allowed ${variants[variant]} ${sizes[size]} ${className}`}
    {...rest}
  >
    {children}
  </button>
);
