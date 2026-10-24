import { describe, expect, it } from "vitest";
import { answerUrl, fastHint, modeFrom, sourceLabel } from "@/lib/mode";
import { EMPTY_ASK, toRequestBody } from "@/lib/request";

describe("the request", () => {
  it("asks for fast mode only when it's picked; live is the server's default", () => {
    expect(toRequestBody({ ...EMPTY_ASK, query: "q", mode: "fast" }).mode).toBe("fast");
    expect(toRequestBody({ ...EMPTY_ASK, query: "q" })).not.toHaveProperty("mode");
  });
});

describe("shareable links", () => {
  it("keep the mode, so a fast answer's link asks in fast mode again", () => {
    expect(answerUrl("breast cancer by phase", "fast")).toBe("?q=breast%20cancer%20by%20phase&mode=fast");
    expect(answerUrl("breast cancer by phase", "live")).toBe("?q=breast%20cancer%20by%20phase");
    expect(answerUrl("q", "fast", "PHASE2")).toBe("?q=q&mode=fast&d=PHASE2");
  });

  it("read the mode back; anything else is live", () => {
    expect(modeFrom("?q=x&mode=fast")).toBe("fast");
    expect(modeFrom("?q=x")).toBe("live");
    expect(modeFrom("?q=x&mode=turbo")).toBe("live");
  });
});

describe("the answer says where its trials came from", () => {
  it("names the copy and its date for fast answers", () => {
    expect(sourceLabel({ data_source: "fast", data_timestamp: "2026-10-23T09:00:04" }))
      .toBe("Fast: our copy of the Oct 23, 2026 data, checked against ClinicalTrials.gov");
    expect(sourceLabel({ data_source: "live" })).toBe("Live from ClinicalTrials.gov");
    expect(sourceLabel({})).toBe("Live from ClinicalTrials.gov"); // answers saved before fast mode
  });
});

describe("the picker's hint", () => {
  it("is quiet when fast mode is ready, and says what happens otherwise", () => {
    expect(fastHint("ready")).toBeNull();
    expect(fastHint("syncing")).toMatch(/answered live/);
    expect(fastHint("not_loaded")).toMatch(/answered live/);
    expect(fastHint("off")).toMatch(/off/);
  });
});
