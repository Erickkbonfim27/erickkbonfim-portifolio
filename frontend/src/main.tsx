import "@fontsource-variable/sora/index.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "@fontsource/jetbrains-mono/600.css";
import "./styles/handoff.css";
import "./styles/app.css";
import "./styles/blocks.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { startClarity, wantsClarity } from "./lib/clarity";
import { landingRedirect } from "./lib/locale";
import { initTheme } from "./lib/theme";

const root = document.getElementById("root");
if (!root) throw new Error("#root is missing from index.html");

// Before the first render, so neither the language nor the theme flips on screen.
initTheme();
const redirect = landingRedirect(window.location);
if (redirect) window.history.replaceState(null, "", redirect);

if (wantsClarity(window.location, navigator)) startClarity();

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
