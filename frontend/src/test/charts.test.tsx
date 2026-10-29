import { fireEvent, render, screen } from "@testing-library/react";
import { BarChart, LineChart } from "../components/charts";

const series = [
  { name: "baseline", color: "var(--series-1)" },
  { name: "candidate", color: "var(--series-2)" },
];

describe("charts", () => {
  it("renders labelled, focusable bars with a legend for two series", () => {
    render(
      <BarChart
        title="exact_match — mean"
        rows={[{ label: "model-a", values: [1, 0.75] }]}
        series={series}
        format={(v) => (v === null ? "—" : String(v))}
      />,
    );
    expect(screen.getByRole("img", { name: /exact_match/ })).toBeInTheDocument();
    expect(screen.getByLabelText("Legend")).toHaveTextContent("baseline");
    const bar = screen.getByLabelText("model-a, candidate: 0.75");
    fireEvent.focus(bar);
    expect(screen.getByRole("presentation")).toHaveTextContent("0.75");
  });

  it("omits the legend for a single series and shows missing values", () => {
    render(
      <BarChart
        title="latency"
        rows={[{ label: "m", values: [null] }]}
        series={[series[0]!]}
        format={(v) => (v === null ? "—" : String(v))}
      />,
    );
    expect(screen.queryByLabelText("Legend")).not.toBeInTheDocument();
    expect(screen.getByLabelText("m, baseline: —")).toBeInTheDocument();
  });

  it("moves the line chart crosshair with the keyboard and selects a point", () => {
    const onSelect = vi.fn();
    render(
      <LineChart
        title="trend"
        points={[
          { label: "run 1", values: [0.5, 0.4] },
          { label: "run 2", values: [0.9, null] },
        ]}
        series={series}
        format={(v) => (v === null ? "—" : String(v))}
        onSelect={onSelect}
      />,
    );
    const chart = screen.getByRole("img", { name: "trend" });
    fireEvent.keyDown(chart, { key: "ArrowRight" });
    fireEvent.keyDown(chart, { key: "ArrowRight" });
    const tooltip = screen.getByRole("presentation");
    expect(tooltip).toHaveTextContent("run 2");
    expect(tooltip).toHaveTextContent("0.9");
    expect(tooltip).toHaveTextContent("—");
    fireEvent.keyDown(chart, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith(1);
  });
});
