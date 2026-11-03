import type { ExperienceRow, LearningCard } from "../content/fallback";
import { useI18n } from "../i18n";

interface ExperienceProps {
  rows: ExperienceRow[];
  learning: LearningCard[];
}

export function Experience({ rows, learning }: ExperienceProps) {
  const { t } = useI18n();
  return (
    <section id="experience" className="sec" aria-labelledby="xp-title">
      <div className="wrap">
        <div className="shead reveal">
          <div className="l">
            <p className="eyebrow mono">
              <span className="n">03</span>
              {t.experience.eyebrow}
            </p>
            <h2 id="xp-title" className="h2">
              {t.experience.title}
            </h2>
          </div>
          <p className="r">{t.experience.intro}</p>
        </div>
        <div className="bento">
          <div className="card s12 reveal" style={{ overflow: "hidden" }}>
            <ol className="xplist">
              {rows.map((row, index) => (
                <li key={row.key} className="xp">
                  <span className="ix mono">{String(index + 1).padStart(2, "0")}</span>
                  <p className={row.now ? "when now mono" : "when mono"}>
                    {row.now && <span className="live" aria-hidden="true" />}
                    {row.when}
                  </p>
                  <h3 className="co">
                    {row.company}
                    <span className="role">{row.role}</span>
                  </h3>
                  <p className="desc">
                    {row.flag && <span className="tag mono xp-flag">{row.flag}</span>}
                    {row.desc}
                  </p>
                </li>
              ))}
            </ol>
          </div>
          {learning.map((card) => (
            <article key={card.key} className={card.live ? "card dark lcard s4 lw reveal" : "card lcard s4 reveal"}>
              {card.live ? (
                <span className="label mono" style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                  <span className="live" aria-hidden="true" />
                  {card.label}
                </span>
              ) : (
                <span className="label mono">{card.label}</span>
              )}
              <h3 className="lt">{card.title}</h3>
              <p className="lm">{card.meta}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
