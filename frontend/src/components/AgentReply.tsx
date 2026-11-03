import type { ReactNode } from "react";
import type { AgentAnswer, Citation } from "../api/types";
import { useI18n } from "../i18n";
import { hitHref } from "../lib/search";
import { Link } from "./Link";

/** The agent's answer: its paragraphs, with each [n] linked to the page it came from. */
export function AgentReply({ answer }: { answer: AgentAnswer }) {
  const { t, to } = useI18n();
  const byN = new Map(answer.citations.map((c) => [c.n, c]));
  const href = (c: Citation) => hitHref({ kind: c.kind, slug: c.slug }, to);

  const inline = (text: string): ReactNode[] =>
    text.split(/(\[\d{1,2}\])/g).map((part, index) => {
      const n = /^\[(\d{1,2})\]$/.exec(part)?.[1];
      const cited = n ? byN.get(Number(n)) : undefined;
      if (!cited) return part;
      const target = href(cited);
      const label = `${cited.title}${cited.heading ? ` · ${cited.heading}` : ""}`;
      return target ? (
        <Link key={index} className="cite mono" to={target} title={label}>
          {cited.n}
        </Link>
      ) : (
        <span key={index} className="cite mono" title={label}>
          {cited.n}
        </span>
      );
    });

  return (
    <div className="bubble site agent-reply">
      {answer.text.split(/\n{2,}/).map((paragraph, index) => (
        <p key={index}>{inline(paragraph)}</p>
      ))}
      {answer.citations.length > 0 && (
        <div className="sources">
          <span className="label mono">{t.assistant.sources}</span>
          <ol>
            {answer.citations.map((c) => {
              const target = href(c);
              const label = (
                <>
                  <strong>{c.title}</strong>
                  {c.heading && <span> · {c.heading}</span>}
                </>
              );
              return (
                <li key={c.n}>
                  <span className="mono">{c.n}</span> {target ? <Link to={target}>{label}</Link> : label}
                </li>
              );
            })}
          </ol>
        </div>
      )}
    </div>
  );
}
