import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
// Astryx (MIT): its reset and the prebuilt component styles sit in CSS layers, so every unlayered rule of ours wins.
import "@astryxdesign/core/reset.css";
import "@astryxdesign/core/astryx.css";
import "./styles/tokens.css";
import "./styles/astryx-theme.css";
import "./styles/app.css";
import "./styles/window.css";
import "./styles/motion.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { applyPlatformClass, initTheme } from "./lib/platform";

const params = new URLSearchParams(window.location.search);
applyPlatformClass();
initTheme(params.get("theme"));

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
