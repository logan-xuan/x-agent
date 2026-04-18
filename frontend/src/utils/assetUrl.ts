const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "::1"]);

function isBrowser(): boolean {
  return typeof window !== "undefined" && Boolean(window.location);
}

function currentOrigin(): string | null {
  if (!isBrowser()) {
    return null;
  }
  return window.location.origin;
}

function currentHostname(): string | null {
  if (!isBrowser()) {
    return null;
  }
  return window.location.hostname;
}

export function normalizeAssetUrl(rawUrl?: string | null): string | undefined {
  if (!rawUrl || !isBrowser()) {
    return rawUrl ?? undefined;
  }

  try {
    const parsed = new URL(rawUrl, currentOrigin() ?? undefined);
    const hostname = currentHostname();

    if (
      parsed.pathname.startsWith("/api/v1/assets/") &&
      LOCAL_HOSTS.has(parsed.hostname) &&
      hostname &&
      LOCAL_HOSTS.has(hostname)
    ) {
      return `${parsed.pathname}${parsed.search}${parsed.hash}`;
    }

    return parsed.toString();
  } catch {
    return rawUrl;
  }
}
