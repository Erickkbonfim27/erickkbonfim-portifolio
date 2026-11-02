import { useEffect } from "react";
import { api } from "../api/client";
import type { Attachment, Entry, Link as EntryLink } from "../api/types";
import { ArrowUpRight, Download } from "../components/Icons";
import { Layout } from "../components/Layout";
import { formatBytes, period } from "../lib/derive";
import { Link } from "../components/Link";
import { useApi } from "../lib/useApi";
import { NotFoundContent } from "./NotFound";

const STATE_LABEL: Record<string, string> = {
  active: "Active",
  standby: "On hold",
  shipped: "Shipped",
  archived: "Archived",
};

function links(details: Record<string, unknown>): EntryLink[] {
  const raw = details.links;
  if (!Array.isArray(raw)) return [];
  return raw.filter(
    (link): link is EntryLink =>
      typeof link === "object" && link !== null && typeof link.label === "string" && typeof link.url === "string",
  );
}

function BackHome() {
  return (
    <Link className="pillbtn pill-line sm" to="/#work">
      ← All work
    </Link>
  );
}

function AttachmentButton({ file }: { file: Attachment }) {
  return (
    <a className="pillbtn pill-dark" href={file.url} download={file.filename}>
      {file.label}
      <span className="mono case-size">{formatBytes(file.size)}</span>
      <span className="ab">
        <Download size={16} />
      </span>
    </a>
  );
}

export function CaseStudyContent({ entry }: { entry: Entry }) {
  const when = period(entry.details);
  const organization = typeof entry.details.organization === "string" ? entry.details.organization : null;
  const state = typeof entry.details.state === "string" ? STATE_LABEL[entry.details.state] : undefined;
  const entryLinks = links(entry.details);

  return (
    <article className="wrap case" aria-labelledby="case-title">
      <header id="top" className="card case-head">
        <div className="card-top">
          <div className="tagrow">
            {organization && <span className="tag acc">{organization}</span>}
            {when && <span className="tag mono">{when}</span>}
            {state && <span className="tag">{state}</span>}
          </div>
          <BackHome />
        </div>
        <h1 id="case-title" className="case-title">
          {entry.title}
        </h1>
        {entry.summary && <p className="case-summary">{entry.summary}</p>}
        {(entryLinks.length > 0 || entry.attachments.length > 0) && (
          <div className="case-actions">
            {entry.attachments.map((file) => (
              <AttachmentButton key={file.url} file={file} />
            ))}
            {entryLinks.map((link) => (
              <a key={link.url} className="pillbtn pill-line" href={link.url} target="_blank" rel="noopener noreferrer">
                {link.label}
                <ArrowUpRight size={14} />
              </a>
            ))}
          </div>
        )}
      </header>

      {entry.body_html && (
        // body_html is rendered and sanitized by the API from an allow-list of nodes.
        <div className="card case-body prose" dangerouslySetInnerHTML={{ __html: entry.body_html }} />
      )}

      {entry.skills.length > 0 && (
        <section className="card case-skills" aria-labelledby="case-skills-title">
          <h2 id="case-skills-title" className="label mono">
            Skills used
          </h2>
          <div className="tagrow">
            {entry.skills.map((skill) => (
              <span key={skill.slug} className="tag">
                {skill.title}
              </span>
            ))}
          </div>
        </section>
      )}
    </article>
  );
}

export function CaseStudy({ slug }: { slug: string }) {
  const state = useApi(`project:${slug}`, (signal) => api.project(slug, { signal }));

  useEffect(() => {
    if (state.data) document.title = `${state.data.title} — Erick Kopak Bonfim`;
  }, [state.data]);

  let content;
  if (state.data) {
    content = <CaseStudyContent entry={state.data} />;
  } else if (state.error?.kind === "not_found") {
    content = <NotFoundContent />;
  } else if (state.error) {
    content = (
      <div id="top" className="wrap case">
        <div className="card case-head" role="alert">
          <h1 className="case-title">Couldn't load this case study.</h1>
          <p className="case-summary">The server didn't answer. Try again in a moment.</p>
          <div className="case-actions">
            <BackHome />
          </div>
        </div>
      </div>
    );
  } else {
    content = (
      <div id="top" className="wrap case" aria-busy="true">
        <div className="card case-head case-loading">
          <span className="label mono">Loading case study…</span>
        </div>
      </div>
    );
  }

  return (
    <Layout base="/" cv={null}>
      {content}
    </Layout>
  );
}
