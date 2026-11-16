import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "./styles/tokens.css";
import "./styles/app.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";

const params = new URLSearchParams(window.location.search);
const theme = params.get("theme");
if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <StrictMode>
      <App demo={params.get("demo") === "1"} />
    </StrictMode>,
  );
}
