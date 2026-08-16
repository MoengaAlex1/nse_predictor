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
  /**
   * Firestore short-form ticker (e.g. "ABSA", "SGL") — this is the filename
   * key used by /logos/${id}.png. Do NOT pass the .NR-suffixed URL ticker
   * or the lookup will 404 and every callsite will see a fallback tile.
   */
  id: string;
  /**
   * Optional CompanyDoc fields. When missing (either because the doc hasn't
   * loaded yet or because the ticker has no Firestore entry — GLD, KAPC,
   * PORT, SHKL), the component synthesises a deterministic colour from `id`
   * and the first two characters of the ticker as the glyph, so callsites
   * can drop their `{company && …}` guards and always render SOMETHING.
   */
  short?: string;
  color?: string;
  icon?: string;
  size?: Size;
  className?: string;
}

/**
 * Return a deterministic 6-digit hex colour derived from the seed. Used as
 * a fallback when the CompanyDoc has no `color` field so every ticker gets
 * a stable, recognisable tint instead of a blank tile. Saturation and
 * lightness are fixed to keep every generated colour readable against the
 * page's surfaces in both light and dark themes.
 */
function hashColor(seed: string): string {
  let hash = 0;
  for (let i = 0; i < seed.length; i++) {
    hash = (hash << 5) - hash + seed.charCodeAt(i);
    hash |= 0; // int32
  }
  const hue = Math.abs(hash) % 360;
  return hslToHex(hue, 55, 50);
}

function hslToHex(h: number, s: number, l: number): string {
  const S = s / 100;
  const L = l / 100;
  const k = (n: number): number => (n + h / 30) % 12;
  const a = S * Math.min(L, 1 - L);
  const f = (n: number): number =>
    L - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
  const to255 = (v: number): string =>
    Math.round(v * 255).toString(16).padStart(2, "0");
  return `#${to255(f(0))}${to255(f(8))}${to255(f(4))}`;
}

/**
 * Prefer the CompanyDoc's `icon` (often a curated emoji or short glyph),
 * otherwise the first two characters of the short-form ticker upper-cased.
 * `?` is the ultimate fallback so the tile is never completely empty.
 */
function fallbackGlyph(icon: string | undefined, short: string | undefined, id: string): string {
  if (icon && icon.trim()) return icon;
  // Prefer the human-readable short label; fall back to id (also short-form
  // when passed correctly). Take 2 characters so the tile is more identifiable
  // than a single letter — "SG" for SGL, "CT" for CTUM, etc.
  const seed = ((short ?? id) ?? "").trim();
  if (seed.length >= 2) return seed.slice(0, 2).toUpperCase();
  if (seed.length === 1) return seed.toUpperCase();
  return "?";
}

export function CompanyLogo({
  id,
  short,
  color,
  icon,
  size = "md",
  className = "",
}: Props) {
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

  // The logo file didn't exist. Render a deterministic coloured tile so the
  // reader still sees something anchored to the ticker rather than a blank
  // shape — matches how the working sidebar fallback would look, but never
  // fails to fill because we now synthesize `color` and `icon` locally
  // whenever the CompanyDoc doesn't carry them.
  const effectiveColor = color && color.trim() ? color : hashColor(id || short || "?");
  const effectiveIcon  = fallbackGlyph(icon, short, id);

  return (
    <div
      className={fallbackClass}
      style={{
        backgroundColor: `${effectiveColor}22`,
        border: `1.5px solid ${effectiveColor}55`,
        color: effectiveColor,
      }}
      title={short}
    >
      <span className={`${SIZE_TEXT[size]} font-bold select-none`}>
        {effectiveIcon}
      </span>
    </div>
  );
}
