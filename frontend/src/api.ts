// Thin API client: JWT in localStorage, silent refresh, language header, typed helpers.
import { useCallback, useEffect, useState } from 'react';
import { getLang } from './i18n';

const ACCESS = 'fdc.access';
const REFRESH = 'fdc.refresh';
const CLUB = 'fdc.club';

const store = {
  get: (k: string) => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k: string, v: string | null) => { try { v === null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { /* private mode */ } },
};

export class ApiError extends Error {
  constructor(public status: number, public detail: string) { super(detail); }
}

export const auth = {
  loggedIn: () => !!store.get(ACCESS),
  async login(email: string, password: string) {
    const r = await fetch('/api/auth/token/', {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept-Language': getLang() },
      body: JSON.stringify({ email, password }),
    });
    if (!r.ok) throw new ApiError(r.status, 'bad_credentials');
    const d = await r.json();
    store.set(ACCESS, d.access); store.set(REFRESH, d.refresh);
  },
  logout() { store.set(ACCESS, null); store.set(REFRESH, null); store.set(CLUB, null); window.location.href = '/login'; },
  club: () => Number(store.get(CLUB)) || null,
  setClub: (id: number) => store.set(CLUB, String(id)),
};

async function refresh(): Promise<boolean> {
  const token = store.get(REFRESH);
  if (!token) return false;
  const r = await fetch('/api/auth/token/refresh/', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh: token }),
  });
  if (!r.ok) return false;
  const d = await r.json();
  store.set(ACCESS, d.access);
  if (d.refresh) store.set(REFRESH, d.refresh);
  return true;
}

export async function api<T = any>(path: string, init: RequestInit = {}, retry = true): Promise<T> {
  const headers: Record<string, string> = { 'Accept-Language': getLang(), ...(init.headers as Record<string, string> || {}) };
  if (init.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
  const token = store.get(ACCESS);
  if (token) headers.Authorization = `Bearer ${token}`;
  const r = await fetch(`/api/${path.replace(/^\//, '')}`, { ...init, headers });
  if (r.status === 401 && retry && await refresh()) return api<T>(path, init, false);
  if (r.status === 401) { auth.logout(); throw new ApiError(401, 'unauthorised'); }
  if (!r.ok) {
    let detail = r.statusText;
    try { const d = await r.json(); detail = d.detail || Object.values(d).flat().join(' ') || detail; } catch { /* not JSON */ }
    throw new ApiError(r.status, detail);
  }
  return r.status === 204 ? (undefined as T) : r.json();
}

export const clubPath = (p: string) => `clubs/${auth.club()}/${p.replace(/^\//, '')}`;

/** Load data for a component; re-runs when `key` changes. */
export function useApi<T = any>(path: string | null, key: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(!!path);
  const load = useCallback(() => {
    if (!path) return;
    setLoading(true); setError(null);
    api<T>(path).then(setData).catch((e: ApiError) => setError(e.detail)).finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...key]);
  useEffect(() => { load(); }, [load]);
  return { data, error, loading, reload: load, setData };
}

// --- types (only what the screens use) ---
export interface Reason { code: string; value?: number; date?: string }
export interface SquadPlayer {
  player_id: number; name: string; shirt_number: number | null; position: string; level: 'modify' | 'monitor' | 'ready';
  reasons: Reason[]; acwr_distance: number | null; acwr_hsr: number | null; week_distance: number;
  week_change_pct: number | null; last_match_minutes: number; last_session: string;
}
export interface SquadStatus {
  as_of: string; days_since_match: number | null; players: SquadPlayer[];
  last_match: { session_id: number; date: string; name: string } | null;
}
export interface SessionSummary {
  id: number; date: string; start: string; name: string; md: string; type: string; players: number;
  duration: number | null; distance: number | null; hsr: number | null; sprint: number | null;
}
export interface MetricCol { key: string; label: string; short_label: string; unit: string; category: string; aggregation: string }
export interface MetricSetMeta { id: number | null; name: string; display: string; metrics: MetricCol[] }
export interface SessionDetail {
  session: { id: number; date: string; start: string; end: string | null; name: string; md: string; type: string; previous_id: number | null; next_id: number | null };
  metric_set: MetricSetMeta;
  periods: { id: number; name: string; role: string; role_label: string; minutes: number | null; counts_as_play: boolean }[];
  rows: { player_id: number; name: string; shirt_number: number | null; position: string; participation: string; flagged: boolean;
          values: Record<string, number | null>; periods: Record<string, Record<string, number | null>> }[];
}
export interface MetricSetItem { id: number; name: string; metric_keys: string[]; display: string; is_default: boolean; is_club: boolean; metrics: MetricCol[] }
