// Which image the app runs: exactly its own version (ghcr.io/marcopatzelt/crewcut:<version>, pushed for a v* tag), or
// :edge for a development build (a version with a suffix, such as the CI builds 0.1.0-dev.42, or an unpackaged run).
export const IMAGE = "ghcr.io/marcopatzelt/crewcut";
export const RELEASES = "https://github.com/marcopatzelt/crewcut/releases";

export function imageTag(version: string, packaged: boolean, override?: string): string {
  if (override && /^[\w.-]{1,128}$/.test(override)) return override;
  return packaged && /^\d+\.\d+\.\d+$/.test(version) ? version : "edge";
}
