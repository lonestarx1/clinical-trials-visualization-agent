"use client";

import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import type { ECharts } from "echarts";
import { datumAt, isHorizontal, toChart } from "@/lib/adapter";
import type { Theme } from "@/lib/theme";
import type { Datum, Visualization } from "@/lib/types";

export interface ChartHandle { toPng: () => string | null }

function height(viz: Visualization): number {
  if (viz.type === "network_graph") return 620;
  if (isHorizontal(viz) && Array.isArray(viz.data)) {
    const bars = new Set(viz.data.map((r) => r[viz.encoding.x.field])).size;
    const series = viz.encoding.color ? new Set(viz.data.map((r) => r[viz.encoding.color!.field])).size : 1;
    return Math.max(320, Math.min(1400, bars * (18 + 12 * series) + 90));
  }
  return 440;
}

export const Chart = forwardRef<ChartHandle, { viz: Visualization; theme: Theme; onSelect: (d: Datum) => void }>(
  function Chart({ viz, theme, onSelect }, ref) {
    const box = useRef<HTMLDivElement>(null);
    const instance = useRef<ECharts | null>(null);
    const chart = toChart(viz, theme);

    useImperativeHandle(ref, () => ({
      toPng: () => instance.current?.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: theme.surface }) ?? null,
    }), [theme]);

    useEffect(() => {
      if (chart.kind !== "echarts" || !box.current) return;
      let disposed = false;
      let observer: ResizeObserver | null = null;
      import("echarts").then((echarts) => {
        if (disposed || !box.current) return;
        const ec = echarts.init(box.current, undefined, { renderer: "canvas" });
        instance.current = ec;
        ec.setOption(chart.option, true);
        ec.on("click", (event) => {
          const datum = datumAt(viz, event as never);
          if (datum) onSelect(datum);
        });
        observer = new ResizeObserver(() => ec.resize());  // follows the card, never the window
        observer.observe(box.current);
      });
      return () => {
        disposed = true;
        observer?.disconnect();
        instance.current?.dispose();
        instance.current = null;
      };
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [viz, theme]);

    if (chart.kind === "metric") {
      const row = (viz.data as Datum[])[0];
      return (
        <button className="metric" onClick={() => row && onSelect(row)}>
          <span className="metric-value">{chart.value.toLocaleString()}</span>
          <span className="metric-label">{chart.unit ?? chart.label}</span>
          <span className="metric-hint">Show the trials</span>
        </button>
      );
    }
    return (
      <div ref={box} className="chart" style={{ height: height(viz) }} role="img"
        aria-label={`${viz.title}. Use the table view for the values.`} />
    );
  },
);
