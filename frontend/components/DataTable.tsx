import { toTable } from "@/lib/adapter";
import type { Datum, Visualization } from "@/lib/types";

const show = (v: unknown) =>
  typeof v === "number" ? v.toLocaleString("en-US", { maximumFractionDigits: 3 }) : v === null || v === undefined ? "–" : String(v);

export function DataTable({ viz, onSelect }: { viz: Visualization; onSelect: (d: Datum) => void }) {
  const table = toTable(viz);
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>{table.columns.map((c) => <th key={c.field} className={c.numeric ? "num" : ""}>{c.label}</th>)}<th /></tr>
        </thead>
        <tbody>
          {table.rows.map((row) => (
            <tr key={row.key}>
              {table.columns.map((c) => <td key={c.field} className={c.numeric ? "num" : ""}>{show(row[c.field])}</td>)}
              <td><button className="link" onClick={() => onSelect(row)} disabled={!row.citation_count}>Trials</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
