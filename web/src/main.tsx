import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "./styles/tokens.css";
import "./styles/app.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { applyPlatformClass, initTheme } from "./lib/platform";

const params = new URLSearchParams(window.location.search);
applyPlatformClass();
initTheme(params.get("theme"));

// ?demo=1 shows demo data as a still scene; with &play=1 the demo plays its short scripted sequence once.
const demo = params.get("demo") === "1";
const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <StrictMode>
      <App demo={demo} play={demo && params.get("play") === "1"} />
    </StrictMode>,
  );
}
