import { Layout } from "../components/Layout";
import { Link } from "../components/Link";
import { useI18n } from "../i18n";

export function NotFoundContent() {
  const { t, to } = useI18n();
  return (
    <div id="top" className="wrap case">
      <div className="card case-head">
        <span className="label mono">404</span>
        <h1 className="case-title">{t.notFound.title}</h1>
        <p className="case-summary">{t.notFound.text}</p>
        <div className="case-actions">
          <Link className="pillbtn pill-dark" to={to("/")}>
            {t.notFound.back}
          </Link>
        </div>
      </div>
    </div>
  );
}

export function NotFound() {
  const { t } = useI18n();
  return (
    <Layout onHome={false} cv={null} title={t.titles.notFound}>
      <NotFoundContent />
    </Layout>
  );
}
