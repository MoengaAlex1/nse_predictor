import { describe, it, expect } from "vitest";
import { marketStatus } from "./marketStatus";

// EAT is UTC+3, so 06:00Z == 09:00 EAT.
const utc = (iso: string) => new Date(iso);

describe("marketStatus", () => {
  it("is open at 09:00 EAT on a weekday", () => {
    // Mon 2026-09-07 06:00Z = 09:00 EAT
    const s = marketStatus(utc("2026-09-07T06:00:00Z"));
    expect(s.isOpen).toBe(true);
    expect(s.nowEat).toBe("09:00");
    expect(s.nextOpen).toBeNull();
  });

  it("is closed just before the open and points at today", () => {
    const s = marketStatus(utc("2026-09-07T05:30:00Z")); // 08:30 EAT Mon
    expect(s.isOpen).toBe(false);
    expect(s.nextOpen).toBe("today 09:00");
  });

  it("is closed at 15:00 EAT sharp", () => {
    const s = marketStatus(utc("2026-09-07T12:00:00Z")); // 15:00 EAT
    expect(s.isOpen).toBe(false);
  });

  it("rolls Friday evening to Monday", () => {
    const s = marketStatus(utc("2026-09-04T15:00:00Z")); // Fri 18:00 EAT
    expect(s.isOpen).toBe(false);
    expect(s.nextOpen).toBe("Mon 09:00");
  });

  it("rolls Saturday to Monday", () => {
    const s = marketStatus(utc("2026-09-05T09:00:00Z")); // Sat 12:00 EAT
    expect(s.nextOpen).toBe("Mon 09:00");
  });

  it("rolls Sunday to Monday", () => {
    const s = marketStatus(utc("2026-09-06T09:00:00Z")); // Sun 12:00 EAT
    expect(s.nextOpen).toBe("Mon 09:00");
  });

  it("handles the UTC-day boundary correctly", () => {
    // Mon 2026-09-07 22:30Z is Tue 01:30 EAT — next open is Tue, not Wed.
    const s = marketStatus(utc("2026-09-07T22:30:00Z"));
    expect(s.nowEat).toBe("01:30");
    expect(s.nextOpen).toBe("today 09:00");
  });
});
