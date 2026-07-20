import { useState } from "react";

type Size = "sm" | "md" | "lg" | "xl";

const SIZE_IMG: Record<Size, string> = {
  sm: "h-8 w-8",
  md: "h-10 w-10",
  lg: "h-14 w-14",
  xl: "h-20 w-20",
};

const SIZE_TEXT: Record<Size, string> = {
  sm: "text-xs",
  md: "text-sm",
  lg: "text-base",
  xl: "text-2xl",
};

interface Props {
  /** Firestore document ID — the safe ticker, e.g. "ABSA_NR" */
  id: string;
  short: string;
  color: string;
  icon: string;
  size?: Size;
  className?: string;
}

export function CompanyLogo({ id, short, color, icon, size = "md", className = "" }: Props) {
  const [failed, setFailed] = useState(false);
  const imgClass = `${SIZE_IMG[size]} object-contain rounded ${className}`;
  const fallbackClass = `${SIZE_IMG[size]} rounded flex items-center justify-center flex-shrink-0 ${className}`;

  if (!failed) {
    return (
      <img
        src={`/logos/${id}.png`}
        alt={short}
        className={imgClass}
        onError={() => setFailed(true)}
      />
    );
  }

  return (
    <div
      className={fallbackClass}
      style={{ backgroundColor: `${color}22`, border: `1.5px solid ${color}55` }}
      title={short}
    >
      <span className={`${SIZE_TEXT[size]} select-none`}>{icon}</span>
    </div>
  );
}
