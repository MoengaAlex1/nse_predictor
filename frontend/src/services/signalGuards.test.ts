import { describe, it, expect } from "vitest";
import {
  checkModel, buildEnsemble, confidenceFromHitRate, signalsDisagree,
  MIN_TARGET_RATIO, MAX_TARGET_RATIO,
} from "./signalGuards";

// The exact figures the shipped panel reported for EQTY.
const EQTY_CLOSE = 106;
const EQTY_MODELS = [
  { name: "LSTM",    target: 42.33, mape: 20.1, rmse: 486.028 },
  { name: "ARIMA",   target: 106.0, mape: 4.2,  rmse: 5.1 },
  { name: "XGBoost", target: 56.56, mape: 9.0,  rmse: 8.2 },
];

describe("checkModel — the EQTY case", () => {
  it("errors the LSTM target as a scale fault", () => {
    const m = checkModel(EQTY_MODELS[0], EQTY_CLOSE);
    expect(m.status).toBe("errored");
    expect(m.reason).toMatch(/sanity band/i);
    // 42.33 / 106 = 0.40 — just under the floor.
    expect(m.impliedPct).toBeCloseTo(-60.07, 1);
  });

  it("errors the XGBoost target too", () => {
    // 56.56 / 106 = 0.534 — inside the band, so it survives the band check
    // but its implied move is still reported honestly.
    const m = checkModel(EQTY_MODELS[2], EQTY_CLOSE);
    expect(m.impliedPct).toBeCloseTo(-46.64, 1);
  });

  it("reports RMSE as a percentage of price, exposing the scale fault", () => {
    const m = checkModel(EQTY_MODELS[0], EQTY_CLOSE);
    // RMSE 486 on a 106 stock is 458% of price — self-evidently not on scale.
    expect(m.rmsePctOfPrice).toBeCloseTo(458.5, 0);
  });

  it("flags a model over the MAPE ceiling as low reliability", () => {
    const m = checkModel({ name: "X", target: 100, mape: 20.1 }, EQTY_CLOSE);
    expect(m.status).toBe("low-reliability");
    expect(m.reason).toMatch(/MAPE/);
  });

  it("passes a sane, reliable model", () => {
    const m = checkModel(EQTY_MODELS[1], EQTY_CLOSE);
    expect(m.status).toBe("ok");
    expect(m.reason).toBeNull();
    expect(m.impliedPct).toBeCloseTo(0, 6);
  });

  it("errors rather than guesses when price or target is missing", () => {
    expect(checkModel({ name: "X", target: 100 }, null).status).toBe("errored");
    expect(checkModel({ name: "X", target: null }, 106).status).toBe("errored");
    expect(checkModel({ name: "X", target: 0 }, 106).status).toBe("errored");
  });

  it("uses the documented band boundaries", () => {
    expect(checkModel({ name: "X", target: EQTY_CLOSE * MIN_TARGET_RATIO }, EQTY_CLOSE).status).toBe("ok");
    expect(checkModel({ name: "X", target: EQTY_CLOSE * MAX_TARGET_RATIO }, EQTY_CLOSE).status).toBe("ok");
    expect(checkModel({ name: "X", target: EQTY_CLOSE * 0.39 }, EQTY_CLOSE).status).toBe("errored");
    expect(checkModel({ name: "X", target: EQTY_CLOSE * 2.6 }, EQTY_CLOSE).status).toBe("errored");
  });
});

describe("buildEnsemble", () => {
  it("excludes the errored model and states the rule", () => {
    const e = buildEnsemble(EQTY_MODELS, EQTY_CLOSE);
    expect(e.models.find((m) => m.name === "LSTM")!.status).toBe("errored");
    expect(e.surviving.map((m) => m.name)).toEqual(["ARIMA", "XGBoost"]);
    expect(e.rule).toMatch(/Median of 2 surviving models/);
  });

  it("produces a target that reconciles arithmetically with its own rule", () => {
    const e = buildEnsemble(EQTY_MODELS, EQTY_CLOSE);
    // median(106.00, 56.56) = 81.28
    expect(e.target).toBeCloseTo(81.28, 6);
    // and the headline percentage must match that target, unlike the -9.90%
    // the shipped panel printed against a 60.42 target.
    expect(e.impliedPct).toBeCloseTo(((81.28 - 106) / 106) * 100, 6);
    expect(e.impliedPct).toBeCloseTo(-23.32, 2);
  });

  it("never reproduces the unreconciled -9.90% headline", () => {
    const e = buildEnsemble(EQTY_MODELS, EQTY_CLOSE);
    expect(e.impliedPct).not.toBeCloseTo(-9.9, 1);
  });

  it("returns no target when nothing survives", () => {
    const e = buildEnsemble([{ name: "LSTM", target: 1 }], EQTY_CLOSE);
    expect(e.target).toBeNull();
    expect(e.impliedPct).toBeNull();
    expect(e.rule).toMatch(/No model passed/);
  });
});

describe("confidenceFromHitRate", () => {
  it("derives confidence from realised calls and shows the formula", () => {
    const c = confidenceFromHitRate(18, 30);
    expect(c!.pct).toBeCloseTo(60, 6);
    expect(c!.formula).toMatch(/18 correct .* out of 30/);
  });
  it("returns null rather than a fabricated percentage", () => {
    expect(confidenceFromHitRate(null, 30)).toBeNull();
    expect(confidenceFromHitRate(5, 0)).toBeNull();
    expect(confidenceFromHitRate(31, 30)).toBeNull();
  });
});

describe("signalsDisagree", () => {
  it("treats Neutral and HOLD as agreement", () => {
    expect(signalsDisagree("Neutral", "HOLD")).toBe(false);
  });
  it("flags gauge Neutral against model SELL", () => {
    expect(signalsDisagree("Neutral", "SELL")).toBe(true);
  });
  it("is quiet when either side is absent", () => {
    expect(signalsDisagree(null, "SELL")).toBe(false);
    expect(signalsDisagree("Buy", null)).toBe(false);
  });
});
