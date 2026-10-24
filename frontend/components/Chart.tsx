"use client";

import { useEffect, useRef } from "react";
import type { ECharts } from "echarts";
import { datumAt, toChart } from "@/lib/adapter";
import type { Datum, Visualization } from "@/lib/types";

export function Chart({ viz, onSelect }: { viz: Visualization; onSelect: (d: Datum) => void }) {
  const box = useRef<HTMLDivElement>(null);
  const chart = toChart(viz);

  useEffect(() => {
    if (chart.kind !== "echarts" || !box.current) return;
    let instance: ECharts | null = null;
    let disposed = false;
    const resize = () => instance?.resize();
    import("echarts").then((echarts) => {
      if (disposed || !box.current) return;
      instance = echarts.init(box.current, undefined, { renderer: "canvas" });
      instance.setOption(chart.option, true);
      instance.on("click", (event) => {
        const datum = datumAt(viz, event as never);
        if (datum) onSelect(datum);
      });
      window.addEventListener("resize", resize);
    });
    return () => {
      disposed = true;
      window.removeEventListener("resize", resize);
      instance?.dispose();
    };
    // Re-render only when the visualization changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viz]);

  if (chart.kind === "metric") {
    const row = (viz.data as Datum[])[0];
    return (
      <button className="metric" onClick={() => row && onSelect(row)} title="Show the trials">
        <span className="metric-value">{chart.value.toLocaleString()}</span>
        <span className="metric-label">{chart.unit ?? chart.label}</span>
      </button>
    );
  }
  return <div ref={box} className={viz.type === "network_graph" ? "chart chart-tall" : "chart"} />;
}
