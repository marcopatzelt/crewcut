export interface PrompterRequest { id: string; episode: string; created: number; status: string }

export function parsePrompterRequest(value: unknown, filename: string, now = Date.now()): PrompterRequest | null {
  if (!value || typeof value !== "object") return null;
  const request = value as PrompterRequest;
  if (!/^[a-f0-9]{32}$/.test(request.id) || filename !== `${request.id}.json` ||
      typeof request.episode !== "string" || !/^[A-Za-z0-9_-]+$/.test(request.episode) ||
      !Number.isFinite(request.created) || request.created * 1000 > now + 5000 || request.status !== "pending") return null;
  return request;
}

export function prompterUrl(token: unknown, port: number): string {
  if (typeof token !== "string" || !/^[A-Za-z0-9_-]{8,128}$/.test(token)) throw new Error("Invalid teleprompter link.");
  return `http://127.0.0.1:${port}/p/${token}`;
}
