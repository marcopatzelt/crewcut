import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "../styles/tokens.css";
import "./prompter.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import type { PrompterControl } from "../api/types";
import { makeDemo } from "../demo/fixtures";
import { applyPlatformClass } from "../lib/platform";
import { DEFAULT_CONTROL, httpSource, Prompter, tokenFromLocation, type PrompterSource } from "./Prompter";

function demoSource(): PrompterSource {
  const { script } = makeDemo();
  let control: PrompterControl = { ...DEFAULT_CONTROL };
  return {
    shared: false,
    script: async () => script,
    getControl: async () => control,
    setControl: async (c) => {
      control = c;
    },
  };
}

const params = new URLSearchParams(window.location.search);
const token = tokenFromLocation(window.location);
const source = params.get("demo") === "1" ? demoSource() : token ? httpSource(token) : null;
document.documentElement.dataset.theme = "dark";
applyPlatformClass(); // the system font on an iPhone, Inter elsewhere (DESIGN.md rule 5)

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <StrictMode>
      <Prompter source={source} remote={params.get("remote") === "1"} />
    </StrictMode>,
  );
}
