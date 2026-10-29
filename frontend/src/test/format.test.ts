import { formatMetric, formatNumber, formatPercent, formatSigned, niceTicks, seriesColor } from "../format";

describe("formatting", () => {
  it("formats numbers, missing values and infinities", () => {
    expect(formatNumber(null)).toBe("—");
    expect(formatNumber(0.842105)).toBe("0.842");
    expect(formatNumber(12345.6)).toBe("12,346");
    expect(formatNumber(Infinity)).toBe("∞");
    expect(formatPercent(0.0476)).toBe("4.8%");
    expect(formatSigned(0.25)).toBe("+0.25");
    expect(formatSigned(-0.25)).toBe("-0.25");
  });

  it("formats metrics in their units", () => {
    expect(formatMetric("latency", 15.9)).toBe("15.9 ms");
    expect(formatMetric("estimated_cost", 0.0012)).toBe("$0.0012");
    expect(formatMetric("estimated_cost", 0.0000126)).toBe("$0.000013");
    expect(formatMetric("estimated_cost", 0)).toBe("$0.00");
    expect(formatMetric("estimated_cost", 2.5)).toBe("$2.50");
    expect(formatMetric("exact_match", 1)).toBe("1");
  });

  it("produces nice ticks that cover the maximum", () => {
    expect(niceTicks(1)).toEqual([0, 0.25, 0.5, 0.75, 1]);
    const ticks = niceTicks(37);
    expect(ticks[0]).toBe(0);
    expect(ticks[ticks.length - 1]).toBeGreaterThanOrEqual(37);
  });

  it("keeps a series colour with its entity", () => {
    const all = ["a", "b", "c"];
    expect(seriesColor(all, "b")).toBe("var(--series-2)");
    expect(seriesColor(["b"], "b")).toBe("var(--series-1)");
  });
});
