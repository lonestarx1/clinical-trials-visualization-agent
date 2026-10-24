// Our visualization spec -> an ECharts option. Reads field names only from `encoding`,
// which is the point: a frontend can render the response without guessing (design Q12).
import type { EChartsOption } from "echarts";
import type { Channel, Datum, NetworkData, Visualization } from "./types";

export type Chart =
  | { kind: "echarts"; option: EChartsOption }
  | { kind: "metric"; value: number; label: string; unit: string | null };

export interface ClickEvent {
  seriesIndex?: number;
  dataIndex?: number;
  dataType?: string; // "node" | "edge" for graphs
}

const PALETTE = ["#2563eb", "#d97706", "#059669", "#dc2626", "#7c3aed", "#0891b2", "#db2777", "#65a30d"];

const axisName = (c: Channel) => (c.unit ? `${c.label} (${c.unit})` : c.label);

function rows(viz: Visualization): Datum[] {
  return Array.isArray(viz.data) ? viz.data : [];
}

function seriesField(viz: Visualization): string | null {
  return viz.encoding.color?.field ?? null;
}

/** Categories in first-seen order, and series names in first-seen order. */
function grid(viz: Visualization) {
  const x = viz.encoding.x.field;
  const color = seriesField(viz);
  const categories = [...new Set(rows(viz).map((r) => String(r[x])))];
  const series = color ? [...new Set(rows(viz).map((r) => String(r[color])))] : [null];
  return { x, color, categories, series };
}

const base = (viz: Visualization): EChartsOption => ({
  color: PALETTE,
  tooltip: { trigger: viz.type === "network_graph" ? "item" : "axis", confine: true },
  grid: { left: 64, right: 24, top: 40, bottom: 80, containLabel: true },
  animationDuration: 400,
});

export function toChart(viz: Visualization): Chart {
  const enc = viz.encoding;
  switch (viz.type) {
    case "metric": {
      const row = rows(viz)[0];
      return {
        kind: "metric",
        value: Number(row?.[enc.value.field] ?? 0),
        label: enc.value.label,
        unit: enc.value.unit ?? null,
      };
    }
    case "bar_chart":
    case "grouped_bar_chart":
    case "time_series": {
      const { x, color, categories, series } = grid(viz);
      const y = enc.y.field;
      const line = viz.type === "time_series";
      return {
        kind: "echarts",
        option: {
          ...base(viz),
          legend: color ? { top: 0, type: "scroll" } : undefined,
          xAxis: {
            type: "category",
            data: categories,
            name: axisName(enc.x),
            nameLocation: "middle",
            nameGap: 56,
            axisLabel: { rotate: categories.length > 6 && !line ? 30 : 0, interval: 0, hideOverlap: true },
          },
          yAxis: { type: "value", name: axisName(enc.y) },
          dataZoom: line && categories.length > 30 ? [{ type: "slider" }] : undefined,
          series: series.map((name) => ({
            name: name ?? enc.y.label,
            type: line ? "line" : "bar",
            smooth: false,
            showSymbol: line,
            data: categories.map((cat) => {
              const row = rows(viz).find((r) => String(r[x]) === cat && (!color || String(r[color]) === name));
              return row ? (row[y] as number) : 0;
            }),
          })),
        },
      };
    }
    case "histogram": {
      return {
        kind: "echarts",
        option: {
          ...base(viz),
          xAxis: { type: "category", data: rows(viz).map((r) => r.key), name: enc.x.label, nameLocation: "middle", nameGap: 40 },
          yAxis: { type: "value", name: axisName(enc.y) },
          series: [{ type: "bar", barCategoryGap: "2%", data: rows(viz).map((r) => r[enc.y.field] as number) }],
        },
      };
    }
    case "scatter_plot": {
      return {
        kind: "echarts",
        option: {
          ...base(viz),
          tooltip: { trigger: "item" },
          xAxis: { type: "value", name: axisName(enc.x), nameLocation: "middle", nameGap: 32, scale: true },
          yAxis: { type: "value", name: axisName(enc.y), scale: true },
          series: [{
            type: "scatter",
            symbolSize: 6,
            data: rows(viz).map((r) => [r[enc.x.field] as number, r[enc.y.field] as number]),
          }],
        },
      };
    }
    case "network_graph": {
      const { nodes, edges } = viz.data as NetworkData;
      const colorBy = enc.node_color.field;
      const groups = [...new Set(nodes.map((n) => String(n[colorBy])))].sort((a, b) =>
        colorBy === "community" ? Number(a) - Number(b) : a.localeCompare(b),
      );
      const maxWeight = Math.max(1, ...nodes.map((n) => Number(n[enc.node_size.field])));
      const maxEdge = Math.max(1, ...edges.map((e) => Number(e[enc.edge_width.field])));
      return {
        kind: "echarts",
        option: {
          ...base(viz),
          legend: { top: 0, type: "scroll", data: groups.map((g) => (colorBy === "community" ? `Cluster ${g}` : g)) },
          series: [{
            type: "graph",
            layout: "force",
            roam: true,
            draggable: true,
            force: { repulsion: 220, edgeLength: [40, 160], gravity: 0.08 },
            categories: groups.map((g) => ({ name: colorBy === "community" ? `Cluster ${g}` : g })),
            label: { show: true, position: "right", fontSize: 11 },
            labelLayout: { hideOverlap: true },
            emphasis: { focus: "adjacency", lineStyle: { width: 4 } },
            data: nodes.map((n) => ({
              id: String(n[enc.node_id.field]),
              name: String(n[enc.node_label.field]),
              value: Number(n[enc.node_size.field]),
              category: groups.indexOf(String(n[colorBy])),
              symbolSize: 8 + 34 * Math.sqrt(Number(n[enc.node_size.field]) / maxWeight),
              itemStyle: n.is_query_entity ? { borderColor: "#111827", borderWidth: 3 } : undefined,
            })),
            links: edges.map((e) => ({
              source: String(e[enc.edge_source.field]),
              target: String(e[enc.edge_target.field]),
              value: Number(e[enc.edge_width.field]),
              lineStyle: { width: 1 + 6 * (Number(e[enc.edge_width.field]) / maxEdge), opacity: 0.45 },
            })),
          }],
        },
      };
    }
  }
}

/** The data point behind a chart click, so its citations can be shown. */
export function datumAt(viz: Visualization, event: ClickEvent): Datum | null {
  if (viz.type === "network_graph") {
    const data = viz.data as NetworkData;
    const list = event.dataType === "edge" ? data.edges : data.nodes;
    return list[event.dataIndex ?? -1] ?? null;
  }
  if (viz.type === "scatter_plot" || viz.type === "histogram") return rows(viz)[event.dataIndex ?? -1] ?? null;
  const { x, color, categories, series } = grid(viz);
  const category = categories[event.dataIndex ?? -1];
  const name = series[event.seriesIndex ?? 0];
  return rows(viz).find((r) => String(r[x]) === category && (!color || String(r[color]) === name)) ?? null;
}
