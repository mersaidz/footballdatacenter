import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { clubPath, Reason, SquadStatus, useApi } from '../api';
import { day, num, t } from '../i18n';
import { Gauge, InfoTip, LEVEL, LevelBadge, State } from '../components/ui';
import { FeelBadge } from './Wellness';

/** Plain words, not formulas: "Нагрузка в 1,7 раза выше привычной", "Плохо спал, мало сил". */
export function reasonText(r: Reason) {
  if (r.code.startsWith('wellness_')) {
    const said = (r.flags || []).map((f) => t(`f_${f}` as never));
    if (!said.length) return t(`r_${r.code}` as never);
    const s = said.join(', ');
    return s.charAt(0).toUpperCase() + s.slice(1);
  }
  const why = t(`av_${r.reason || 'other'}` as never);
  if (r.code === 'unavailable') { const s = r.date ? t('r_unavailable', { why, d: day(r.date) }) : t('r_unavailable_nodate', { why }); return s.charAt(0).toUpperCase() + s.slice(1); }
  if (r.code === 'modified') return t('r_modified', { why });
  const v = r.value != null ? num(r.value, 1) : '';
  const d = r.date ? day(r.date) : '';
  return t(`r_${r.code}` as never, { v, d });
}

/** Reasons as one short line: at most two, and HSR only when distance says nothing (the columns carry the numbers). */
export function reasonsLine(rs: Reason[]) {
  const topup = rs.find((r) => r.code === 'no_topup_today');
  if (topup) return [rs.find((r) => r.code.startsWith('wellness_')), topup].filter(Boolean).map((r) => reasonText(r!)).join('. ');
  const dist = rs.some((r) => r.code.startsWith('acwr_dist'));
  const main = rs.filter((r) => r.code !== 'short_history' && !(dist && r.code.startsWith('acwr_hsr')))
    .filter((r) => !(r.code === 'low_hsr' && rs.some((x) => x.code === 'underloaded')));
  return main.slice(0, 2).map(reasonText).join('. ');
}

export default function Today() {
  const [date, setDate] = useState('');
  const [filter, setFilter] = useState<'all' | 'reduce' | 'hold' | 'build' | 'plan' | 'out'>('all');
  const nav = useNavigate();
  const q = useApi<SquadStatus>(clubPath(`squad-status/${date ? `?date=${date}` : ''}`), [date]);
  const s = q.data;
  const counts = { reduce: 0, hold: 0, build: 0, plan: 0, out: 0 };
  s?.players.forEach((p) => { counts[p.level] += 1; });
  const rows = (s?.players || []).filter((p) => filter === 'all' || p.level === filter);
  const md1 = s?.days_since_match === 1 && s.last_match;
  const training = (s?.players || []).filter((p) => p.level !== 'out');
  return (
    <>
      <header className="top">
        <span>{t('nav_today')}</span>
        <span className="grow" />
        <label className="small" htmlFor="asof">{t('as_of')}</label>
        <input id="asof" className="input" type="date" value={date || s?.as_of || ''} onChange={(e) => setDate(e.target.value)} />
      </header>
      <div className="page">
        <div>
          <h1>{t('today_title')}</h1>
          {s?.last_match && <p className="muted" style={{ margin: '6px 0 0' }}>
            {s.days_since_match === 1 ? t('day_after') : `${s.days_since_match} ${t('days_after')}`}: <Link to={`/sessions/${s.last_match.session_id}`} style={{ color: 'var(--accent-text)' }}>{s.last_match.name}</Link> · {day(s.last_match.date)}
          </p>}
        </div>
        <State loading={q.loading && !s} error={q.error} onRetry={q.reload}>
          <div className="grid" style={{ '--min': '200px' } as React.CSSProperties}>
            {(['reduce', 'hold', 'build', 'plan'] as const).map((l) => (
              <button key={l} className="kpi" aria-pressed={filter === l} onClick={() => setFilter(filter === l ? 'all' : l)}
                style={filter === l ? { background: LEVEL[l].bg, borderColor: LEVEL[l].color } : undefined}>
                <span className="row small" style={{ color: 'var(--text-2)' }}><span className="dot" style={{ background: LEVEL[l].color }} />{t(`lvl_${l}`)}</span>
                <b>{counts[l]}</b><span className="small muted">{t(`hint_${l}`)}</span>
              </button>
            ))}
          </div>
          {counts.out > 0 && (
            <button type="button" className="pill" aria-pressed={filter === 'out'} onClick={() => setFilter(filter === 'out' ? 'all' : 'out')} style={{ alignSelf: 'flex-start' }}>
              <span className="dot" style={{ background: LEVEL.out.color }} />{t('out_n', { n: counts.out })}
            </button>
          )}
          {md1 && s && (
            <section className="card">
              <div className="head"><h2>{t('md1_groups')}</h2><span className="small muted">{t('md1_hint', { m: s.last_match!.name })}</span></div>
              <div className="grid" style={{ '--min': '240px' } as React.CSSProperties}>
                {[[t('recovery_group'), t('played60'), (m: number) => m >= 60, 'rgba(95,208,224,0.16)', 'var(--teal-text)'],
                  [t('topup_group'), t('under60'), (m: number) => m < 60, 'rgba(255,122,69,0.14)', 'var(--accent-text)']].map(([title, hint, fn, bg, fg]) => {
                  const ps = training.filter((p) => (fn as (m: number) => boolean)(p.last_match_minutes)).sort((a, b) => (a.shirt_number || 99) - (b.shirt_number || 99));
                  return (
                    <div key={title as string} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      <span><b style={{ fontWeight: 500 }}>{title as string}</b> <span className="muted small">— {hint as string} · {ps.length}</span></span>
                      <div className="row" style={{ gap: 6 }}>{ps.map((p) => <Link key={p.player_id} to={`/players/${p.player_id}`} className="small" style={{ padding: '4px 8px', borderRadius: 8, background: bg as string, color: fg as string }}>{p.shirt_number ?? ''} {p.name}</Link>)}</div>
                    </div>
                  );
                })}
              </div>
            </section>
          )}
          <section className="card flush">
            <div className="head"><h2>{t('nav_players')}</h2>
              <span className="row small muted" style={{ gap: 14 }}>
                {s?.wellness && <Link to="/wellness" style={{ color: 'var(--accent-text)' }}>{t('wl_answered', { a: s.wellness.answered, n: s.wellness.squad })}</Link>}
                <InfoTip label={t('how_counted')} text={t('status_rules')} align="right" /></span></div>
            <div className="scroll">
              <table>
                <thead><tr>
                  <th>{t('col_status')}</th><th>#</th><th>{t('col_player')}</th><th>{t('col_why')}</th><th>{t('col_feel')}</th><th>{t('col_acwr_d')}</th>
                  <th>{t('col_acwr_h')}</th><th className="right">{t('col_week')}</th><th className="right">{t('col_vs_prev')}</th><th className="right">{t('col_last_match')}</th>
                </tr></thead>
                <tbody>
                  {rows.map((p) => (
                    <tr key={p.player_id} className={`click${p.level === 'out' ? ' out' : ''}`} onClick={() => nav(`/players/${p.player_id}`)}>
                      <td><LevelBadge level={p.level} /></td>
                      <td className="muted">{p.shirt_number ?? ''}</td>
                      <td><Link to={`/players/${p.player_id}`} style={{ fontWeight: 500 }} onClick={(e) => e.stopPropagation()}>{p.name}</Link>{p.position === 'GK' && <span className="small faint"> GK</span>}</td>
                      <td style={{ whiteSpace: 'normal', minWidth: 240, maxWidth: 420, color: 'var(--text-2)' }}>{p.reasons.length ? reasonsLine(p.reasons) : t('in_range')}</td>
                      <td><FeelBadge a={p.wellness} /></td>
                      <td><Gauge value={p.acwr_distance} /></td>
                      <td>{p.acwr_hsr == null ? <span className="faint">—</span> : <Gauge value={p.acwr_hsr} />}</td>
                      <td className="right">{num(p.week_distance / 1000, 1)}</td>
                      <td className="right" style={{ color: 'var(--text-2)' }}>{p.week_change_pct == null ? '—' : `${p.week_change_pct > 0 ? '+' : ''}${p.week_change_pct}%`}</td>
                      <td className="right">{p.last_match_minutes ? `${p.last_match_minutes}′` : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </State>
      </div>
    </>
  );
}
