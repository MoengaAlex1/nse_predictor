import type { FC } from "react";
import { Link } from "react-router-dom";

export const NseLogo: FC = () => (
  <Link
    to="/"
    className="flex select-none items-center gap-2"
    aria-label="NSE Intelligence Home"
  >
    <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
      <circle cx="14" cy="14" r="13" fill="currentColor" className="text-accent" opacity="0.12" />
      <path
        d="M10 17 Q8 14 9 11 Q11 8 14 8 Q17 8 19 11 Q20 14 18 17 L16 18 Q14 19 12 18 Z"
        fill="currentColor"
        className="text-accent"
      />
      <path d="M10 11 Q8 8 7 9 Q8 11 10 12" fill="currentColor" className="text-accent" />
      <path d="M18 11 Q20 8 21 9 Q20 11 18 12" fill="currentColor" className="text-accent" />
    </svg>
    <span className="flex items-baseline gap-1">
      <span className="text-lg font-black text-ink">NSE</span>
      <span className="text-sm font-medium text-muted">Intelligence</span>
    </span>
  </Link>
);
