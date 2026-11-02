import { Layout } from "../components/Layout";
import { Link } from "../components/Link";

export function NotFoundContent() {
  return (
    <div id="top" className="wrap case">
      <div className="card case-head">
        <span className="label mono">404</span>
        <h1 className="case-title">Nothing here.</h1>
        <p className="case-summary">The page you followed doesn't exist, or it moved.</p>
        <div className="case-actions">
          <Link className="pillbtn pill-dark" to="/">
            Back to the portfolio
          </Link>
        </div>
      </div>
    </div>
  );
}

export function NotFound() {
  return (
    <Layout base="/" cv={null}>
      <NotFoundContent />
    </Layout>
  );
}
