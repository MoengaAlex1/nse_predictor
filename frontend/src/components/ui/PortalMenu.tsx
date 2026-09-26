import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { FC, ReactNode, RefObject } from "react";
import { createPortal } from "react-dom";

// PortalMenu — renders a floating menu into document.body so it escapes
// any overflow-hidden / overflow-x-auto ancestor. The workstation
// toolbar row uses both (overflow-hidden for the rounded card border,
// overflow-x-auto so controls survive narrow viewports), which had
// been clipping every dropdown into a 40px sliver at the bottom of
// the trigger. Rendering via createPortal into body sidesteps both
// clips without changing any parent's overflow rules.
//
// Positioning is collision-aware: we anchor to the trigger's bounding
// box and flip to the opposite side of the axis if the menu would
// overflow the viewport. Recomputes on window resize, page scroll,
// and any container scroll that bubbles.

type Align = "start" | "end";

interface Props {
  open: boolean;
  triggerRef: RefObject<HTMLElement | null>;
  onClose: () => void;
  align?: Align;         // horizontal alignment against the trigger
  offset?: number;       // px gap between trigger and menu
  width?: number;        // if set, menu gets this width; otherwise auto
  className?: string;    // additional classes for the menu container
  children: ReactNode;
}

export const PortalMenu: FC<Props> = ({
  open,
  triggerRef,
  onClose,
  align = "start",
  offset = 4,
  width,
  className = "",
  children,
}) => {
  const menuRef = useRef<HTMLDivElement | null>(null);
  const [pos, setPos] = useState<{ top: number; left: number; maxHeight: number } | null>(null);

  // Position measure. Uses useLayoutEffect so the initial paint of the
  // menu never lands offscreen. Recomputes on scroll+resize while open.
  useLayoutEffect(() => {
    if (!open) return;
    const trigger = triggerRef.current;
    if (!trigger) return;

    const recompute = () => {
      const r = trigger.getBoundingClientRect();
      const menu = menuRef.current;
      const menuWidth = menu?.offsetWidth ?? width ?? 240;
      const menuHeight = menu?.offsetHeight ?? 240;

      let left = align === "end" ? r.right - menuWidth : r.left;
      // Clamp horizontally into the viewport with an 8px margin.
      const maxLeft = window.innerWidth - menuWidth - 8;
      if (left > maxLeft) left = maxLeft;
      if (left < 8) left = 8;

      // Prefer below the trigger. Flip above if there isn't enough
      // room and there IS enough room above.
      const spaceBelow = window.innerHeight - r.bottom - 8;
      const spaceAbove = r.top - 8;
      let top: number;
      let maxHeight: number;
      if (menuHeight + offset <= spaceBelow || spaceBelow >= spaceAbove) {
        top = r.bottom + offset;
        maxHeight = Math.max(120, spaceBelow);
      } else {
        top = Math.max(8, r.top - menuHeight - offset);
        maxHeight = Math.max(120, spaceAbove);
      }

      setPos({ top, left, maxHeight });
    };

    recompute();
    window.addEventListener("resize", recompute);
    window.addEventListener("scroll", recompute, true);
    return () => {
      window.removeEventListener("resize", recompute);
      window.removeEventListener("scroll", recompute, true);
    };
  }, [open, triggerRef, align, offset, width]);

  // Close on outside click and Escape. We check the trigger too so a
  // click on it doesn't immediately re-close the menu it just opened.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (menuRef.current?.contains(t)) return;
      if (triggerRef.current?.contains(t)) return;
      onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, onClose, triggerRef]);

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div
      ref={menuRef}
      role="menu"
      style={{
        position: "fixed",
        top: pos?.top ?? -9999,
        left: pos?.left ?? -9999,
        width,
        maxHeight: pos?.maxHeight,
        overflowY: "auto",
        zIndex: 9999,
      }}
      className={`rounded-md border border-rim bg-surface shadow-xl ${className}`}
    >
      {children}
    </div>,
    document.body,
  );
};
