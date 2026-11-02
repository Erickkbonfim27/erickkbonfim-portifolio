// Shapes of the public API. Source of truth: docs/public-api.md.

export type Lang = "en" | "pt";

export interface Link {
  label: string;
  url: string;
}

export interface Attachment {
  label: string;
  filename: string;
  url: string;
  content_type: string;
  size: number;
}

export interface SkillRef {
  slug: string;
  title: string;
}

export type EntryKind = "experience" | "project" | "education" | "certificate" | "study" | "writing";

export interface Entry {
  kind: EntryKind;
  slug: string;
  title: string;
  summary: string;
  tags: string[];
  details: Record<string, unknown>;
  body_html: string;
  skills: SkillRef[];
  attachments: Attachment[];
  published_at: string;
  updated_at: string;
}

export type AvailabilityStatus = "open" | "not_looking" | "unknown";

export interface Availability {
  status: AvailabilityStatus;
  open: boolean;
  updated_at: string | null;
}

export interface Profile {
  name: string;
  headline: string;
  summary: string;
  bio_html: string;
  location: string | null;
  email: string | null;
  links: Link[];
  availability: Availability;
  attachments: Attachment[];
}

export type SkillCategory = "language" | "framework" | "ai" | "data" | "cloud" | "practice" | "tool";

export interface Skill {
  slug: string;
  title: string;
  category: SkillCategory;
  evidence: { kind: string; slug: string; title: string }[];
}

export interface ContactRequest {
  from: string;
  contact: string;
  brief: string;
  company?: string;
  lang: Lang;
  website: string;
}

export interface ContactAccepted {
  id: string;
}
