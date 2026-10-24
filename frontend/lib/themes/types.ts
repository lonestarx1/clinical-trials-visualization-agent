// A colour theme: UI tokens (become CSS variables) + chart colours (ECharts).
// Every theme must pass: text contrast (ink >= 12:1, ink2 >= 7:1, muted >= 4.5:1, action >= 4.5:1
// on bg, surface and surface2; markInk on mark >= 7:1; actionInk on action >= 4.5:1) and the
// chart palette validated against chart.surface with the dataviz checker.

export interface UiTokens {
  bg: string;          // page background
  surface: string;     // cards, drawer, inputs
  surface2: string;    // subtle fills inside cards (record lines, table header, segmented control)
  ink: string;         // primary text
  ink2: string;        // secondary text (summaries, method notes)
  muted: string;       // minor metadata only
  line: string;        // borders
  lineStrong: string;  // input borders
  action: string;      // buttons, links, active states
  actionHover: string;
  actionInk: string;   // text on action
  actionSoft: string;  // chips, selected backgrounds
  mark: string;        // evidence highlighter
  markInk: string;     // text on mark
  danger: string;
  dangerSoft: string;
  warn: string;
  warnSoft: string;
  shadow: string;      // CSS box-shadow value for cards
}

export interface ChartTokens {
  palette: readonly string[]; // 8 categorical colours, fixed order, validated against `surface`
  other: string;              // series past the eighth (neutral)
  surface: string;            // must equal ui.surface
  ink: string;
  muted: string;              // axis and value labels (>= 7:1 on surface)
  faint: string;              // network edges
  grid: string;               // grid lines
  highlight: string;
}

export interface ThemeDef {
  id: string;        // kebab-case, unique
  name: string;      // shown in the dropdown, e.g. "Glacier"
  mode: "light" | "dark";
  ui: UiTokens;
  chart: ChartTokens;
}
