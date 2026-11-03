import { useEffect, useState } from "react";
import type { BlockData } from "../../api/types";
import { useI18n } from "../../i18n";
import { useInView } from "../../lib/useInView";
import { ArrowUpRight } from "../Icons";

export function Facts({ data }: { data: BlockData["facts"] }) {
  const [ref, seen] = useInView<HTMLDListElement>();
  return (
    <dl ref={ref} className={`blk-facts reveal${seen ? " in" : ""}`}>
      {data.items.map((item) => (
        <div key={item.label} className="fact">
          <dt className="label mono">{item.label}</dt>
          <dd>{item.text}</dd>
        </div>
      ))}
    </dl>
  );
}

const NUMBER = /^([^\d]*)(\d[\d.,]*)(.*)$/;

function reducedMotion(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Counts up to the number at the start of `value` ("150", "3º", "+100") once it is seen. */
function CountUp({ value, run }: { value: string; run: boolean }) {
  const match = NUMBER.exec(value);
  const target = match ? Number(match[2]?.replace(/[.,]/g, "")) : NaN;
  const animate = match !== null && Number.isFinite(target) && !reducedMotion();
  const [progress, setProgress] = useState(0);
  useEffect(() => {
    if (!run || !animate) return;
    const start = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / 900);
      setProgress(t);
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [run, animate]);
  const shown =
    !animate || progress >= 1 ? value : `${match?.[1] ?? ""}${Math.round(target * (1 - (1 - progress) ** 3))}${match?.[3] ?? ""}`;
  return (
    <>
      <span aria-hidden="true">{shown}</span>
      <span className="sr">{value}</span>
    </>
  );
}

export function Metrics({ data }: { data: BlockData["metrics"] }) {
  const [ref, seen] = useInView<HTMLUListElement>(0.4);
  return (
    <ul ref={ref} className="blk-metrics">
      {data.items.map((item) => (
        <li key={item.label} className="metric">
          <span className="metric-value">
            <CountUp value={item.value} run={seen} />
          </span>
          <span className="metric-label">{item.label}</span>
          {item.note && <span className="metric-note mono">{item.note}</span>}
        </li>
      ))}
    </ul>
  );
}

export function Quote({ data }: { data: BlockData["quote"] }) {
  const cite = (
    <>
      <span className="quote-author">{data.author}</span>
      {data.role && <span className="quote-role">{data.role}</span>}
    </>
  );
  return (
    <figure className="blk-quote">
      <blockquote>
        <p>{data.text}</p>
      </blockquote>
      <figcaption>
        {data.url ? (
          <a href={data.url} target="_blank" rel="noopener noreferrer" className="quote-link">
            {cite}
            <ArrowUpRight size={14} />
          </a>
        ) : (
          cite
        )}
      </figcaption>
    </figure>
  );
}

export function Cases({ data }: { data: BlockData["cases"] }) {
  return (
    <div className="blk-cases">
      {data.items.map((item) => (
        <article key={item.title} className="case-card">
          <header>
            {item.tag && <span className="tag mono">{item.tag}</span>}
            <h3>{item.title}</h3>
          </header>
          <dl>
            {item.parts.map((part) => (
              <div key={part.label}>
                <dt className="label mono">{part.label}</dt>
                <dd>{part.text}</dd>
              </div>
            ))}
          </dl>
        </article>
      ))}
    </div>
  );
}

const PER_GROUP = 12;

export function Logos({ data }: { data: BlockData["logos"] }) {
  const { t } = useI18n();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const total = data.groups.reduce((sum, group) => sum + group.items.length, 0);
  const needle = query.trim().toLowerCase();
  const groups = data.groups
    .map((group) => ({
      ...group,
      shown: needle ? group.items.filter((item) => item.name.toLowerCase().includes(needle)) : group.items,
    }))
    .filter((group) => group.shown.length > 0);

  return (
    <section className="blk-logos" aria-label={data.title}>
      {(data.title || total > PER_GROUP * 2) && (
        <div className="logos-head">
          {data.title && (
            <h3>
              {data.title} <span className="mono logos-count">{total}</span>
            </h3>
          )}
          {total > PER_GROUP * 2 && (
            <input
              className="logos-filter"
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={t.blocks.filter}
              aria-label={t.blocks.filter}
            />
          )}
        </div>
      )}
      {data.note && <p className="logos-note">{data.note}</p>}
      {groups.length === 0 && <p className="logos-note">{t.blocks.noMatch}</p>}
      {groups.map((group) => {
        const expanded = needle !== "" || open[group.title] === true;
        const items = expanded ? group.shown : group.shown.slice(0, PER_GROUP);
        return (
          <div key={group.title} className="logo-group">
            <h4 className="label mono">
              {group.title} · {group.items.length}
            </h4>
            <ul className="logo-grid">
              {items.map((item) => {
                const inner = (
                  <>
                    {item.logo ? (
                      <img src={item.logo} alt="" loading="lazy" width={28} height={28} />
                    ) : (
                      <span className="logo-mono mono" aria-hidden="true">
                        {item.name.slice(0, 2)}
                      </span>
                    )}
                    <span className="logo-text">
                      <span className="logo-name">{item.name}</span>
                      {item.note && <span className="logo-sub mono">{item.note}</span>}
                    </span>
                  </>
                );
                return (
                  <li key={item.name}>
                    {item.url ? (
                      <a className="logo-card" href={item.url} target="_blank" rel="noopener noreferrer nofollow">
                        {inner}
                      </a>
                    ) : (
                      <span className="logo-card">{inner}</span>
                    )}
                  </li>
                );
              })}
            </ul>
            {!needle && group.shown.length > PER_GROUP && (
              <button
                type="button"
                className="tlink logos-more"
                aria-expanded={expanded}
                onClick={() => setOpen({ ...open, [group.title]: !expanded })}
              >
                {expanded ? t.blocks.showLess : t.blocks.showAll(group.shown.length)}
              </button>
            )}
          </div>
        );
      })}
    </section>
  );
}
