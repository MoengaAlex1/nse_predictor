import type { FC, ReactNode } from "react";

type ComingSoonProps = {
  title: string;
  /** What this route will do, in one sentence. */
  summary: string;
  /** Which phase of the build lands it. */
  phase: string;
  children?: ReactNode;
};

/**
 * Stub state for a route that exists but is not built yet.
 *
 * A nav item with no route is worse than a stub — it dead-ends the user with
 * no explanation. This says plainly what is coming and when.
 */
export const ComingSoon: FC<ComingSoonProps> = ({ title, summary, phase, children }) => (
  <section className="mx-auto max-w-3xl px-4 py-16 text-center sm:px-6">
    <h1 className="text-2xl font-bold text-ink">{title}</h1>
    <p className="mx-auto mt-3 max-w-prose text-sm text-sub">{summary}</p>
    <p className="mt-6 inline-flex items-center gap-2 rounded-full border border-seam bg-raised/60 px-3 py-1 text-xs font-medium text-muted">
      <span className="h-1.5 w-1.5 rounded-full bg-accent" aria-hidden="true" />
      Coming in {phase}
    </p>
    {children && <div className="mt-8 text-left">{children}</div>}
  </section>
);
