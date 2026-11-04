// The handoff copy for every data-driven part of the page, in both languages. Rendered
// while the API loads, and whenever it is unreachable or has nothing published yet, so
// the site always looks complete. Factual updates to the handoff (Loopia ended in Oct
// 2026, an unverifiable revenue metric removed) are applied here.

import type { Lang } from "../api/types";

export interface ExperienceRow {
  key: string;
  when: string;
  now: boolean;
  company: string;
  role: string;
  desc: string;
  /** "Service provider, in parallel with Vizzion": why two jobs share dates. */
  flag?: string | undefined;
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

export type WorkSlug = "vizzion" | "vizzion-data-platform" | "loopia" | "rhye" | "silpi" | "reuni-challenge";

export interface Fallback {
  experience: ExperienceRow[];
  learning: Record<"education" | "certificate" | "study", LearningCard>;
  stack: StackGroup[];
  work: Record<WorkSlug, WorkText>;
}

export const EMAIL = "erickkbonfim@gmail.com";
export const LINKEDIN = "https://www.linkedin.com/in/erick-kopak-bonfim-rhai";
export const GITHUB = "https://github.com/Erickkbonfim27";

const TAGS = {
  ai: ["LangGraph", "LangChain", "LlamaIndex", "LangSmith", "Langfuse", "RAG", "Hybrid search", "Evals", "LoRA fine-tuning", "Deep Agents"],
  backend: ["Python", "TypeScript", "Node.js", "Java · Spring Boot", "FastAPI", "Django + DRF", "Microservices"],
  data: ["PostgreSQL / PostGIS", "pgvector", "Qdrant", "Elasticsearch", "Pinecone", "Redis", "MongoDB", "BigQuery", "ClickHouse"],
  cloud: ["GCP", "AWS", "CloudFormation", "Pub/Sub", "RabbitMQ"],
  product: ["React", "React Native", "GIS", "Computer vision"],
};

const en: Fallback = {
  experience: [
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
      desc: "Real-estate and urban-planning analysis using ML, computer vision and GIS data, integrating many data sources on GCP. Fine-tuned models with LoRA. 3rd place nationally at PropVentures Lab by Brognoli.",
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
  ],
  learning: {
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
  },
  stack: [
    { key: "ai", title: "Agents & LLMs", label: "Core", dark: true, span: "s6", tags: TAGS.ai },
    { key: "backend", title: "Languages & backend", label: null, dark: false, span: "s6", tags: TAGS.backend },
    { key: "data", title: "Data & search", label: null, dark: false, span: "s6", tags: TAGS.data },
    { key: "cloud", title: "Cloud & messaging", label: null, dark: false, span: "s3", tags: TAGS.cloud },
    { key: "product", title: "Product & geo", label: null, dark: false, span: "s3", tags: TAGS.product },
  ],
  work: {
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
        "People intelligence for small and mid-sized companies: the employee lifecycle in eight journeys, and Aeva, an AI HR business partner that proposes actions a person confirms.",
    },
    silpi: {
      title: "SILPI",
      summary:
        "Management software for long-term care homes for the elderly. As the only developer I owned the architecture: Java and Spring Boot microservices, an Angular web app and a React Native app brought back after two years without updates.",
    },
    "reuni-challenge": {
      title: "Reuni Challenge 2023",
      summary:
        "A team of 13 from UNIFEBE and one programmer: a platform to find skilled construction labour and spot irregular construction with satellite data.",
    },
  },
};

const pt: Fallback = {
  experience: [
    {
      key: "loopia",
      when: "MAI 2026 — OUT 2026",
      now: false,
      company: "Loopia",
      role: "Engenheiro de software · agentes de IA",
      desc: "Integrações com Nuvemshop, Magazord e Loja Integrada, recuperação de carrinho abandonado e agentes de IA no WhatsApp. Langfuse para tracing e evals, busca híbrida, AWS com CloudFormation.",
    },
    {
      key: "silpi",
      when: "JUN 2024 — MAI 2026",
      now: false,
      company: "SILPI",
      role: "Engenheiro de software · full stack",
      desc: "Software de gestão para casas de repouso, com microsserviços em Java/Spring Boot e React Native. Atualizei um app React Native que estava dois anos sem atualização e trabalhei no módulo de franquias.",
    },
    {
      key: "vizzion",
      when: "MAR 2024 — OUT 2025",
      now: false,
      company: "Vizzion",
      role: "Cofundador e CTO",
      desc: "Análise imobiliária e urbana com machine learning, visão computacional e dados GIS, integrando diversas fontes de dados na GCP. Fiz fine-tuning de modelos com LoRA. 3º lugar nacional no PropVentures Lab da Brognoli.",
    },
    {
      key: "coneng",
      when: "SET 2023 — MAR 2024",
      now: false,
      company: "ConEng",
      role: "Cofundador e CTO",
      desc: "Nasceu no hackathon Reuni Challenge como um marketplace de profissionais da construção, e depois ganhou ferramentas de orçamento. Node.js, TypeScript, MongoDB. Time de 8 pessoas. Mais tarde pivotamos a empresa para a Vizzion.",
    },
    {
      key: "grupo-mello",
      when: "2019 — 2023",
      now: false,
      company: "Grupo Mello",
      role: "Gerente de marketing e comercial",
      desc: "Cuidei do marketing e das vendas de 7 empresas de um grupo de construção e incorporação, com um time de 6 pessoas. Uma vez vendemos um prédio inteiro num único fim de semana de lançamento.",
    },
  ],
  learning: {
    education: {
      key: "pucrs",
      label: "Formação · 2026 — 2028",
      title: "Tecnologia em banco de dados, análise de dados e IA",
      meta: "PUCRS · em andamento",
      live: false,
    },
    certificate: {
      key: "langsmith",
      label: "Concluído · Out 2026",
      title: "Building Reliable Agents with LangSmith",
      meta: "Curso sobre tracing e avaliação de agentes.",
      live: false,
    },
    study: {
      key: "deep-agents",
      label: "Estudando agora",
      title: "Deep Agents · LangChain",
      meta: "Curso sobre agentes que planejam, delegam para subagentes e gerenciam o próprio contexto.",
      live: true,
    },
  },
  stack: [
    { key: "ai", title: "Agentes e LLMs", label: "Principal", dark: true, span: "s6", tags: TAGS.ai },
    { key: "backend", title: "Linguagens e backend", label: null, dark: false, span: "s6", tags: TAGS.backend },
    { key: "data", title: "Dados e busca", label: null, dark: false, span: "s6", tags: TAGS.data },
    { key: "cloud", title: "Cloud e mensageria", label: null, dark: false, span: "s3", tags: TAGS.cloud },
    { key: "product", title: "Produto e geo", label: null, dark: false, span: "s3", tags: TAGS.product },
  ],
  work: {
    vizzion: {
      title: "Vizzion",
      summary:
        "Cofundei a Vizzion e liderei a engenharia. Usávamos machine learning, visão computacional, imagens de satélite e dados GIS para avaliar terrenos e prever como os bairros mudariam em 10 anos.",
    },
    "vizzion-data-platform": {
      title: "Plataforma de dados da Vizzion",
      summary: "Como a plataforma de dados funcionava",
    },
    loopia: {
      title: "Loopia",
      summary:
        "Construí as integrações com Nuvemshop, Magazord e Loja Integrada e trabalhei nos agentes de IA que atendem clientes no WhatsApp.",
    },
    rhye: {
      title: "Rhye",
      summary:
        "People intelligence para pequenas e médias empresas: o ciclo do colaborador em oito jornadas, e a Aeva, uma BP de RH com IA que propõe ações que uma pessoa confirma.",
    },
    silpi: {
      title: "SILPI",
      summary:
        "Software de gestão para instituições de longa permanência para idosos. Como único desenvolvedor, respondi pela arquitetura: microsserviços em Java e Spring Boot, app web em Angular e um app React Native atualizado depois de dois anos parado.",
    },
    "reuni-challenge": {
      title: "Reuni Challenge 2023",
      summary:
        "Um time de 13 pessoas da UNIFEBE e um programador: uma plataforma para achar mão de obra qualificada para obras e identificar construções irregulares com dados de satélite.",
    },
  },
};

export const FALLBACK: Record<Lang, Fallback> = { en, pt };
