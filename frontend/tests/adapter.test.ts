// The adapter turns our spec into an ECharts option using only `encoding` (no guessing, Q12).
// Tested against the real example responses in docs/examples.
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, expectTypeOf, it } from "vitest";
import { datumAt, toChart, toTable } from "@/lib/adapter";
import { DARK, LIGHT, seriesColor } from "@/lib/theme";
import type { Datum, NetworkData, QueryResponse, Visualization } from "@/lib/types";

function example(name: string): Visualization {
  const file = path.resolve(__dirname, "../../docs/examples", `${name}.json`);
  const body = JSON.parse(readFileSync(file, "utf8")).response as QueryResponse;
  return body.visualization!;
}

describe("toChart", () => {
  it("bar chart: one category per row, in the given order", () => {
    const viz = example("2-condition-phases");
    const chart = toChart(viz);
    const rows = viz.data as Datum[];
    expect(chart.kind).toBe("echarts");
    if (chart.kind !== "echarts") return;
    expect((chart.option.xAxis as any).data).toEqual(rows.map((r) => r.phase));
    expect((chart.option.series as any[])[0].type).toBe("bar");
    expect((chart.option.series as any[])[0].data).toEqual(rows.map((r) => r.trial_count));
  });

  it("grouped bars: one series per group, aligned on the x categories", () => {
    const viz = example("3-drug-comparison");
    const chart = toChart(viz);
    if (chart.kind !== "echarts") throw new Error("expected echarts");
    const series = chart.option.series as any[];
    const groups = new Set((viz.data as Datum[]).map((r) => r.group));
    const categories = new Set((viz.data as Datum[]).map((r) => r.phase));
    expect(series.length).toBe(groups.size);
    series.forEach((s) => expect(s.data.length).toBe(categories.size));
  });

  it("time series: a line over the years", () => {
    const viz = example("1-drug-trend");
    const chart = toChart(viz);
    if (chart.kind !== "echarts") throw new Error("expected echarts");
    const series = chart.option.series as any[];
    expect(series[0].type).toBe("line");
    expect((chart.option.xAxis as any).data).toEqual((viz.data as Datum[]).map((r) => r.start_year));
  });

  it("network: every node and edge, coloured by community", () => {
    const viz = example("5-drug-network");
    const data = viz.data as NetworkData;
    const chart = toChart(viz);
    if (chart.kind !== "echarts") throw new Error("expected echarts");
    const graph = (chart.option.series as any[])[0];
    expect(graph.type).toBe("graph");
    expect(graph.data.length).toBe(data.nodes.length);
    expect(graph.links.length).toBe(data.edges.length);
    expect(graph.categories.length).toBe(new Set(data.nodes.map((n) => n.community)).size);
  });

  it("histogram and scatter from the encoding fields", () => {
    const histogram: Visualization = {
      type: "histogram", title: "t",
      encoding: { x: { field: "bin_start", type: "quantitative", label: "Enrollment" },
                  y: { field: "count", type: "quantitative", label: "Trials" } },
      data: [
        { key: "0-200", bin_start: 0, bin_end: 200, count: 4, is_overflow: false, citation_count: 4, citations: [], citations_truncated: false },
        { key: "1400+", bin_start: 1400, bin_end: null, count: 1, is_overflow: true, citation_count: 1, citations: [], citations_truncated: false },
      ],
    };
    const h = toChart(histogram);
    if (h.kind !== "echarts") throw new Error("expected echarts");
    expect((h.option.xAxis as any).data).toEqual(["0-200", "1400+"]);

    const scatter: Visualization = {
      type: "scatter_plot", title: "t",
      encoding: { x: { field: "enrollment", type: "quantitative", label: "Enrollment" },
                  y: { field: "duration_months", type: "quantitative", label: "Duration" },
                  id: { field: "nct_id", type: "nominal", label: "Trial" } },
      data: [{ key: "NCT1", nct_id: "NCT1", enrollment: 30, duration_months: 93.1, citation_count: 1, citations: [], citations_truncated: false }],
    };
    const sc = toChart(scatter);
    if (sc.kind !== "echarts") throw new Error("expected echarts");
    expect((sc.option.series as any[])[0].data).toEqual([[30, 93.1]]);
  });

  it("metric: a single number, not a chart", () => {
    const metric: Visualization = {
      type: "metric", title: "t",
      encoding: { value: { field: "value", type: "quantitative", label: "Trials", unit: "trials" } },
      data: [{ key: "all", value: 8, label: "Number of trials", citation_count: 8, citations: [], citations_truncated: false }],
    };
    expect(toChart(metric)).toMatchObject({ kind: "metric", value: 8, unit: "trials" });
  });
});

describe("datumAt", () => {
  it("maps a click back to the data point (for the citations panel)", () => {
    const bars = example("3-drug-comparison");
    const rows = bars.data as Datum[];
    const chart = toChart(bars);
    if (chart.kind !== "echarts") throw new Error("expected echarts");
    const second = (chart.option.series as any[])[1];
    const datum = datumAt(bars, { seriesIndex: 1, dataIndex: 0, dataType: undefined });
    expect(datum?.group).toBe(second.name);
    expect(datum?.phase).toBe((chart.option.xAxis as any).data[0]);
    expect(rows).toContain(datum);

    const net = example("5-drug-network");
    const nodes = (net.data as NetworkData).nodes;
    expect(datumAt(net, { seriesIndex: 0, dataIndex: 2, dataType: "node" })).toBe(nodes[2]);
    expect(datumAt(net, { seriesIndex: 0, dataIndex: 0, dataType: "edge" })).toBe((net.data as NetworkData).edges[0]);
  });
});

describe("network legend", () => {
  it("names each cluster after its largest entity, in cluster order", () => {
    const viz = example("5-drug-network");
    const nodes = (viz.data as NetworkData).nodes;
    const chart = toChart(viz);
    if (chart.kind !== "echarts") throw new Error("expected echarts");
    const names = ((chart.option.series as any[])[0].categories as { name: string }[]).map((c) => c.name);
    const communities = [...new Set(nodes.map((n) => Number(n.community)))].sort((a, b) => a - b);
    communities.forEach((c, i) => {
      const largest = nodes.filter((n) => n.community === c).sort((a, b) => Number(b.weight) - Number(a.weight))[0];
      expect(names[i]).toBe(`${largest.label} cluster`);
    });
  });

  it("keeps the layout inside the card, below the legend", () => {
    const chart = toChart(example("5-drug-network"));
    if (chart.kind !== "echarts") throw new Error("expected echarts");
    const graph = (chart.option.series as any[])[0];
    expect(graph.top).toBeGreaterThanOrEqual(48);
    // enough pull to stay in the card, enough push to keep labels apart (tuned on screenshots)
    expect(graph.force.gravity).toBeGreaterThanOrEqual(0.08);
    expect(graph.force.gravity).toBeLessThanOrEqual(0.15);
    expect(graph.force.repulsion).toBeGreaterThanOrEqual(250);
  });
});

describe("readable bars", () => {
  it("names (countries, sponsors, drugs) become horizontal bars, largest on top", () => {
    const viz = example("4-recruiting-countries");
    const rows = viz.data as Datum[];
    const chart = toChart(viz);
    if (chart.kind !== "echarts") throw new Error("expected echarts");
    const y = chart.option.yAxis as any;
    expect(y.type).toBe("category");
    expect(y.data).toEqual(rows.map((r) => r.country));
    expect(y.inverse).toBe(true);
    expect((chart.option.xAxis as any).type).toBe("value");
  });

  it("ordered categories (phases) stay vertical", () => {
    const chart = toChart(example("2-condition-phases"));
    if (chart.kind !== "echarts") throw new Error("expected echarts");
    expect((chart.option.xAxis as any).type).toBe("category");
  });
});

describe("colour", () => {
  it("uses the validated palette in fixed order, per theme", () => {
    const light = toChart(example("3-drug-comparison"), LIGHT);
    const dark = toChart(example("3-drug-comparison"), DARK);
    if (light.kind !== "echarts" || dark.kind !== "echarts") throw new Error("expected echarts");
    expect((light.option.color as string[]).slice(0, 2)).toEqual(["#2a78d6", "#eb6834"]);
    expect((dark.option.color as string[]).slice(0, 2)).toEqual(["#3987e5", "#d95926"]);
  });

  it("folds clusters past the eighth into one neutral colour, never a generated hue", () => {
    expect(seriesColor(LIGHT, 0)).toBe("#2a78d6");
    expect(seriesColor(LIGHT, 7)).toBe("#e34948");
    expect(seriesColor(LIGHT, 8)).toBe(LIGHT.other);
    expect(seriesColor(LIGHT, 12)).toBe(LIGHT.other);
  });
});

describe("table view", () => {
  it("lists every data point with the encoded fields and its trial count", () => {
    const viz = example("4-recruiting-countries");
    const table = toTable(viz);
    expect(table.columns.map((c) => c.field)).toEqual(["country", "trial_count", "citation_count"]);
    expect(table.rows.length).toBe((viz.data as Datum[]).length);
  });

  it("lists network nodes and links", () => {
    const viz = example("5-drug-network");
    const table = toTable(viz);
    expect(table.rows.length).toBe((viz.data as NetworkData).nodes.length + (viz.data as NetworkData).edges.length);
  });
});

describe("direct labels", () => {
  it("single-series horizontal bars carry their values at the bar end", () => {
    const chart = toChart(example("4-recruiting-countries"));
    if (chart.kind !== "echarts") throw new Error("expected echarts");
    const series = (chart.option.series as any[])[0];
    expect(series.label.show).toBe(true);
    expect(series.label.position).toBe("right");
    expect((chart.option.xAxis as any).nameLocation).toBe("middle");
  });
});

describe("schema 2.0", () => {
  it("has a title and no summary (the AI summary was removed)", () => {
    expectTypeOf<Visualization>().toHaveProperty("title");
    expectTypeOf<Visualization>().not.toHaveProperty("summary");
    for (const name of ["1-drug-trend", "2-condition-phases", "3-drug-comparison", "4-recruiting-countries", "5-drug-network"]) {
      const viz = example(name);
      expect(viz.title).toBeTruthy();
      expect(viz).not.toHaveProperty("summary");
    }
  });
});
