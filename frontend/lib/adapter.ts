// Our visualization spec -> an ECharts option. Field names are read only from `encoding`,
// which is the point: a frontend can render the response without guessing (design Q12).
import type { EChartsOption } from "echarts";
import { LIGHT, seriesColor, type Theme } from "./theme";
import type { Channel, Datum, NetworkData, Visualization } from "./types";

export type Chart =
  | { kind: "echarts"; option: EChartsOption }
  | { kind: "metric"; value: number; label: string; unit: string | null };

export interface ClickEvent {
  seriesIndex?: number;
  dataIndex?: number;
  dataType?: string; // "node" | "edge" for graphs
}

const FONT = "'IBM Plex Sans', ui-sans-serif, system-ui, sans-serif";
const fmt = (v: unknown) => (typeof v === "number" ? v.toLocaleString("en-US", { maximumFractionDigits: 1 }) : String(v));
const axisName = (c: Channel) => (c.unit && c.unit !== "trials" ? `${c.label} (${c.unit})` : c.label);

function rows(viz: Visualization): Datum[] {
  return Array.isArray(viz.data) ? viz.data : [];
}

/** Categories and series in first-seen order (the backend already sorted them). */
function grid(viz: Visualization) {
  const x = viz.encoding.x.field;
  const color = viz.encoding.color?.field ?? null;
  const categories = [...new Set(rows(viz).map((r) => String(r[x])))];
  const series = color ? [...new Set(rows(viz).map((r) => String(r[color])))] : [null];
  return { x, color, categories, series };
}

/** Names (entities) read best as horizontal bars; ordered categories and time stay vertical. */
export function isHorizontal(viz: Visualization): boolean {
  return (viz.type === "bar_chart" || viz.type === "grouped_bar_chart") && viz.encoding.x.type === "nominal";
}

function base(theme: Theme, palette: string[]): EChartsOption {
  return {
    color: palette,
    textStyle: { fontFamily: FONT, color: theme.ink },
    animationDuration: 350,
    tooltip: {
      confine: true,
      backgroundColor: theme.surface,
      borderColor: theme.grid,
      textStyle: { color: theme.ink, fontFamily: FONT, fontSize: 13 },
      extraCssText: "box-shadow: 0 6px 24px rgba(15,23,42,.12); border-radius: 8px;",
    },
  };
}

const valueAxis = (theme: Theme, name: string) => ({
  type: "value" as const,
  name,
  nameGap: 14,
  nameTextStyle: { color: theme.muted, align: "left" as const },
  axisLabel: { color: theme.muted, formatter: (v: number) => fmt(v) },
  splitLine: { lineStyle: { color: theme.grid } },
});

const categoryAxis = (theme: Theme, data: string[], extra: Record<string, unknown> = {}) => ({
  type: "category" as const,
  data,
  axisTick: { show: false },
  axisLine: { lineStyle: { color: theme.grid } },
  axisLabel: { color: theme.muted, hideOverlap: true },
  ...extra,
});

function legend(theme: Theme, show: boolean) {
  return show
    ? { top: 0, left: 0, type: "scroll" as const, icon: "roundRect", itemWidth: 12, itemHeight: 12,
        textStyle: { color: theme.ink }, pageTextStyle: { color: theme.muted } }
    : undefined;
}

export function toChart(viz: Visualization, theme: Theme = LIGHT): Chart {
  const enc = viz.encoding;
  const palette = theme.palette.slice();
  switch (viz.type) {
    case "metric": {
      const row = rows(viz)[0];
      return { kind: "metric", value: Number(row?.[enc.value.field] ?? 0), label: enc.value.label, unit: enc.value.unit ?? null };
    }
    case "bar_chart":
    case "grouped_bar_chart":
    case "time_series": {
      const { x, color, categories, series } = grid(viz);
      const y = enc.y.field;
      const line = viz.type === "time_series";
      const horizontal = isHorizontal(viz);
      const radius = horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0];
      const cats = categoryAxis(theme, categories, horizontal
        ? { inverse: true, axisLabel: { color: theme.ink, width: 180, overflow: "truncate", hideOverlap: false } }
        : { axisLabel: { color: theme.muted, hideOverlap: true, rotate: !line && categories.length > 7 ? 35 : 0,
            width: 120, overflow: "truncate" } });
      const values = horizontal
        ? { ...valueAxis(theme, axisName(enc.y)), nameLocation: "middle" as const, nameGap: 28 }
        : valueAxis(theme, axisName(enc.y));
      const directLabels = horizontal && !color && categories.length <= 30;
      return {
        kind: "echarts",
        option: {
          ...base(theme, palette),
          legend: legend(theme, Boolean(color)),
          grid: { left: 8, right: 24, top: color ? 72 : 32, bottom: line && categories.length > 24 ? 56 : 8, containLabel: true },
          tooltip: { ...(base(theme, palette).tooltip as object), trigger: "axis", axisPointer: { type: line ? "line" : "shadow" } },
          xAxis: horizontal ? values : cats,
          yAxis: horizontal ? cats : values,
          dataZoom: line && categories.length > 24 ? [{ type: "slider", height: 18, bottom: 8 }, { type: "inside" }] : undefined,
          series: series.map((name, i) => ({
            name: name ?? enc.y.label,
            type: line ? "line" : "bar",
            color: seriesColor(theme, i),
            barMaxWidth: 36,
            barGap: "8%",
            itemStyle: line ? undefined : { borderRadius: radius, borderColor: theme.surface, borderWidth: 1 },
            lineStyle: line ? { width: 2 } : undefined,
            symbolSize: 8,
            showSymbol: line && categories.length <= 24,
            areaStyle: line && series.length === 1 ? { opacity: 0.08 } : undefined,
            emphasis: { focus: "series" },
            label: directLabels
              ? { show: true, position: "right", color: theme.muted, fontSize: 12, formatter: (p: any) => fmt(p.value) }
              : undefined,
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
          ...base(theme, palette),
          grid: { left: 8, right: 24, top: 28, bottom: 8, containLabel: true },
          tooltip: { ...(base(theme, palette).tooltip as object), trigger: "axis", axisPointer: { type: "shadow" } },
          xAxis: categoryAxis(theme, rows(viz).map((r) => r.key), { name: enc.x.label, nameLocation: "middle", nameGap: 32 }),
          yAxis: valueAxis(theme, axisName(enc.y)),
          series: [{ type: "bar", barCategoryGap: "4%", color: palette[0],
            itemStyle: { borderRadius: [3, 3, 0, 0] }, data: rows(viz).map((r) => r[enc.y.field] as number) }],
        },
      };
    }
    case "scatter_plot": {
      return {
        kind: "echarts",
        option: {
          ...base(theme, palette),
          grid: { left: 8, right: 24, top: 28, bottom: 8, containLabel: true },
          tooltip: { ...(base(theme, palette).tooltip as object), trigger: "item",
            formatter: (p: any) => `${rows(viz)[p.dataIndex]?.[enc.id?.field ?? "key"]}<br/>${enc.x.label}: ${fmt(p.value[0])}<br/>${enc.y.label}: ${fmt(p.value[1])}` },
          xAxis: { ...valueAxis(theme, axisName(enc.x)), nameLocation: "middle", nameGap: 28, scale: true },
          yAxis: { ...valueAxis(theme, axisName(enc.y)), scale: true },
          series: [{ type: "scatter", symbolSize: 8, color: palette[0],
            itemStyle: { opacity: 0.7, borderColor: theme.surface, borderWidth: 1 },
            data: rows(viz).map((r) => [r[enc.x.field] as number, r[enc.y.field] as number]) }],
        },
      };
    }
    case "network_graph": {
      const { nodes, edges } = viz.data as NetworkData;
      const colorBy = enc.node_color.field;
      const groups = [...new Set(nodes.map((n) => String(n[colorBy])))].sort((a, b) =>
        colorBy === "community" ? Number(a) - Number(b) : a.localeCompare(b),
      );
      const largest = (g: string) =>
        [...nodes].filter((n) => String(n[colorBy]) === g).sort((a, b) => Number(b[enc.node_size.field]) - Number(a[enc.node_size.field]))[0];
      const name = (g: string) =>
        colorBy === "community" ? `${largest(g)?.[enc.node_label.field] ?? g} cluster` : g.replace(/_/g, " ");
      const size = enc.node_size.field;
      const maxWeight = Math.max(1, ...nodes.map((n) => Number(n[size])));
      const maxEdge = Math.max(1, ...edges.map((e) => Number(e[enc.edge_width.field])));
      const labelled = new Set([...nodes].sort((a, b) => Number(b[size]) - Number(a[size])).slice(0, 18).map((n) => n.key));
      return {
        kind: "echarts",
        option: {
          ...base(theme, groups.map((_, i) => seriesColor(theme, i))),
          legend: legend(theme, true),
          tooltip: { ...(base(theme, palette).tooltip as object), trigger: "item",
            formatter: (p: any) => p.dataType === "edge"
              ? `${p.data.sourceName} – ${p.data.targetName}<br/>${fmt(p.data.weight)} shared trials`
              : `<b>${p.name}</b><br/>${fmt(p.value)} trials` },
          series: [{
            type: "graph",
            layout: "force",
            roam: true,
            draggable: true,
            top: 56, bottom: 16, left: 16, right: 16,
            force: { repulsion: 320, edgeLength: [60, 170], gravity: 0.11, friction: 0.2 },
            categories: groups.map((g, i) => ({ name: name(g), itemStyle: { color: seriesColor(theme, i) } })),
            label: { position: "right", fontSize: 12, color: theme.ink },
            labelLayout: { hideOverlap: true },
            lineStyle: { color: theme.faint, curveness: 0.08 },
            emphasis: { focus: "adjacency", label: { show: true }, lineStyle: { width: 4, opacity: 0.9 } },
            data: nodes.map((n) => ({
              id: String(n[enc.node_id.field]),
              name: String(n[enc.node_label.field]),
              value: Number(n[size]),
              category: groups.indexOf(String(n[colorBy])),
              symbolSize: 10 + 34 * Math.sqrt(Number(n[size]) / maxWeight),
              label: { show: labelled.has(n.key) },
              itemStyle: n.is_query_entity
                ? { borderColor: theme.ink, borderWidth: 3 }
                : { borderColor: theme.surface, borderWidth: 2 },
            })),
            links: edges.map((e) => {
              const source = nodes.find((n) => n.key === e[enc.edge_source.field]);
              const target = nodes.find((n) => n.key === e[enc.edge_target.field]);
              return {
                source: String(e[enc.edge_source.field]),
                target: String(e[enc.edge_target.field]),
                value: Number(e[enc.edge_width.field]),
                sourceName: source?.label, targetName: target?.label, weight: e.weight,
                lineStyle: { width: 1 + 7 * (Number(e[enc.edge_width.field]) / maxEdge), opacity: 0.35 },
              };
            }),
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

export interface Table {
  columns: { field: string; label: string; numeric: boolean }[];
  rows: Datum[];
}

/** Every data point as a table (accessibility relief, and for people who prefer numbers). */
export function toTable(viz: Visualization): Table {
  if (viz.type === "network_graph") {
    const { nodes, edges } = viz.data as NetworkData;
    const labels = new Map(nodes.map((n) => [n.key, String(n.label)]));
    return {
      columns: [
        { field: "label", label: "Entity or link", numeric: false },
        { field: "type", label: "Kind", numeric: false },
        { field: "weight", label: "Trials", numeric: true },
        { field: "jaccard", label: "Jaccard", numeric: true },
        { field: "citation_count", label: "Cited trials", numeric: true },
      ],
      rows: [
        ...nodes,
        ...edges.map((e) => ({ ...e, label: `${labels.get(String(e.source))} – ${labels.get(String(e.target))}`, type: "link" })),
      ],
    };
  }
  const fields: Table["columns"] = [];
  for (const channel of Object.values(viz.encoding)) {
    if (!fields.some((f) => f.field === channel.field)) {
      fields.push({ field: channel.field, label: axisName(channel), numeric: channel.type === "quantitative" });
    }
  }
  fields.push({ field: "citation_count", label: "Cited trials", numeric: true });
  return { columns: fields, rows: rows(viz) };
}
