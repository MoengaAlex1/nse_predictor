import { useMemo } from "react";
import type { FC } from "react";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";
import type { FundamentalsDoc } from "../../types";
import { EM_DASH } from "../../lib/format";

type Props = {
  fundamentals: FundamentalsDoc | null | undefined;
};

const SEGMENT_COLORS = [
  "#22c55e", "#38bdf8", "#f59e0b", "#a78bfa",
  "#f472b6", "#facc15", "#2dd4bf", "#f87171",
];

const GEO_COLORS = [
  "#0ea5e9", "#8b5cf6", "#10b981", "#f97316",
  "#ec4899", "#eab308", "#14b8a6", "#ef4444",
];

type PieRow = { name: string; value: number; hasPct: boolean };

function prepPie(rows: { name: string; revenue_pct?: number | null; country?: never }[] | { country: string; revenue_pct?: number | null; name?: never }[] | undefined): PieRow[] {
  if (!rows || rows.length === 0) return [];
  const withPct = rows.filter((r) => r.revenue_pct != null && r.revenue_pct > 0);
  if (withPct.length > 0) {
    return withPct.map((r) => ({
      name: ("name" in r ? r.name : r.country) as string,
      value: r.revenue_pct as number,
      hasPct: true,
    }));
  }
  // No percentages — equal-weight so we can still visualise the segment names
  const equalPct = 100 / rows.length;
  return rows.map((r) => ({
    name: ("name" in r ? r.name : r.country) as string,
    value: equalPct,
    hasPct: false,
  }));
}

const MiniTooltip: FC<{
  active?: boolean;
  payload?: { name: string; value: number; payload: PieRow }[];
}> = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const r = payload[0].payload;
  return (
    <div className="rounded border border-rim bg-surface px-2 py-1 text-[10px]">
      <p className="font-semibold text-ink">{r.name}</p>
      {r.hasPct ? (
        <p className="font-mono text-hint">{r.value.toFixed(1)}%</p>
      ) : (
        <p className="italic text-hint">breakdown not published</p>
      )}
    </div>
  );
};

const Donut: FC<{ data: PieRow[]; colors: string[] }> = ({ data, colors }) => (
  <ResponsiveContainer width="100%" height={160}>
    <PieChart>
      <Pie
        data={data}
        dataKey="value"
        cx="50%"
        cy="50%"
        innerRadius={38}
        outerRadius={60}
        paddingAngle={2}
        stroke="rgb(var(--canvas))"
        strokeWidth={2}
        isAnimationActive={false}
      >
        {data.map((_, i) => (
          <Cell key={i} fill={colors[i % colors.length]} />
        ))}
      </Pie>
      <Tooltip content={<MiniTooltip />} />
    </PieChart>
  </ResponsiveContainer>
);

export const BusinessMixCard: FC<Props> = ({ fundamentals }) => {
  const segments = useMemo(() => prepPie(fundamentals?.business_segments), [fundamentals?.business_segments]);
  const geo      = useMemo(() => prepPie(fundamentals?.geographic_exposure), [fundamentals?.geographic_exposure]);

  if (segments.length === 0 && geo.length === 0) {
    return (
      <div className="rounded-xl border border-rim bg-surface p-4">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted">
          Business Mix
        </p>
        <p className="mt-3 text-xs text-hint">
          No segment or geographic breakdown extracted yet. Populates once
          the IR-enrichment pipeline processes the company's annual report.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-rim bg-surface">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-seam px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted">
          Business Mix
        </p>
        <span className="font-mono text-[10px] text-hint">
          {segments.length > 0 && `${segments.length} segments`}
          {segments.length > 0 && geo.length > 0 && " · "}
          {geo.length > 0 && `${geo.length} regions`}
        </span>
      </div>

      <div className="grid gap-4 p-4 md:grid-cols-2">
        <MixPanel title="By segment" data={segments} colors={SEGMENT_COLORS} />
        <MixPanel title="By geography" data={geo} colors={GEO_COLORS} />
      </div>
    </div>
  );
};

const MixPanel: FC<{ title: string; data: PieRow[]; colors: string[] }> = ({
  title, data, colors,
}) => {
  if (data.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-seam bg-canvas/40 p-4 text-[11px] text-hint">
        <p className="font-semibold uppercase tracking-wider text-muted">{title}</p>
        <p className="mt-1">Not disclosed{EM_DASH ? "" : "—"}</p>
      </div>
    );
  }
  return (
    <div>
      <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-hint">
        {title}
      </p>
      <Donut data={data} colors={colors} />
      <ul className="mt-2 space-y-1">
        {data.slice(0, 6).map((r, i) => (
          <li key={i} className="flex items-baseline justify-between gap-2 text-[10px]">
            <span className="flex min-w-0 items-baseline gap-1.5">
              <span
                className="mt-1 inline-block h-1.5 w-1.5 shrink-0 rounded-sm"
                style={{ background: colors[i % colors.length] }}
              />
              <span className="truncate text-sub">{r.name}</span>
            </span>
            <span className="font-mono tabular-nums text-hint">
              {r.hasPct ? `${r.value.toFixed(1)}%` : EM_DASH}
            </span>
          </li>
        ))}
        {data.length > 6 && (
          <li className="pl-3 text-[10px] italic text-hint">
            +{data.length - 6} more
          </li>
        )}
      </ul>
    </div>
  );
};
