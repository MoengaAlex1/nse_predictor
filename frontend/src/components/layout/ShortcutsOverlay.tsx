import type { FC } from "react";

const SHORTCUTS: Array<{ keys: string; action: string }> = [
  { keys: "⌘K / Ctrl-K", action: "Open symbol search" },
  { keys: "/", action: "Focus symbol search" },
  { keys: "W", action: "Toggle the current ticker in your watchlist" },
  { keys: "1 – 9", action: "Switch chart range" },
  { keys: "?", action: "Show this list" },
  { keys: "Esc", action: "Close search or this list" },
];

export const ShortcutsOverlay: FC<{ open: boolean; onClose: () => void }> = ({ open, onClose }) => {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Keyboard shortcuts"
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm rounded-xl border border-rim bg-surface p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-ink">Keyboard shortcuts</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-xs text-sub transition-colors hover:text-ink"
          >
            Esc
          </button>
        </div>
        <dl className="space-y-2">
          {SHORTCUTS.map(({ keys, action }) => (
            <div key={keys} className="flex items-baseline justify-between gap-4">
              <dt className="shrink-0 rounded border border-seam bg-raised/60 px-1.5 py-0.5 font-mono text-[11px] text-sub">
                {keys}
              </dt>
              <dd className="text-right text-xs text-muted">{action}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
};
