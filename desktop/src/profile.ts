import { join } from "node:path";

export function profileConfig(name: string | undefined, userData: string, home: string, packaged: boolean) {
  const selected = name || (packaged ? "personal" : "development");
  if (selected !== "personal" && selected !== "development") {
    throw new Error("CREWCUT_PROFILE must be personal or development.");
  }
  const development = selected === "development";
  return {
    development,
    name: selected,
    title: development ? "Crewcut Development" : "Crewcut",
    userData: development ? `${userData}-development` : userData,
    studioDir: join(home, development ? "Crewcut Development" : "Crewcut"),
    projectName: development ? "crewcut-desktop-development" : "crewcut",
    port: development ? 4757 : 4747,
    prompterPort: development ? 4758 : 4748,
  };
}
