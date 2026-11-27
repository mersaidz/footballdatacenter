// Player profile: what he told us (check-ins against his own normal) and internal load (sRPE).
import { useState } from 'react';
import { clubPath, useApi } from '../api';
import { scoreText, answerWord, areaLabel, ITEMS, rpeColor, SCORE_COLOR } from '../components/Checkin';
import { Bars, InfoTip, LineChart, State } from '../components/ui';
import { day, Key, num, t } from '../i18n';
import { Answer, EntryDialog, FeelBadge } from './Wellness';

export interface PlayerWellnessData {
  from: string; to: string; details: boolean; answered_days: number;
  baseline: ({ n: number; total: [number, number] } & Record<string, [number, number] | number>) | null;
  latest: Answer | null; history: Answer[];
  rpe: { date: string; rpe: number; minutes: number | null; srpe: number | null; session_id: number | null; session_name: string | null; source: string }[];
  internal?: { week_load: number; monotony: number | null; strain: number | null; monotony_high: boolean;
    harder: { date: string; ratio: number; flag: boolean } | null };
}

export const usePlayerWellness = (id: string) => useApi<PlayerWellnessData>(clubPath(`players/${id}/wellness/?days=28`), [id]);

const localToday = () => { const d = new Date(); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10); };

function dates(from: string, to: string) {
  const out: string[] = []; const d = new Date(`${from}T12:00:00`); const end = new Date(`${to}T12:00:00`);
  while (d <= end) { out.push(d.toISOString().slice(0, 10)); d.setDate(d.getDate() + 1); }
  return out;
}

export function CheckinCard({ w, player, onSaved }: { w: PlayerWellnessData; player: { id: number; name: string }; onSaved: () => void }) {
  const [entry, setEntry] = useState(false);
  const a = w.latest;
  const base = w.baseline;
  return (
    <section className="card">
      <div className="head">
        <h2>{t('wl_latest')}</h2>
        <span className="row">{a && <span className="small muted">{day(a.date, { day: 'numeric', month: 'long' })}{a.source ? ` · ${t(`src_${a.source}` as Key)}` : ''}</span>}
          {w.details && <button className="pill" onClick={() => setEntry(true)}>{t('wl_enter')}</button>}</span>
      </div>
      {!a ? <p className="muted" style={{ margin: 0, lineHeight: 1.6 }}>{t('wl_no_data')}</p> : <>
        <div className="row" style={{ alignItems: 'baseline', gap: 12 }}>
          <b className="num" style={{ fontSize: 36, fontWeight: 700 }}>{a.total}<span className="muted" style={{ fontSize: 16, fontWeight: 400 }}>/25</span></b>
          <FeelBadge a={a} />{a.normal != null && <span className="small muted">{t('wl_usual', { n: num(a.normal, 0) })}</span>}
        </div>
        {w.details && <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
          {ITEMS.map((i) => {
            const v = a[i] || 0; const usual = base ? (base[i] as [number, number])[0] : null;
            return (
              <div key={i} style={{ display: 'grid', gridTemplateColumns: '110px 1fr 112px', gap: 10, alignItems: 'center' }}>
                <span className="small" style={{ color: 'var(--text-2)' }}>{t(`q_${i}` as Key).replace('?', '')}</span>
                <span style={{ position: 'relative', height: 8, borderRadius: 4, background: 'rgba(var(--fg-rgb),0.07)' }}>
                  <span style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${(v / 5) * 100}%`, borderRadius: 4, background: SCORE_COLOR[v] }} />
                  {usual != null && <span title={t('wl_usual', { n: num(usual, 1) })} style={{ position: 'absolute', left: `${(usual / 5) * 100}%`, top: -4, bottom: -4, width: 2, background: 'rgba(var(--fg-rgb),0.6)' }} />}
                </span>
                <span className="small" style={{ color: scoreText(v) }}>{v} · {answerWord(i, v)}</span>
              </div>
            );
          })}
          <div className="row small muted" style={{ gap: 14, marginTop: 4 }}>
            {a.sleep_hours != null && <span>{t('col_sleep_h')}: <b style={{ color: 'var(--text)', fontWeight: 500 }}>{num(a.sleep_hours, 1)}</b></span>}
            {!!a.sore_areas?.length && <span>{t('col_sore')}: <b style={{ color: 'var(--red)', fontWeight: 500 }}>{a.sore_areas.map(areaLabel).join(', ')}</b></span>}
          </div>
          {a.comment && <div className="notice small" style={{ borderStyle: 'solid', borderColor: 'var(--line)', background: 'var(--raised)' }}>«{a.comment}»</div>}
          {base && <span className="small faint">{t('wl_tick')}</span>}
        </div>}
      </>}
      {entry && <EntryDialog player={player} date={localToday()}
        initial={a && a.date === localToday() ? a : null}
        onClose={(saved) => { setEntry(false); if (saved) onSaved(); }} />}
    </section>
  );
}

export function WellnessTrend({ w }: { w: PlayerWellnessData }) {
  const ds = dates(w.from, w.to);
  const byDay = Object.fromEntries(w.history.map((h) => [h.date, h.total]));
  const base = w.baseline?.total;
  return (
    <section className="card">
      <div className="head"><h2>{t('wl_trend')}</h2><span className="small muted">{t('wl_answered_days', { n: w.answered_days })}{base ? ` · ${t('wl_band')}` : ''}</span></div>
      {/* the scale runs 5–25, so plot (total − 5) on 0–20 */}
      <LineChart ariaLabel={t('wl_trend')} labels={ds.map((d) => day(d))} max={20} height={180}
        band={base ? [Math.max(0, base[0] - base[1] - 5), Math.min(20, base[0] + base[1] - 5)] : undefined}
        series={[{ values: ds.map((d) => (byDay[d] != null ? byDay[d] - 5 : null)), color: '#ff7a45', width: 2.5 }]} />
      <div className="row small" style={{ gap: 4 }}>
        {ds.map((d) => { const h = w.history.find((x) => x.date === d); return (
          <span key={d} title={h ? `${day(d)} · ${h.total}/25` : `${day(d)} · ${t('wl_none')}`} style={{ flex: 1, height: 6, borderRadius: 2,
            background: h ? (h.level === 'ok' ? 'rgba(74,222,128,0.6)' : h.level === 'low' ? 'var(--amber)' : 'var(--red)') : 'rgba(var(--fg-rgb),0.06)' }} />); })}
      </div>
    </section>
  );
}

export function InternalLoad({ w }: { w: PlayerWellnessData }) {
  const ds = dates(w.from, w.to);
  const byDay = Object.fromEntries(w.rpe.map((r) => [r.date, r]));
  return (
    <section className="card">
      <div className="head"><h2>{t('internal_load')}</h2><span className="small muted">{t('internal_hint')}</span></div>
      {w.internal && w.rpe.length > 0 && (
        <div className="grid" style={{ '--min': '150px' } as React.CSSProperties}>
          <div><span className="small muted">{t('il_week')}</span><b className="num" style={{ display: 'block', fontSize: 20, fontWeight: 600 }}>{num(w.internal.week_load)} AU</b></div>
          <div><InfoTip label={t('il_monotony')} text={t('il_monotony_hint')} />
            <b className="num" style={{ display: 'block', fontSize: 20, fontWeight: 600, color: w.internal.monotony_high ? 'var(--amber)' : undefined }}>{num(w.internal.monotony, 2)}</b></div>
          <div><span className="small muted">{t('il_strain')}</span><b className="num" style={{ display: 'block', fontSize: 20, fontWeight: 600 }}>{num(w.internal.strain)}</b></div>
          {w.internal.harder && <div><InfoTip label={t('il_harder')} text={t('il_harder_hint', { r: num(w.internal.harder.ratio, 2) })} />
            <b className="num" style={{ display: 'block', fontSize: 20, fontWeight: 600, color: w.internal.harder.flag ? 'var(--amber)' : undefined }}>
              {w.internal.harder.flag ? `×${num(w.internal.harder.ratio, 2)}` : t('il_as_usual')}</b></div>}
        </div>
      )}
      {!w.rpe.length ? <p className="muted" style={{ margin: 0 }}>{t('rpe_none')}</p> :
        <Bars height={150} items={ds.map((d, i) => { const r = byDay[d]; return {
          value: r ? (r.srpe ?? r.rpe * 60) : 0, color: r ? rpeColor(r.rpe) : 'transparent',
          title: r ? `${day(d)} · RPE ${r.rpe}${r.srpe != null ? ` · sRPE ${r.srpe}` : ''}${r.session_name ? ` · ${r.session_name}` : ''}` : day(d),
          label: i % 4 === 0 ? day(d) : '' }; })} />}
    </section>
  );
}

export default function PlayerWellnessTab({ player }: { player: { id: number; name: string } }) {
  const q = usePlayerWellness(String(player.id));
  return (
    <State loading={q.loading && !q.data} error={q.error} onRetry={q.reload}>
      {q.data && <>
        <div className="grid" style={{ '--min': '380px' } as React.CSSProperties}>
          <CheckinCard w={q.data} player={player} onSaved={q.reload} />
          <WellnessTrend w={q.data} />
        </div>
        <InternalLoad w={q.data} />
      </>}
    </State>
  );
}
