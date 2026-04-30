import { environment } from '../../environments/environment';

/**
 * Use for links to Django-stored uploads when the SPA runs on another origin/port.
 * Absolute http(s) URLs are returned as-is; root-relative `/media/...` is prefixed
 * with {@link environment.apiUrl}.
 */
export function resolveApiFileUrl(raw: string | null | undefined): string | null {
  if (!raw?.trim()) {
    return null;
  }
  const s = raw.trim();
  if (s.startsWith('http://') || s.startsWith('https://')) {
    return s;
  }
  const base = environment.apiUrl.replace(/\/$/, '');
  const path = s.startsWith('/') ? s : `/${s}`;
  return `${base}${path}`;
}
