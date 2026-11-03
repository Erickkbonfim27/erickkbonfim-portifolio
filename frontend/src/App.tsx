import { CaseStudy } from "./pages/CaseStudy";
import { Home } from "./pages/Home";
import { Integrations } from "./pages/Integrations";
import { Mcp } from "./pages/Mcp";
import { NotFound } from "./pages/NotFound";
import { matchRoute, usePathname } from "./lib/router";

export function App() {
  const route = matchRoute(usePathname());
  if (route.name === "home") return <Home />;
  if (route.name === "case") return <CaseStudy key={`${route.lang}:${route.slug}`} slug={route.slug} />;
  if (route.name === "mcp") return <Mcp />;
  if (route.name === "integrations") return <Integrations key={route.lang} />;
  return <NotFound />;
}
