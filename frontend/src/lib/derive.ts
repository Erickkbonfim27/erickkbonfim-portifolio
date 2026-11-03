// Pure mapping from API data to what the sections render, with the handoff copy as
// the fallback for anything missing. No React here: this is what the tests pin down.

import type { Attachment, Availability, Entry, Lang, Profile, Skill, SkillCategory } from "../api/types";
import { FALLBACK, type ExperienceRow, type LearningCard, type StackGroup, type WorkSlug, type WorkText } from "../content/fallback";
import { MESSAGES } from "../i18n/messages";

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

/** "2026-05" -> "MAY 2026" (or "MAI 2026"). Anything else is returned as is, or null. */
export function formatMonth(value: unknown, lang: Lang = "en"): string | null {
  const raw = text(value);
  if (!raw) return null;
  const match = /^(\d{4})-(\d{2})$/.exec(raw);
  if (!match) return raw;
  const month = MESSAGES[lang].dates.months[Number(match[2]) - 1];
  return month ? `${month} ${match[1]}` : raw;
}

function titleCaseMonth(value: unknown, lang: Lang): string | null {
  const formatted = formatMonth(value, lang);
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
/** A contract that overlaps a company Erick founded: say so, instead of leaving two jobs
 * with the same dates unexplained. */
function contractFlag(entry: Entry, entries: Entry[], lang: Lang): string | undefined {
  if (entry.details.employment !== "contract") return undefined;
  const copy = MESSAGES[lang].experience;
  const [start, end] = [text(entry.details.start) ?? "", text(entry.details.end) ?? "9999-12"];
  const founded = entries.find(
    (other) =>
      other !== entry &&
      other.details.employment === "founder" &&
      (text(other.details.start) ?? "") <= end &&
      (text(other.details.end) ?? "9999-12") >= start,
  );
  const organization = founded && text(founded.details.organization);
  return organization ? copy.inParallel(organization) : copy.contract;
}

export function experienceRows(entries: Entry[] | null | undefined, lang: Lang = "en"): ExperienceRow[] {
  if (!entries || entries.length === 0) return FALLBACK[lang].experience;
  return entries.map((entry) => {
    const start = formatMonth(entry.details.start, lang);
    const end = formatMonth(entry.details.end, lang);
    const now = !end;
    const when = start ? `${start} — ${end ?? MESSAGES[lang].dates.now}` : (end ?? "");
    return {
      key: entry.slug,
      when,
      now,
      company: text(entry.details.organization) ?? entry.title,
      role: entry.title,
      desc: entry.summary,
      flag: contractFlag(entry, entries, lang),
    };
  });
}

function educationCard(entry: Entry, now: Date, lang: Lang): LearningCard {
  const copy = MESSAGES[lang].learning;
  const start = year(entry.details.start);
  const end = year(entry.details.end);
  const period = start ? ` · ${start}${end ? ` — ${end}` : ""}` : "";
  const endMonth = text(entry.details.end);
  const inProgress = !endMonth || endMonth > currentMonth(now);
  const institution = text(entry.details.institution) ?? "";
  return {
    key: entry.slug,
    label: `${copy.education}${period}`,
    title: entry.title,
    meta: inProgress ? `${institution} · ${copy.inProgress}` : institution,
    live: false,
  };
}

function certificateCard(entry: Entry, lang: Lang): LearningCard {
  const issued = titleCaseMonth(entry.details.issued, lang);
  const completed = MESSAGES[lang].learning.completed;
  return {
    key: entry.slug,
    label: issued ? `${completed} · ${issued}` : completed,
    title: entry.title,
    meta: entry.summary || (text(entry.details.issuer) ?? ""),
    live: false,
  };
}

function studyCard(entry: Entry, lang: Lang): LearningCard {
  return {
    key: entry.slug,
    label: MESSAGES[lang].learning.studying,
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
  lang: Lang = "en",
): LearningCard[] {
  const fallback = FALLBACK[lang].learning;
  const firstEducation = education?.[0];
  const firstCertificate = certificates?.[0];
  const current = studies?.find((s) => s.details.progress === "in_progress");
  return [
    firstEducation ? educationCard(firstEducation, now, lang) : fallback.education,
    firstCertificate ? certificateCard(firstCertificate, lang) : fallback.certificate,
    current ? studyCard(current, lang) : fallback.study,
  ];
}

interface GroupSpec {
  key: "ai" | "backend" | "data" | "cloud" | "practice";
  label: boolean;
  dark: boolean;
  span: "s6" | "s3";
  categories: SkillCategory[];
}

const GROUPS: GroupSpec[] = [
  { key: "ai", label: true, dark: true, span: "s6", categories: ["ai"] },
  { key: "backend", label: false, dark: false, span: "s6", categories: ["language", "framework"] },
  { key: "data", label: false, dark: false, span: "s6", categories: ["data"] },
  { key: "cloud", label: false, dark: false, span: "s3", categories: ["cloud"] },
  { key: "practice", label: false, dark: false, span: "s3", categories: ["practice", "tool"] },
];

/** Skills grouped into the handoff's cards, in API order; empty groups are dropped. */
export function stackGroups(skills: Skill[] | null | undefined, lang: Lang = "en"): StackGroup[] {
  if (!skills || skills.length === 0) return FALLBACK[lang].stack;
  const titles = MESSAGES[lang].stackGroups;
  return GROUPS.map((group) => ({
    key: group.key,
    title: titles[group.key],
    label: group.label ? titles.core : null,
    dark: group.dark,
    span: group.span,
    tags: skills.filter((s) => group.categories.includes(s.category)).map((s) => s.title),
  })).filter((group) => group.tags.length > 0);
}

export function workText(slug: WorkSlug, entry: Entry | null | undefined, lang: Lang = "en"): WorkText {
  const fallback = FALLBACK[lang].work[slug];
  if (!entry) return fallback;
  return { title: entry.title || fallback.title, summary: entry.summary || fallback.summary };
}

/** Text of the hero status pill. Unknown (no profile yet, or API down) keeps the handoff copy. */
export function availabilityText(availability: Availability | null | undefined, lang: Lang = "en"): string {
  const copy = MESSAGES[lang].availability;
  return availability?.status === "not_looking" ? copy.closed : copy.open;
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
export function period(details: Record<string, unknown>, lang: Lang = "en"): string | null {
  const start = formatMonth(details.start, lang);
  const end = formatMonth(details.end, lang);
  if (!start && !end) return null;
  if (!start || start === end) return start ?? end;
  return `${start} — ${end ?? MESSAGES[lang].dates.now}`;
}
