import { CaseStudy } from "./pages/CaseStudy";
import { Home } from "./pages/Home";
import { Mcp } from "./pages/Mcp";
import { NotFound } from "./pages/NotFound";
import { matchRoute, usePathname } from "./lib/router";

export function App() {
  const route = matchRoute(usePathname());
  if (route.name === "home") return <Home />;
  if (route.name === "case") return <CaseStudy key={route.slug} slug={route.slug} />;
  if (route.name === "mcp") return <Mcp />;
  return <NotFound />;
}
