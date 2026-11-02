import { describe, expect, it } from "vitest";
import {
  AVAILABILITY_CLOSED,
  AVAILABILITY_OPEN,
  FALLBACK_EXPERIENCE,
  FALLBACK_LEARNING,
  FALLBACK_STACK,
  FALLBACK_WORK,
} from "../src/content/fallback";
import {
  availabilityText,
  cvAttachment,
  experienceRows,
  formatBytes,
  formatMonth,
  isOpen,
  learningCards,
  period,
  stackGroups,
  workText,
} from "../src/lib/derive";
import { buildCells } from "../src/lib/parcels";
import { entry, profile, skill } from "./helpers";

const NOV_2026 = new Date(2026, 10, 2);

describe("fallback copy", () => {
  it("has the factual fixes: Loopia ended, no one is 'now'", () => {
    expect(FALLBACK_EXPERIENCE[0]).toMatchObject({ company: "Loopia", when: "MAY 2026 — OCT 2026", now: false });
    expect(FALLBACK_EXPERIENCE.every((row) => !row.now)).toBe(true);
    expect(JSON.stringify(FALLBACK_WORK)).not.toContain("80M");
  });
});

describe("experienceRows", () => {
  it("falls back to the handoff copy when the API has nothing", () => {
    expect(experienceRows(null)).toBe(FALLBACK_EXPERIENCE);
    expect(experienceRows([])).toBe(FALLBACK_EXPERIENCE);
  });

  it("maps entries; only an entry without end date is now", () => {
    const rows = experienceRows([
      entry({ slug: "next", title: "AI Engineer", summary: "Agents.", details: { organization: "Next", start: "2026-12" } }),
      entry({ slug: "loopia", title: "Software engineer", details: { organization: "Loopia", start: "2026-05", end: "2026-10" } }),
      entry({ slug: "x", title: "Role only", details: {} }),
    ]);
    expect(rows[0]).toEqual({ key: "next", when: "DEC 2026 — NOW", now: true, company: "Next", role: "AI Engineer", desc: "Agents." });
    expect(rows[1]).toMatchObject({ when: "MAY 2026 — OCT 2026", now: false, company: "Loopia" });
    expect(rows[2]).toMatchObject({ when: "", company: "Role only" });
  });
});

describe("learningCards", () => {
  it("falls back slot by slot", () => {
    expect(learningCards(null, null, null, NOV_2026)).toEqual([
      FALLBACK_LEARNING.education,
      FALLBACK_LEARNING.certificate,
      FALLBACK_LEARNING.study,
    ]);
    const cert = entry({ kind: "certificate", slug: "c", title: "LangSmith", summary: "", details: { issuer: "LangChain", issued: "2026-10" } });
    const [education, certificate, study] = learningCards([], [cert], [entry({ details: { progress: "done" } })], NOV_2026);
    expect(education).toBe(FALLBACK_LEARNING.education);
    expect(certificate).toEqual({ key: "c", label: "Completed · Oct 2026", title: "LangSmith", meta: "LangChain", live: false });
    expect(study).toBe(FALLBACK_LEARNING.study);
  });

  it("marks education in progress until its end month", () => {
    const ongoing = entry({ kind: "education", slug: "pucrs", title: "Data & AI", details: { institution: "PUCRS", start: "2026-04", end: "2028-04" } });
    const done = entry({ kind: "education", slug: "u", title: "Comms", details: { institution: "UNIFEBE", start: "2010-01", end: "2012-12" } });
    const noDates = entry({ kind: "education", slug: "n", title: "Course", details: { institution: "X" } });
    expect(learningCards([ongoing], null, null, NOV_2026)[0]).toMatchObject({ label: "Education · 2026 — 2028", meta: "PUCRS · in progress" });
    expect(learningCards([done], null, null, NOV_2026)[0]).toMatchObject({ label: "Education · 2010 — 2012", meta: "UNIFEBE" });
    expect(learningCards([noDates], null, null, NOV_2026)[0]).toMatchObject({ label: "Education", meta: "X · in progress" });
  });

  it("uses the study in progress as the live card", () => {
    const study = entry({ kind: "study", slug: "deep", title: "Deep Agents", summary: "", details: { progress: "in_progress", author: "LangChain" } });
    expect(learningCards(null, null, [study], NOV_2026)[2]).toEqual({ key: "deep", label: "Studying now", title: "Deep Agents", meta: "LangChain", live: true });
  });
});

describe("stackGroups", () => {
  it("falls back when there are no skills", () => {
    expect(stackGroups(undefined)).toBe(FALLBACK_STACK);
    expect(stackGroups([])).toBe(FALLBACK_STACK);
  });

  it("groups by category into the handoff cards and drops empty groups", () => {
    const groups = stackGroups([
      skill("LangGraph", "ai"),
      skill("Python", "language"),
      skill("FastAPI", "framework"),
      skill("Qdrant", "data"),
      skill("Evals", "practice"),
    ]);
    expect(groups.map((g) => [g.key, g.tags, g.span, g.dark])).toEqual([
      ["ai", ["LangGraph"], "s6", true],
      ["backend", ["Python", "FastAPI"], "s6", false],
      ["data", ["Qdrant"], "s6", false],
      ["practice", ["Evals"], "s3", false],
    ]);
    expect(groups[0]?.label).toBe("Core");
  });
});

describe("small helpers", () => {
  it("workText overrides title and summary only when present", () => {
    expect(workText("rhye", null)).toBe(FALLBACK_WORK.rhye);
    expect(workText("rhye", entry({ title: "Rhye 2", summary: "" }))).toEqual({ title: "Rhye 2", summary: FALLBACK_WORK.rhye.summary });
  });

  it("availability keeps the handoff copy unless explicitly not looking", () => {
    expect(availabilityText(null)).toBe(AVAILABILITY_OPEN);
    expect(availabilityText({ status: "unknown", open: false, updated_at: null })).toBe(AVAILABILITY_OPEN);
    expect(availabilityText({ status: "not_looking", open: false, updated_at: null })).toBe(AVAILABILITY_CLOSED);
    expect(isOpen({ status: "not_looking", open: false, updated_at: null })).toBe(false);
    expect(isOpen(undefined)).toBe(true);
  });

  it("finds the CV by label", () => {
    const cv = { label: " cv ", filename: "cv.pdf", url: "https://f/cv.pdf", content_type: "application/pdf", size: 1 };
    expect(cvAttachment(profile({ attachments: [{ ...cv, label: "Portfolio" }, cv] }))).toBe(cv);
    expect(cvAttachment(profile())).toBeNull();
    expect(cvAttachment(null)).toBeNull();
  });

  it("formats months, periods and sizes", () => {
    expect(formatMonth("2026-05")).toBe("MAY 2026");
    expect(formatMonth("2026-13")).toBe("2026-13");
    expect(formatMonth("spring")).toBe("spring");
    expect(formatMonth(7)).toBeNull();
    expect(period({ start: "2024-03", end: "2025-10" })).toBe("MAR 2024 — OCT 2025");
    expect(period({ start: "2024-03" })).toBe("MAR 2024 — NOW");
    expect(period({ end: "2025-10" })).toBe("OCT 2025");
    expect(period({})).toBeNull();
    expect([formatBytes(500), formatBytes(2048), formatBytes(3.5 * 1024 * 1024)]).toEqual(["500 B", "2 KB", "3.5 MB"]);
  });

  it("builds the deterministic 14×8 parcel map", () => {
    const cells = buildCells();
    expect(cells).toHaveLength(112);
    expect(buildCells().map((c) => c.cls)).toEqual(cells.map((c) => c.cls));
    expect(cells.filter((c) => c.cls.includes("road")).length).toBeGreaterThan(14);
  });
});
