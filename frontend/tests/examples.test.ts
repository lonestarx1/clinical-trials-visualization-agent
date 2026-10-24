import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ExampleCard } from "@/components/ExampleCard";
import { askUrl, pagerLabel, positionOf, statusWords, step, type Example, type ExampleSummary } from "@/lib/examples";
import { LIGHT } from "@/lib/theme";

const row = (n: number): ExampleSummary => ({ n, question: `q${n}`, status: "ok", title: `t${n}` });
// 1..5 with 3 missing, like a run whose last answers aren't saved yet.
const LIST = [1, 2, 4, 5].map(row);

describe("the pager", () => {
  it("opens the example named in the URL", () => {
    expect(positionOf(LIST, "4")).toBe(2);
    expect(positionOf(LIST, "1")).toBe(0);
  });

  it("falls back to the next saved example for a gap, the last past the end, the first for junk", () => {
    expect(positionOf(LIST, "3")).toBe(2);
    expect(positionOf(LIST, "99")).toBe(3);
    expect(positionOf(LIST, null)).toBe(0);
    expect(positionOf(LIST, "abc")).toBe(0);
    expect(positionOf(LIST, "0")).toBe(0);
  });

  it("moves one at a time and stops at both ends", () => {
    expect(step(1, 1, LIST.length)).toBe(2);
    expect(step(1, -1, LIST.length)).toBe(0);
    expect(step(0, -1, LIST.length)).toBe(0);
    expect(step(3, 1, LIST.length)).toBe(3);
  });

  it("shows the example's number out of the highest one", () => {
    expect(pagerLabel(LIST, 2)).toBe("4 / 5");
    expect(pagerLabel(LIST, 0)).toBe("1 / 5");
  });
});

describe("asking an example again", () => {
  it("links to the question page in live mode", () => {
    expect(askUrl("Lung cancer & COVID-19?")).toBe("/?q=Lung%20cancer%20%26%20COVID-19%3F&mode=live");
  });
});

describe("a card without a chart", () => {
  const theme = LIGHT;
  const example: Example = {
    n: 73, question: "What will the weather be in Seoul tomorrow?", status: "out_of_scope", visualization: null,
    unique_trials: null, reason: "This tool only plans ClinicalTrials.gov queries, not weather forecasts.",
    suggestion: "How many clinical trials are recruiting in Seoul?",
  };

  it("says the status in plain words, with the reason and the suggestion, and draws no chart", () => {
    const html = renderToStaticMarkup(createElement(ExampleCard, { example, theme }));
    expect(html).toContain(example.question);
    expect(html).toContain(statusWords("out_of_scope"));
    expect(html).toContain(example.reason);
    expect(html).toContain(example.suggestion);
    expect(html).not.toContain('class="chart"');
    expect(html).toContain(`href="${askUrl(example.question).replace(/&/g, "&amp;")}"`);
  });

  it("leaves out a missing reason or suggestion", () => {
    const html = renderToStaticMarkup(createElement(ExampleCard, {
      example: { ...example, status: "no_matching_trials", reason: null, suggestion: null }, theme,
    }));
    expect(html).toContain(statusWords("no_matching_trials"));
    expect(html).not.toContain("Try instead");
    expect(html).not.toContain("null");
  });

  it("has words for every status", () => {
    for (const s of ["out_of_scope", "no_matching_trials", "could_not_interpret", "rejected"] as const)
      expect(statusWords(s)).not.toMatch(/_/);
  });
});
