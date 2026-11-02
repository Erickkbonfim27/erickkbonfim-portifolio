// The handoff copy for every data-driven part of the page. Rendered while the API
// loads, and whenever it is unreachable or has nothing published yet, so the site
// always looks complete. Factual updates to the handoff (Loopia ended in Oct 2026,
// the unverifiable R$80M metric removed) are applied here.

export interface ExperienceRow {
  key: string;
  when: string;
  now: boolean;
  company: string;
  role: string;
  desc: string;
}

export interface LearningCard {
  key: string;
  label: string;
  title: string;
  meta: string;
  live: boolean;
}

export interface StackGroup {
  key: string;
  title: string;
  label: string | null;
  dark: boolean;
  span: "s6" | "s3";
  tags: string[];
}

export interface WorkText {
  title: string;
  summary: string;
}

export const EMAIL = "erickkbonfim@gmail.com";
export const LINKEDIN = "https://www.linkedin.com/in/erick-kopak-bonfim-rhai";
export const GITHUB = "https://github.com/Erickkbonfim27";
export const AVAILABILITY_OPEN = "Open to AI Engineer roles";
export const AVAILABILITY_CLOSED = "Not looking for new roles";

export const FALLBACK_EXPERIENCE: ExperienceRow[] = [
  {
    key: "loopia",
    when: "MAY 2026 — OCT 2026",
    now: false,
    company: "Loopia",
    role: "Software engineer · AI agents",
    desc: "Nuvemshop, Magazord and Loja Integrada integrations, abandoned-cart recovery and AI agents on WhatsApp. Langfuse for tracing and evals, hybrid search, AWS with CloudFormation.",
  },
  {
    key: "silpi",
    when: "JUN 2024 — MAY 2026",
    now: false,
    company: "SILPI",
    role: "Software engineer · full stack",
    desc: "Management software for elderly care homes, built on Java/Spring Boot microservices and React Native. Updated a React Native app that had gone two years without updates, and worked on the franchise module.",
  },
  {
    key: "vizzion",
    when: "MAR 2024 — OCT 2025",
    now: false,
    company: "Vizzion",
    role: "Co-founder & CTO",
    desc: "Real-estate and urban-planning analysis using ML, computer vision and GIS data. Integrated 100+ data APIs on GCP and fine-tuned models with LoRA. 3rd place nationally at PropVentures Lab by Brognoli.",
  },
  {
    key: "coneng",
    when: "SEP 2023 — MAR 2024",
    now: false,
    company: "ConEng",
    role: "Co-founder & CTO",
    desc: "Started at the Reuni Challenge hackathon as a marketplace for construction workers, then added estimating and budgeting tools. Node.js, TypeScript, MongoDB. Team of 8. We later pivoted the company into Vizzion.",
  },
  {
    key: "grupo-mello",
    when: "2019 — 2023",
    now: false,
    company: "Grupo Mello",
    role: "Marketing & commercial manager",
    desc: "Ran marketing and sales for 7 businesses in a construction and real-estate group, with a team of 6. We once sold out an apartment building in a single launch weekend.",
  },
];

export const FALLBACK_LEARNING: Record<"education" | "certificate" | "study", LearningCard> = {
  education: {
    key: "pucrs",
    label: "Education · 2026 — 2028",
    title: "Database technology, data analytics & AI",
    meta: "PUCRS · in progress",
    live: false,
  },
  certificate: {
    key: "langsmith",
    label: "Completed · Oct 2026",
    title: "Building Reliable Agents with LangSmith",
    meta: "Course on tracing and evaluating agents.",
    live: false,
  },
  study: {
    key: "deep-agents",
    label: "Studying now",
    title: "Deep Agents · LangChain",
    meta: "Course on agents that plan, delegate to sub-agents and manage their own context.",
    live: true,
  },
};

export const FALLBACK_STACK: StackGroup[] = [
  {
    key: "ai",
    title: "Agents & LLMs",
    label: "Core",
    dark: true,
    span: "s6",
    tags: ["LangGraph", "LangChain", "LlamaIndex", "LangSmith", "Langfuse", "RAG", "Hybrid search", "Evals", "LoRA fine-tuning", "Deep Agents"],
  },
  {
    key: "backend",
    title: "Languages & backend",
    label: null,
    dark: false,
    span: "s6",
    tags: ["Python", "TypeScript", "Node.js", "Java · Spring Boot", "FastAPI", "Django + DRF", "Microservices"],
  },
  {
    key: "data",
    title: "Data & search",
    label: null,
    dark: false,
    span: "s6",
    tags: ["PostgreSQL / PostGIS", "pgvector", "Qdrant", "Elasticsearch", "Pinecone", "Redis", "MongoDB", "BigQuery", "ClickHouse"],
  },
  {
    key: "cloud",
    title: "Cloud & messaging",
    label: null,
    dark: false,
    span: "s3",
    tags: ["GCP", "AWS", "CloudFormation", "Pub/Sub", "RabbitMQ"],
  },
  {
    key: "product",
    title: "Product & geo",
    label: null,
    dark: false,
    span: "s3",
    tags: ["React", "React Native", "GIS", "Computer vision"],
  },
];

export type WorkSlug = "vizzion" | "vizzion-data-platform" | "loopia" | "rhye";

export const FALLBACK_WORK: Record<WorkSlug, WorkText> = {
  vizzion: {
    title: "Vizzion",
    summary:
      "I co-founded Vizzion and ran engineering. We used machine learning, computer vision, satellite imagery and GIS data to assess land and forecast how neighborhoods would change over 10 years.",
  },
  "vizzion-data-platform": {
    title: "Vizzion data platform",
    summary: "How the data platform worked",
  },
  loopia: {
    title: "Loopia",
    summary:
      "I built the Nuvemshop, Magazord and Loja Integrada integrations and worked on the AI agents that answer customers on WhatsApp.",
  },
  rhye: {
    title: "Rhye",
    summary:
      "An HR platform for companies with 50 to 300 people. It screens résumés, scores candidate fit, schedules interviews, automates onboarding and drafts feedback for candidates.",
  },
};
