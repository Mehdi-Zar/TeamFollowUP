import { describe, it, expect } from "vitest";
import { roadmapRag, trendRag, qhToRag, ragClass, badgeClass, dotClass } from "./labels";

describe("status → RAG mappings", () => {
  it("maps roadmap statuses", () => {
    expect(roadmapRag("blocked")).toBe("red");
    expect(roadmapRag("at_risk")).toBe("amber");
    expect(roadmapRag("on_track")).toBe("green");
    expect(roadmapRag("done")).toBe("green");
  });
  it("maps KPI trends", () => {
    expect(trendRag("missed")).toBe("red");
    expect(trendRag("under_pressure")).toBe("amber");
    expect(trendRag("on_target")).toBe("green");
  });
  it("maps quarter health", () => {
    expect(qhToRag("blocked")).toBe("red");
    expect(qhToRag("at_risk")).toBe("amber");
    expect(qhToRag("on_track")).toBe("green");
  });
  it("derives CSS classes from RAG", () => {
    expect(ragClass("red")).toBe("red");
    expect(badgeClass("amber")).toBe("badge-orange");
    expect(dotClass("green")).toBe("dot-green");
  });
});
