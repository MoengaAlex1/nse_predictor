import type { FC } from "react";
import type { CompanyDoc, FinancialsDoc } from "../../types";

interface Props {
  company: CompanyDoc;
  financials: FinancialsDoc | null | undefined;
  /**
   * Live price used to compute trailing P/E. Fall-through chain of tiers
   * happens in the caller (see CompanyDeepDive) — this prop is whichever
   * price ended up being freshest.
   */
  currentPrice: number | null;
}

/*
 * ─── Sector-median P/E baseline ───────────────────────────────────────────
 * Duplicated from QuoteSummaryPanel intentionally: this file's Valuation
 * score has the same "attractive vs sector" concept and needs the same
 * numbers, but extracting them to a shared constants module is a follow-up
 * (the two consumers here are the only two in the app). If a third consumer
 * appears, lift both into src/data/sectorConstants.ts and re-import.
 */
const SECTOR_MEDIAN_PE: Record<string, number | null> = {
  Banking: 7.8,
  Insurance: 6.2,
  "Manufacturing and Allied": 11.4,
  "Telecommunication and Technology": 18.5,
  "Energy and Petroleum": 9.1,
  "Commercial and Services": 13.2,
  Agricultural: 14.1,
  Investment: 8.9,
  "Real Estate Investment Trust": 22.0,
  "Automobiles and Accessories": 10.5,
  "Construction and Allied": 9.8,
  "Exchange Traded Funds": null,
};

// Scores are all on a 0..6 integer scale — matches MSN Money's INTC page
// and gives a coarse-enough grid that a viewer instantly reads the shape of
// the polygon without squinting at fractional values.
const SCORE_MAX = 6;

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

/*
 * Every score function now returns { value: 0..SCORE_MAX } for a real
 * score OR { value: null, missing: "…" } when the input required to
 * compute it isn't available. The card renders "n/a" for null axes and
 * excludes them from the total's denominator — the prompt's rule was
 * "never score missing input as 0", because that reads as "worst" and
 * misleads the viewer.
 */
type Score = { value: number | null; missing?: string };

function ok(value: number): Score { return { value }; }
function na(missing: string): Score { return { value: null, missing }; }

function scoreValuation(pe: number | null, sectorMedian: number | null): Score {
  if (pe == null) return na("EPS missing — can't compute trailing P/E");
  if (pe <= 0)    return ok(0);   // negative earnings → genuine low score, not missing
  if (sectorMedian == null || sectorMedian <= 0) return na("Sector median P/E not defined");
  const ratio = pe / sectorMedian;
  const s = SCORE_MAX - (ratio - 0.5) * (SCORE_MAX / 1.5);
  return ok(Math.round(clamp(s, 0, SCORE_MAX)));
}

function scoreHealth(financials: FinancialsDoc | null | undefined): Score {
  const recent = (financials?.annual ?? []).slice(0, 5);
  if (recent.length === 0) return na("No annual results on file");
  const positiveEpsYears = recent.filter((a) => (a.eps ?? 0) > 0).length;
  const positiveBvps     = recent.some((a) => (a.bvps ?? 0) > 0);
  const paysDividend     = (financials?.dividends ?? []).length > 0;
  const epsPart = Math.round((positiveEpsYears / recent.length) * 4);
  return ok(clamp(epsPart + (positiveBvps ? 1 : 0) + (paysDividend ? 1 : 0), 0, SCORE_MAX));
}

function scoreEarnings(financials: FinancialsDoc | null | undefined): Score {
  const annual = (financials?.annual ?? [])
    .slice()
    .sort((a, b) => b.period_end.localeCompare(a.period_end));
  if (annual.length < 2) return na("Need at least 2 annual results to measure EPS growth");
  const eps1 = annual[0]?.eps;
  const eps0 = annual[1]?.eps;
  if (eps1 == null || eps0 == null) return na("EPS missing in one of the two most recent filings");
  if (eps0 <= 0) return ok(0);   // recovering from a loss year is a genuine 0
  const growth = (eps1 - eps0) / eps0;
  const g = clamp(growth, -0.2, 0.2);
  return ok(Math.round(3 + g * 15));
}

function scoreGrowth(financials: FinancialsDoc | null | undefined): Score {
  const annual = (financials?.annual ?? [])
    .slice()
    .sort((a, b) => b.period_end.localeCompare(a.period_end));
  if (annual.length < 2) return na("Need at least 2 annual results to measure revenue growth");
  const r1 = annual[0]?.revenue_kes_mn;
  const r0 = annual[1]?.revenue_kes_mn;
  if (r1 == null || r0 == null) return na("Revenue missing in one of the two most recent filings");
  if (r0 <= 0) return ok(0);
  const growth = (r1 - r0) / r0;
  const g = clamp(growth, -0.15, 0.15);
  return ok(Math.round(3 + g * 20));
}

function scorePerformance(company: CompanyDoc): Score {
  const points = company.price_history ?? [];
  if (points.length < 2) return na("Price history too short to compute 1Y return");
  const now = points[points.length - 1].price;
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - 365);
  const cutoffStr = cutoff.toISOString().slice(0, 10);
  const before = points.filter((p) => p.date <= cutoffStr);
  const yearAgo = before.length ? before[before.length - 1].price : points[0].price;
  if (!yearAgo || yearAgo <= 0) return na("No valid price 1 year ago");
  const ret = (now - yearAgo) / yearAgo;
  const g = clamp(ret, -0.2, 0.2);
  return ok(Math.round(3 + g * 15));
}

// ── SVG geometry ────────────────────────────────────────────────────────────

// viewBox is wider than tall so end-anchored labels on the two leftmost
// vertices (Growth and Performance) don't extend past x=0 and get clipped
// by the SVG boundary. The radar itself is centered inside this canvas —
// only the label margin uses the extra width.
const VIEWBOX_W = 400;
const VIEWBOX_H = 260;
const CX = VIEWBOX_W / 2;
const CY = VIEWBOX_H / 2 - 4;   // shift up a touch so labels have room below
const R  = 88;
const LABEL_R = R + 22;

/**
 * Convert (angleDeg, distance-from-center) to (x, y) on the SVG canvas.
 * Angle 0 points UP (north); positive angle rotates clockwise. Mirrors
 * how a viewer intuits a compass rose — Valuation up top, others rotating
 * clockwise from there.
 */
function polar(angleDeg: number, dist: number): [number, number] {
  const rad = ((angleDeg - 90) * Math.PI) / 180;
  return [CX + dist * Math.cos(rad), CY + dist * Math.sin(rad)];
}

const DIM_ORDER = ["Valuation", "Health", "Earnings", "Growth", "Performance"] as const;
type Dim = typeof DIM_ORDER[number];

export const RadarScoreCard: FC<Props> = ({ company, financials, currentPrice }) => {
  // ── Compute the five scores ──────────────────────────────────────────
  const annual = (financials?.annual ?? [])
    .slice()
    .sort((a, b) => b.period_end.localeCompare(a.period_end));
  const latestEps = annual[0]?.eps ?? null;
  const pe = currentPrice != null && latestEps != null && latestEps > 0
    ? currentPrice / latestEps
    : null;
  const sectorMedianPe = SECTOR_MEDIAN_PE[company.sector] ?? null;

  const scores: Record<Dim, Score> = {
    Valuation:   scoreValuation(pe, sectorMedianPe),
    Health:      scoreHealth(financials),
    Earnings:    scoreEarnings(financials),
    Growth:      scoreGrowth(financials),
    Performance: scorePerformance(company),
  };
  const scoredDims = DIM_ORDER.filter(d => scores[d].value != null);
  const totalScore = scoredDims.reduce((s, d) => s + (scores[d].value as number), 0);
  const totalDenominator = scoredDims.length * SCORE_MAX;
  const missingCount = DIM_ORDER.length - scoredDims.length;

  // ── Geometry ─────────────────────────────────────────────────────────
  const n = DIM_ORDER.length;
  const angles = DIM_ORDER.map((_, i) => (i * 360) / n);

  // Concentric grid pentagons at each integer score level
  const gridPentagons = Array.from({ length: SCORE_MAX }, (_, k) => k + 1).map((level) =>
    angles
      .map((a) => polar(a, (level / SCORE_MAX) * R))
      .map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`)
      .join(" ")
  );

  const axisEnds = angles.map((a) => polar(a, R));

  // Missing axes render at the center dot (distance 0) so they visibly
  // "collapse" instead of biasing the polygon toward a mid-value. The
  // per-axis label calls them out as n/a so the collapsed shape isn't
  // read as "0/6".
  const scorePoly = DIM_ORDER.map((dim, i) => {
    const s = scores[dim].value;
    return polar(angles[i], (s == null ? 0 : (s / SCORE_MAX) * R));
  });
  const scorePolyPoints = scorePoly
    .map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`)
    .join(" ");

  const labels = DIM_ORDER.map((dim, i) => {
    const [x, y] = polar(angles[i], LABEL_R);
    const anchor: "end" | "middle" | "start" =
      x < CX - 5 ? "end" : x > CX + 5 ? "start" : "middle";
    return { dim, x, y, anchor, score: scores[dim] };
  });

  return (
    <div className="rounded-xl border border-rim bg-surface p-4">
      <div className="mb-2 flex items-baseline justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted">
          Fundamental Score
        </h3>
        <span className="text-[10px] text-hint">
          {scoredDims.length === 0
            ? "insufficient data"
            : `${totalScore}/${totalDenominator} · ${scoredDims.length} of ${DIM_ORDER.length} axes scored`}
        </span>
      </div>

      <div className="flex justify-center">
        <svg
          viewBox={`0 0 ${VIEWBOX_W} ${VIEWBOX_H}`}
          role="img"
          aria-label={`Fundamental scores. ${DIM_ORDER.map((d) => `${d} ${scores[d]}/${SCORE_MAX}`).join(", ")}.`}
          className="w-full max-w-md"
        >
          {/* Concentric grid pentagons */}
          {gridPentagons.map((points, i) => (
            <polygon
              key={i}
              points={points}
              fill="none"
              className="stroke-seam"
              strokeWidth="1"
              strokeOpacity={i === SCORE_MAX - 1 ? 0.6 : 0.25}
            />
          ))}

          {/* Radial axis lines from center to each vertex */}
          {axisEnds.map(([x, y], i) => (
            <line
              key={i}
              x1={CX}
              y1={CY}
              x2={x.toFixed(1)}
              y2={y.toFixed(1)}
              className="stroke-seam"
              strokeWidth="1"
              strokeOpacity="0.4"
            />
          ))}

          {/* Filled score polygon */}
          <polygon
            points={scorePolyPoints}
            fill="rgb(56, 189, 248)"
            fillOpacity="0.22"
            stroke="rgb(56, 189, 248)"
            strokeWidth="2"
            strokeLinejoin="round"
          />

          {/* Score dots on each vertex — a hint that the axis exists even when
              the score is zero (the polygon degenerates to a point at center
              in that case; the dot at 0 is drawn INSIDE the polygon fill). */}
          {scorePoly.map(([x, y], i) => (
            <circle
              key={i}
              cx={x.toFixed(1)}
              cy={y.toFixed(1)}
              r="3"
              fill="rgb(56, 189, 248)"
            />
          ))}

          {/* Axis labels (dimension name + score) around the outside.
              For missing axes, render "n/a" with a native title tooltip
              explaining WHY it's missing — the prompt's rule was
              "never score missing input as 0". */}
          {labels.map(({ dim, x, y, anchor, score }) => (
            <g key={dim}>
              <text
                x={x.toFixed(1)}
                y={y.toFixed(1)}
                textAnchor={anchor}
                dominantBaseline="middle"
                className="fill-sub text-[10px] font-semibold uppercase tracking-wider"
                style={{ fontSize: "10px" }}
              >
                {dim}
              </text>
              <text
                x={x.toFixed(1)}
                y={(y + 12).toFixed(1)}
                textAnchor={anchor}
                dominantBaseline="middle"
                className={score.value == null ? "fill-hint" : "fill-hint font-mono"}
                style={{ fontSize: "10px" }}
              >
                {score.value == null
                  ? <title>{score.missing ?? "insufficient data"}</title>
                  : null}
                {score.value == null ? "n/a" : `${score.value}/${SCORE_MAX}`}
              </text>
            </g>
          ))}
        </svg>
      </div>

      {missingCount > 0 && (
        <p className="mt-2 text-[10px] leading-relaxed text-hint">
          {missingCount} axis{missingCount === 1 ? "" : "es"} shown as{" "}
          <span className="font-mono">n/a</span> — hover the label for the
          missing input. The score reflects only the axes where the input
          data is present, not zero-filled placeholders.
        </p>
      )}
    </div>
  );
};
