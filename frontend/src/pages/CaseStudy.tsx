import { api } from "../api/client";
import type { Attachment, Entry, Link as EntryLink } from "../api/types";
import { Body } from "../components/blocks/Body";
import { ArrowUpRight, Download } from "../components/Icons";
import { Layout } from "../components/Layout";
import { formatBytes, period } from "../lib/derive";
import { Link } from "../components/Link";
import { useI18n } from "../i18n";
import { useApi } from "../lib/useApi";
import { NotFoundContent } from "./NotFound";

function links(details: Record<string, unknown>): EntryLink[] {
  const raw = details.links;
  if (!Array.isArray(raw)) return [];
  return raw.filter(
    (link): link is EntryLink =>
      typeof link === "object" && link !== null && typeof link.label === "string" && typeof link.url === "string",
  );
}

function BackHome() {
  const { t, to } = useI18n();
  return (
    <Link className="pillbtn pill-line sm" to={to("/#work")}>
      {t.case.allWork}
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
  const { lang, t } = useI18n();
  const when = period(entry.details, lang);
  const organization = typeof entry.details.organization === "string" ? entry.details.organization : null;
  const state = typeof entry.details.state === "string" ? t.case.states[entry.details.state] : undefined;
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

      {(entry.body?.length || entry.body_html) && (
        <div className="card case-body">
          <Body segments={entry.body} fallbackHtml={entry.body_html} />
        </div>
      )}

      {entry.skills.length > 0 && (
        <section className="card case-skills" aria-labelledby="case-skills-title">
          <h2 id="case-skills-title" className="label mono">
            {t.case.skills}
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
  const { lang, t } = useI18n();
  const state = useApi(`project:${lang}:${slug}`, (signal) => api.project(slug, lang, { signal }));

  let title = t.titles.home;
  let content;
  if (state.data) {
    title = `${state.data.title} — ${t.titles.caseSuffix}`;
    content = <CaseStudyContent entry={state.data} />;
  } else if (state.error?.kind === "not_found") {
    title = t.titles.notFound;
    content = <NotFoundContent />;
  } else if (state.error) {
    content = (
      <div id="top" className="wrap case">
        <div className="card case-head" role="alert">
          <h1 className="case-title">{t.case.errorTitle}</h1>
          <p className="case-summary">{t.case.errorText}</p>
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
          <span className="label mono">{t.case.loading}</span>
        </div>
      </div>
    );
  }

  return (
    <Layout onHome={false} title={title}>
      {content}
    </Layout>
  );
}
