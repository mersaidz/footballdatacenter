import { ReactNode, useState } from 'react';
import { num, t } from '../i18n';

export const LEVEL = {
  reduce: { color: 'var(--red)', bg: 'rgba(248,113,113,0.12)' },
  hold: { color: 'var(--amber)', bg: 'rgba(251,191,36,0.12)' },
  build: { color: 'var(--blue)', bg: 'rgba(96,165,250,0.12)' },
  plan: { color: 'var(--green)', bg: 'rgba(74,222,128,0.10)' },
} as const;

export const CAT_COLOR: Record<string, string> = {
  volume: '#a3a3a3', speed: '#ff7a45', acceleration: '#fbbf24', load: '#4ade80', metabolic: '#5fd0e0',
  multidirectional: '#a78bfa', mechanical: '#60a5fa', rhie: '#f472b6', heart_rate: '#f87171', other: '#a3a3a3',
};

export function State({ loading, error, empty, onRetry, children }:
  { loading?: boolean; error?: string | null; empty?: boolean; onRetry?: () => void; children?: ReactNode }) {
  if (loading) return <div className="state" role="status">{t('loading')}</div>;
  if (error) return <div className="state" role="alert">{t('error')}: {error} {onRetry && <button className="pill" onClick={onRetry}>{t('retry')}</button>}</div>;
  if (empty) return <div className="state">{t('empty')}</div>;
  return <>{children}</>;
}

export function LevelBadge({ level }: { level: keyof typeof LEVEL }) {
  const l = LEVEL[level];
  return <span className="badge" style={{ color: l.color, background: l.bg }}><span className="dot" style={{ background: l.color, width: 7, height: 7 }} />{t(`lvl_${level}` as never)}</span>;
}

export function acwrColor(v: number | null) {
  if (v == null) return '#737373';
  return v > 1.5 ? 'var(--red)' : v > 1.3 ? 'var(--amber)' : v < 0.8 ? 'var(--blue)' : 'var(--green)';
}

export function Gauge({ value }: { value: number | null }) {
  return (
    <span className="row" style={{ gap: 8, flexWrap: 'nowrap' }}>
      <span className="gauge" aria-hidden="true"><span className="zone" />
        <span className="mark" style={{ left: `${Math.min(100, ((value || 0) / 2.5) * 100)}%`, background: acwrColor(value) }} /></span>
      <span className="num">{num(value, 2)}</span>
    </span>
  );
}

export function Seg<T extends string>({ value, options, onChange, label }:
  { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; label: string }) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => <button key={o.value} type="button" aria-pressed={o.value === value} onClick={() => onChange(o.value)}>{o.label}</button>)}
    </div>
  );
}

/** Lines over days: values ≥ 0, optional green band and red threshold (ACWR). */
export function LineChart({ series, labels, max, band, threshold, height = 200, ariaLabel }:
  { series: { values: (number | null)[]; color: string; width?: number }[]; labels: string[]; max: number;
    band?: [number, number]; threshold?: number; height?: number; ariaLabel: string }) {
  const n = Math.max(1, labels.length - 1);
  const x = (i: number) => (i / n) * 800;
  const y = (v: number) => height - (Math.min(v, max) / max) * height;
  const path = (vals: (number | null)[]) => {
    let d = ''; let pen = false;
    vals.forEach((v, i) => { if (v == null) { pen = false; return; } d += `${pen ? 'L' : 'M'}${x(i).toFixed(1)} ${y(v).toFixed(1)} `; pen = true; });
    return d;
  };
  const ticks = labels.map((l, i) => ({ l, i })).filter(({ i }) => i % Math.ceil(labels.length / 6) === 0 || i === labels.length - 1);
  return (
    <div>
      <svg viewBox={`0 0 800 ${height}`} preserveAspectRatio="none" role="img" aria-label={ariaLabel} style={{ width: '100%', height }}>
        {band && <rect x="0" y={y(band[1])} width="800" height={y(band[0]) - y(band[1])} fill="rgba(74,222,128,0.12)" />}
        {threshold != null && <line x1="0" x2="800" y1={y(threshold)} y2={y(threshold)} stroke="rgba(248,113,113,0.6)" strokeDasharray="4 4" vectorEffect="non-scaling-stroke" />}
        {series.map((s, k) => <path key={k} d={path(s.values)} fill="none" stroke={s.color} strokeWidth={s.width || 2} vectorEffect="non-scaling-stroke" />)}
      </svg>
      <div className="row small faint" style={{ justifyContent: 'space-between' }}>{ticks.map(({ l, i }) => <span key={i}>{l}</span>)}</div>
    </div>
  );
}

export function Bars({ items, height = 160, refValue, refLabel }:
  { items: { value: number; color: string; title: string; label?: string; onClick?: () => void }[]; height?: number; refValue?: number; refLabel?: string }) {
  const max = Math.max(1, ...items.map((i) => i.value), refValue || 0) * 1.08;
  return (
    <div>
      <div style={{ position: 'relative', display: 'flex', alignItems: 'flex-end', gap: 3, height, borderBottom: '1px solid var(--line)' }}>
        {refValue ? <span title={refLabel} style={{ position: 'absolute', left: 0, right: 0, bottom: (refValue / max) * height, borderTop: '1px dashed rgba(255,255,255,0.35)' }} /> : null}
        {items.map((it, i) => (
          <button key={i} type="button" title={it.title} aria-label={it.title} onClick={it.onClick} disabled={!it.onClick}
            style={{ flex: 1, minWidth: 0, height: Math.max(it.value ? 2 : 0, (it.value / max) * height), background: it.color,
              border: 0, borderRadius: '4px 4px 1px 1px', padding: 0, cursor: it.onClick ? 'pointer' : 'default' }} />
        ))}
      </div>
      <div style={{ display: 'flex', gap: 3, marginTop: 6 }}>
        {items.map((it, i) => <span key={i} className="small faint" style={{ flex: 1, minWidth: 0, overflow: 'visible', whiteSpace: 'nowrap' }}>{it.label || ''}</span>)}
      </div>
    </div>
  );
}

export function Icon({ d, size = 16 }: { d: string; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={d} /></svg>;
}
export const ICONS = {
  today: 'M3 4h18v18H3zM16 2v4M8 2v4M3 10h18', sessions: 'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01',
  week: 'M3 3v18h18M18 17V9M13 17V5M8 17v-3', players: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 7a4 4 0 1 0 0 .01M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75',
  settings: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z',
  wellness: 'M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8l1 1.1L12 21l7.8-7.5 1-1.1a5.5 5.5 0 0 0 0-7.8z',
  left: 'M15 18l-6-6 6-6', right: 'M9 18l6-6-6-6', logout: 'M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9',
};

/** Instant help: shows on hover, keyboard focus or tap (native `title` tooltips wait ~1 s and never show on touch). */
export function InfoTip({ label, text }: { label: string; text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <span style={{ position: 'relative', display: 'inline-flex' }} onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button type="button" aria-expanded={open} aria-label={`${label}: ${text}`} onFocus={() => setOpen(true)} onBlur={() => setOpen(false)}
        onClick={() => setOpen((o) => !o)}
        style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: 'none', border: 0, color: 'inherit', cursor: 'help', padding: 0, font: 'inherit' }}>
        {label}
        <span aria-hidden="true" style={{ width: 16, height: 16, borderRadius: '50%', border: '1px solid var(--faint)', display: 'inline-flex',
          alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 600 }}>?</span>
      </button>
      {open && (
        <span role="tooltip" style={{ position: 'absolute', bottom: 'calc(100% + 8px)', left: 0, width: 280, zIndex: 20, background: 'rgba(17,17,17,0.97)',
          border: '1px solid var(--line)', borderRadius: 10, padding: '10px 12px', color: 'var(--text-2)', fontSize: 12, lineHeight: 1.5,
          boxShadow: '0 8px 24px rgba(0,0,0,0.4)' }}>{text}</span>
      )}
    </span>
  );
}
