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
  /** The body in order: server-rendered HTML runs and structured blocks. */
  body: Segment[];
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

// --- structured blocks (backend: content/domain/blocks.py) ---------------------

export interface Image {
  src: string;
  alt: string;
}

export type Tone = "default" | "accent" | "muted";

export interface BlockData {
  facts: { items: { label: string; text: string }[] };
  metrics: { items: { value: string; label: string; note?: string }[] };
  gallery: { layout?: "grid" | "strip" | "feature"; items: (Image & { caption?: string; wide?: boolean })[] };
  timeline: {
    style?: "list" | "roadbook";
    title?: string;
    items: {
      when: string;
      title: string;
      text?: string;
      place?: string;
      tag?: string;
      image?: Image;
      link?: Link;
    }[];
  };
  diagram: {
    title?: string;
    width: number;
    height: number;
    groups?: { id: string; label: string; x: number; y: number; w: number; h: number; tone?: Tone }[];
    nodes: { id: string; label: string; sub?: string; x: number; y: number; w?: number; h?: number; tone?: Tone }[];
    edges?: { from: string; to: string; label?: string; dashed?: boolean; flow?: boolean }[];
    steps?: { title: string; text: string; focus?: string[] }[];
  };
  logos: {
    title?: string;
    note?: string;
    groups: { title: string; items: { name: string; logo?: string; url?: string; note?: string }[] }[];
  };
  cases: { items: { title: string; tag?: string; parts: { label: string; text: string }[] }[] };
  quote: { text: string; author: string; role?: string; url?: string };
  map: {
    src: string;
    attribution: string;
    metrics: { key: string; label: string; note?: string; low?: string; high?: string }[];
    caption?: string;
    legend?: { low: string; high: string };
  };
}

export type BlockKind = keyof BlockData;

export type Block = { [K in BlockKind]: { type: "block"; kind: K; data: BlockData[K] } }[BlockKind];

export type Segment = { type: "html"; html: string } | Block;

// --- search ------------------------------------------------------------------

export interface SearchHit {
  entry_id: string;
  kind: string;
  slug: string;
  title: string;
  heading: string;
  text: string;
  score: number;
}

export interface Ranked {
  slug: string;
  title: string;
  heading: string;
  score: number;
}

export interface Explained {
  query: string;
  hits: SearchHit[];
  dense: Ranked[];
  sparse: Ranked[];
  steps: { name: string; ms: number }[];
  degraded: boolean;
}

// --- the site's agent (POST /api/chat, Server-Sent Events) ---------------------

export interface AgentStep {
  name: string;
  ms: number;
  detail: Record<string, unknown>;
}

export interface Citation {
  n: number;
  title: string;
  heading: string;
  kind: string;
  slug: string;
}

export interface AgentAnswer {
  text: string;
  citations: Citation[];
  stop: string;
  usage: { input_tokens: number; output_tokens: number; cost: number; ms: number };
}

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

export type AgentEvent = { kind: "step"; data: AgentStep } | { kind: "answer"; data: AgentAnswer } | { kind: "error"; data: { message: string } };
