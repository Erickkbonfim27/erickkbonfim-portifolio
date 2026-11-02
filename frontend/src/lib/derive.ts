// Pure mapping from API data to what the sections render, with the handoff copy as
// the fallback for anything missing. No React here: this is what the tests pin down.

import type { Attachment, Availability, Entry, Profile, Skill, SkillCategory } from "../api/types";
import {
  AVAILABILITY_CLOSED,
  AVAILABILITY_OPEN,
  FALLBACK_EXPERIENCE,
  FALLBACK_LEARNING,
  FALLBACK_STACK,
  FALLBACK_WORK,
  type ExperienceRow,
  type LearningCard,
  type StackGroup,
  type WorkSlug,
  type WorkText,
} from "../content/fallback";

const MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

/** "2026-05" -> "MAY 2026". Anything else is returned as is, or null. */
export function formatMonth(value: unknown): string | null {
  const raw = text(value);
  if (!raw) return null;
  const match = /^(\d{4})-(\d{2})$/.exec(raw);
  if (!match) return raw;
  const month = MONTHS[Number(match[2]) - 1];
  return month ? `${month} ${match[1]}` : raw;
}

function titleCaseMonth(value: unknown): string | null {
  const formatted = formatMonth(value);
  if (!formatted) return null;
  return formatted.replace(/^([A-Z])([A-Z]{2})/, (_, a: string, b: string) => a + b.toLowerCase());
}

function year(value: unknown): string | null {
  const raw = text(value);
  return raw ? raw.slice(0, 4) : null;
}

function currentMonth(now: Date): string {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

/** An experience is "now" only when the API says it has no end date. */
export function experienceRows(entries: Entry[] | null | undefined): ExperienceRow[] {
  if (!entries || entries.length === 0) return FALLBACK_EXPERIENCE;
  return entries.map((entry) => {
    const start = formatMonth(entry.details.start);
    const end = formatMonth(entry.details.end);
    const now = !end;
    const when = start ? `${start} — ${end ?? "NOW"}` : (end ?? "");
    return {
      key: entry.slug,
      when,
      now,
      company: text(entry.details.organization) ?? entry.title,
      role: entry.title,
      desc: entry.summary,
    };
  });
}

function educationCard(entry: Entry, now: Date): LearningCard {
  const start = year(entry.details.start);
  const end = year(entry.details.end);
  const period = start ? ` · ${start}${end ? ` — ${end}` : ""}` : "";
  const endMonth = text(entry.details.end);
  const inProgress = !endMonth || endMonth > currentMonth(now);
  const institution = text(entry.details.institution) ?? "";
  return {
    key: entry.slug,
    label: `Education${period}`,
    title: entry.title,
    meta: inProgress ? `${institution} · in progress` : institution,
    live: false,
  };
}

function certificateCard(entry: Entry): LearningCard {
  const issued = titleCaseMonth(entry.details.issued);
  return {
    key: entry.slug,
    label: issued ? `Completed · ${issued}` : "Completed",
    title: entry.title,
    meta: entry.summary || (text(entry.details.issuer) ?? ""),
    live: false,
  };
}

function studyCard(entry: Entry): LearningCard {
  return {
    key: entry.slug,
    label: "Studying now",
    title: entry.title,
    meta: entry.summary || (text(entry.details.author) ?? ""),
    live: true,
  };
}

/** Three slots: the latest education, the latest certificate, and what is being studied
 * now. Each slot falls back to the handoff card on its own. */
export function learningCards(
  education: Entry[] | null | undefined,
  certificates: Entry[] | null | undefined,
  studies: Entry[] | null | undefined,
  now: Date = new Date(),
): LearningCard[] {
  const firstEducation = education?.[0];
  const firstCertificate = certificates?.[0];
  const current = studies?.find((s) => s.details.progress === "in_progress");
  return [
    firstEducation ? educationCard(firstEducation, now) : FALLBACK_LEARNING.education,
    firstCertificate ? certificateCard(firstCertificate) : FALLBACK_LEARNING.certificate,
    current ? studyCard(current) : FALLBACK_LEARNING.study,
  ];
}

interface GroupSpec {
  key: string;
  title: string;
  label: string | null;
  dark: boolean;
  span: "s6" | "s3";
  categories: SkillCategory[];
}

const GROUPS: GroupSpec[] = [
  { key: "ai", title: "Agents & LLMs", label: "Core", dark: true, span: "s6", categories: ["ai"] },
  { key: "backend", title: "Languages & backend", label: null, dark: false, span: "s6", categories: ["language", "framework"] },
  { key: "data", title: "Data & search", label: null, dark: false, span: "s6", categories: ["data"] },
  { key: "cloud", title: "Cloud & messaging", label: null, dark: false, span: "s3", categories: ["cloud"] },
  { key: "practice", title: "Practices & tools", label: null, dark: false, span: "s3", categories: ["practice", "tool"] },
];

/** Skills grouped into the handoff's cards, in API order; empty groups are dropped. */
export function stackGroups(skills: Skill[] | null | undefined): StackGroup[] {
  if (!skills || skills.length === 0) return FALLBACK_STACK;
  return GROUPS.map((group) => ({
    key: group.key,
    title: group.title,
    label: group.label,
    dark: group.dark,
    span: group.span,
    tags: skills.filter((s) => group.categories.includes(s.category)).map((s) => s.title),
  })).filter((group) => group.tags.length > 0);
}

export function workText(slug: WorkSlug, entry: Entry | null | undefined): WorkText {
  const fallback = FALLBACK_WORK[slug];
  if (!entry) return fallback;
  return { title: entry.title || fallback.title, summary: entry.summary || fallback.summary };
}

/** Text of the hero status pill. Unknown (no profile yet, or API down) keeps the handoff copy. */
export function availabilityText(availability: Availability | null | undefined): string {
  if (availability?.status === "not_looking") return AVAILABILITY_CLOSED;
  return AVAILABILITY_OPEN;
}

export function isOpen(availability: Availability | null | undefined): boolean {
  return availability?.status !== "not_looking";
}

/** The CV is the profile attachment labelled "CV". No CV, no link. */
export function cvAttachment(profile: Profile | null | undefined): Attachment | null {
  return profile?.attachments.find((a) => a.label.trim().toLowerCase() === "cv") ?? null;
}

export function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

/** "MAY 2024 — OCT 2025" from any start/end pair in details, or null. */
export function period(details: Record<string, unknown>): string | null {
  const start = formatMonth(details.start);
  const end = formatMonth(details.end);
  if (!start && !end) return null;
  if (!start) return end;
  return `${start} — ${end ?? "NOW"}`;
}
