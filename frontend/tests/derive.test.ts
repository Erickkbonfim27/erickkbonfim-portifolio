import { describe, expect, it } from "vitest";
import { FALLBACK } from "../src/content/fallback";
import { MESSAGES } from "../src/i18n/messages";
import {
  availabilityText,
  cvAttachment,
  letterAttachment,
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
const { experience: FALLBACK_EXPERIENCE, learning: FALLBACK_LEARNING, stack: FALLBACK_STACK, work: FALLBACK_WORK } = FALLBACK.en;
const { open: AVAILABILITY_OPEN, closed: AVAILABILITY_CLOSED } = MESSAGES.en.availability;

describe("fallback copy", () => {
  it("has the factual fixes in both languages: Loopia ended, no one is 'now'", () => {
    expect(FALLBACK_EXPERIENCE[0]).toMatchObject({ company: "Loopia", when: "MAY 2026 — OCT 2026", now: false });
    expect(FALLBACK.pt.experience[0]).toMatchObject({ company: "Loopia", when: "MAI 2026 — OUT 2026", now: false });
    for (const lang of ["en", "pt"] as const) {
      expect(FALLBACK[lang].experience.every((row) => !row.now)).toBe(true);
      expect(JSON.stringify(FALLBACK[lang])).not.toContain("80M");
    }
  });

  it("has the same cards in both languages", () => {
    const keys = (lang: "en" | "pt") => ({
      experience: FALLBACK[lang].experience.map((row) => row.key),
      stack: FALLBACK[lang].stack.map((group) => [group.key, group.tags]),
      work: Object.keys(FALLBACK[lang].work),
    });
    expect(keys("pt")).toEqual(keys("en"));
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

  it("explains a contract that ran alongside a company Erick founded", () => {
    const silpi = entry({ slug: "silpi", details: { organization: "SILPI", start: "2024-06", end: "2026-05", employment: "contract" } });
    const vizzion = entry({ slug: "vizzion", details: { organization: "Vizzion", start: "2024-03", end: "2025-10", employment: "founder" } });
    const later = entry({ slug: "later", details: { organization: "Later", start: "2027-01", employment: "founder" } });
    expect(experienceRows([silpi, vizzion], "pt")[0]?.flag).toBe("Prestação de serviço, em paralelo à Vizzion");
    expect(experienceRows([silpi, later])[0]?.flag).toBe("Service provider");
    const open = entry({ slug: "open", details: { organization: "Open", employment: "contract" } });
    const founderNoDates = entry({ slug: "f", details: { organization: "F", employment: "founder" } });
    expect(experienceRows([open, founderNoDates])[0]?.flag).toBe("Service provider, in parallel with F");
    expect(experienceRows([vizzion])[0]?.flag).toBeUndefined();
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
      ["practice", ["Evals"], "s6", false],
    ]);
    expect(groups[0]?.label).toBe("Core");
  });

  it("shows each cloud provider with its services, without repeating them as tags", () => {
    const groups = stackGroups([
      { ...skill("AWS", "cloud"), services: ["Lambda", "SQS"] },
      { ...skill("GCP", "cloud"), services: ["Cloud Run", "Pub/Sub"] },
      skill("Pub/Sub", "cloud"),
      skill("RabbitMQ", "cloud"),
    ]);
    expect(groups).toEqual([
      expect.objectContaining({
        key: "cloud",
        span: "s12",
        tags: ["RabbitMQ"],
        providers: [
          { name: "AWS", services: ["Lambda", "SQS"] },
          { name: "GCP", services: ["Cloud Run", "Pub/Sub"] },
        ],
      }),
    ]);
    const plain = stackGroups([skill("AWS", "cloud")]);
    expect(plain[0]).toEqual(expect.objectContaining({ tags: ["AWS"] }));
    expect(plain[0]?.providers).toBeUndefined();
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
    const en = { ...cv, label: "CV (EN)" };
    const pt = { ...cv, label: "CV (PT)" };
    expect(cvAttachment(profile({ attachments: [en, pt] }), "pt")).toBe(pt);
    expect(cvAttachment(profile({ attachments: [en, pt] }), "en")).toBe(en);
    expect(cvAttachment(profile({ attachments: [cv, pt] }), "en")).toBe(cv);
    const letter = { ...cv, label: "Letter (PT)" };
    expect(letterAttachment(profile({ attachments: [pt, letter] }), "pt")).toBe(letter);
    expect(letterAttachment(profile({ attachments: [pt, letter] }), "en")).toBeNull();
    expect(cvAttachment(null)).toBeNull();
  });

  it("speaks Portuguese when asked", () => {
    expect(formatMonth("2026-05", "pt")).toBe("MAI 2026");
    expect(period({ start: "2024-03" }, "pt")).toBe("MAR 2024 — ATUAL");
    const loopia = entry({ slug: "loopia", title: "Engenheiro", details: { organization: "Loopia", start: "2026-05", end: "2026-10" } });
    expect(experienceRows([loopia], "pt")[0]).toMatchObject({ when: "MAI 2026 — OUT 2026" });
    expect(experienceRows(null, "pt")).toBe(FALLBACK.pt.experience);
    const cert = entry({ kind: "certificate", slug: "c", title: "LangSmith", summary: "", details: { issued: "2026-10" } });
    const ongoing = entry({ kind: "education", slug: "p", title: "Dados e IA", details: { institution: "PUCRS", start: "2026-04" } });
    const study = entry({ kind: "study", slug: "d", title: "Deep Agents", summary: "", details: { progress: "in_progress" } });
    expect(learningCards([ongoing], [cert], [study], NOV_2026, "pt").map((card) => [card.label, card.meta])).toEqual([
      ["Formação · 2026", "PUCRS · em andamento"],
      ["Concluído · Out 2026", ""],
      ["Estudando agora", ""],
    ]);
    expect(stackGroups([skill("LangGraph", "ai")], "pt")[0]).toMatchObject({ title: "Agentes e LLMs", label: "Principal" });
    expect(workText("rhye", null, "pt")).toBe(FALLBACK.pt.work.rhye);
    expect(availabilityText(null, "pt")).toBe("Aberto a vagas de AI Engineer");
  });

  it("formats months, periods and sizes", () => {
    expect(formatMonth("2026-05")).toBe("MAY 2026");
    expect(formatMonth("2026-13")).toBe("2026-13");
    expect(formatMonth("spring")).toBe("spring");
    expect(formatMonth(7)).toBeNull();
    expect(period({ start: "2024-03", end: "2025-10" })).toBe("MAR 2024 — OCT 2025");
    expect(period({ start: "2024-03" })).toBe("MAR 2024 — NOW");
    expect(period({ start: "2023-09", end: "2023-09" })).toBe("SEP 2023");
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
