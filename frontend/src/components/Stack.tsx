import type { StackGroup } from "../content/fallback";
import { useI18n } from "../i18n";

export function Stack({ groups }: { groups: StackGroup[] }) {
  const { t } = useI18n();
  return (
    <section id="stack" className="sec" aria-labelledby="stack-title">
      <div className="wrap">
        <div className="shead reveal">
          <div className="l">
            <p className="eyebrow mono">
              <span className="n">04</span>
              {t.stack.eyebrow}
            </p>
            <h2 id="stack-title" className="h2">
              {t.stack.title}
            </h2>
          </div>
          <p className="r">{t.stack.intro}</p>
        </div>
        <div className="bento">
          {groups.map((group) => (
            <article key={group.key} className={`card${group.dark ? " dark" : ""} scard ${group.span} reveal`}>
              {group.label ? (
                <div className="card-top">
                  <h3 className="sh">{group.title}</h3>
                  <span className="label mono">{group.label}</span>
                </div>
              ) : (
                <h3 className="sh">{group.title}</h3>
              )}
              {group.providers && (
                <div className="providers">
                  {group.providers.map((provider) => (
                    <div key={provider.name} className="provider">
                      <p className="provider-name mono">
                        {provider.name}
                        <span>{provider.services.length}</span>
                      </p>
                      <div className="tagrow">
                        {provider.services.map((service) => (
                          <span key={service} className="tag">
                            {service}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {group.tags.length > 0 && (
                <div className="tagrow">
                  {group.tags.map((tag) => (
                    <span key={tag} className="tag">
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
