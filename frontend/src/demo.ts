// Demo build (`npx vite build --mode demo`): the app runs without a server, on API answers recorded from a real
// instance (demo-data.json next to the page). Reads come from the recording; writes are accepted
// and forgotten, so the demo can be clicked through but never changes.
export const DEMO = (import.meta as unknown as { env: { MODE: string } }).env.MODE === 'demo';

let data: Promise<Record<string, unknown>> | null = null;
const load = () => (data ??= fetch('demo-data.json').then((r) => r.json()));

export async function demoFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method || 'GET').toUpperCase();
  if (method !== 'GET') {
    const body = typeof init.body === 'string' ? JSON.parse(init.body) : {};
    return { ok: true, ...body } as T;
  }
  const d = await load();
  const key = path.replace(/^\/+/, '').replace(/^api\//, '');
  if (key in d) return d[key] as T;
  const [base, query = ''] = key.split('?');
  if (base.endsWith('/sessions/') && base in d) {          // history filters work on the recording too
    const q = new URLSearchParams(query);
    return (d[base] as { type: string; date: string }[]).filter((s) =>
      (!q.get('type') || s.type === q.get('type')) && (!q.get('from') || s.date >= q.get('from')!) && (!q.get('to') || s.date <= q.get('to')!)) as T;
  }
  const near = Object.keys(d).find((k) => k.split('?')[0] === base);
  if (near) return d[near] as T;
  throw Object.assign(new Error('not in demo'), { status: 404, detail: 'Этого экрана нет в демо-версии' });
}
