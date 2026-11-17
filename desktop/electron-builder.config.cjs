// Packages the desktop app. CI builds it (.github/workflows/desktop.yml), never a laptop. No release is published from
// here (`--publish never`); the GitHub release, and with it the updates, is made by the owner.
// Signing switches itself on with the secrets: CSC_LINK (+ CSC_KEY_PASSWORD) signs, and on a Mac the APPLE_* variables
// notarize. Without CSC_LINK the Mac app gets an ad-hoc signature (Apple silicon starts nothing unsigned), with the
// hardened runtime off, which an ad-hoc signature needs for Electron's frameworks.
const signed = Boolean(process.env.CSC_LINK);
const notarize =
  signed &&
  Boolean(
    (process.env.APPLE_API_KEY && process.env.APPLE_API_KEY_ID && process.env.APPLE_API_ISSUER) ||
      (process.env.APPLE_ID && process.env.APPLE_APP_SPECIFIC_PASSWORD && process.env.APPLE_TEAM_ID),
  );

/** @type {import("electron-builder").Configuration} */
module.exports = {
  appId: "dev.crewcut.desktop",
  productName: "Crewcut",
  copyright: "Copyright 2026 Marco Patzelt (MIT)",
  directories: { output: "release", buildResources: "build" },
  files: ["dist/**", "package.json", "!dist/test/**"],
  extraResources: [
    // the repository's own compose.yaml, unchanged: the app runs the same stack as ./start.sh
    { from: "../compose.yaml", to: "stack/compose.yaml" },
    { from: "stack/desktop.yaml", to: "stack/desktop.yaml" },
    { from: "build/icon.png", to: "icon.png" },
    { from: "build/tray.png", to: "tray.png" },
    { from: "build/tray@2x.png", to: "tray@2x.png" },
  ],
  mac: {
    category: "public.app-category.video",
    icon: "build/icon.png",
    target: [
      { target: "dmg", arch: ["arm64", "x64"] },
      { target: "zip", arch: ["arm64", "x64"] },
    ],
    artifactName: "${productName}-${version}-mac-${arch}.${ext}",
    identity: signed ? undefined : "-",
    hardenedRuntime: signed,
    gatekeeperAssess: false,
    notarize,
  },
  dmg: { artifactName: "${productName}-${version}-mac-${arch}.${ext}" },
  win: {
    icon: "build/icon.png",
    target: [{ target: "nsis", arch: ["x64"] }],
    artifactName: "${productName}-${version}-windows-${arch}.${ext}",
  },
  nsis: { oneClick: true, perMachine: false },
  linux: {
    executableName: "crewcut-desktop", // `crewcut` is the command line of the Python package
    icon: "build/icon.png",
    category: "AudioVideo",
    target: ["AppImage", "deb"],
    artifactName: "${productName}-${version}-linux-${arch}.${ext}",
    maintainer: "Marco Patzelt",
    synopsis: "A crew of AI agents that makes a whole YouTube video",
  },
  publish: [{ provider: "github", owner: "marcopatzelt", repo: "crewcut" }],
};
