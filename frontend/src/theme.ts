// Dark (Graphite) or light theme. "auto" follows the device. Stored per browser.
export type Theme = 'dark' | 'light' | 'auto';
const KEY = 'fdc.theme';
const media = () => window.matchMedia?.('(prefers-color-scheme: light)');

export function getTheme(): Theme {
  try { const v = localStorage.getItem(KEY); if (v === 'dark' || v === 'light' || v === 'auto') return v; } catch { /* ignore */ }
  return 'dark';
}

export function applyTheme(theme: Theme = getTheme()) {
  const light = theme === 'light' || (theme === 'auto' && !!media()?.matches);
  document.documentElement.dataset.theme = light ? 'light' : 'dark';
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', light ? '#F3F4F6' : '#0F1115');
}

export function setTheme(theme: Theme) {
  try { localStorage.setItem(KEY, theme); } catch { /* ignore */ }
  applyTheme(theme);
}

media()?.addEventListener?.('change', () => { if (getTheme() === 'auto') applyTheme('auto'); });
