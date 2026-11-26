import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { clubPath, Reason, SquadStatus, useApi } from '../api';
import { day, num, t } from '../i18n';
import { Gauge, LEVEL, LevelBadge, State } from '../components/ui';

export function reasonText(r: Reason) {
  const v = r.value != null ? num(r.value, 2) : '';
  const d = r.date ? day(r.date) : '';
  return t(`r_${r.code}` as never, { v, d });
}

export default function Today() {
  const [date, setDate] = useState('');
  const [filter, setFilter] = useState<'all' | 'modify' | 'monitor' | 'ready'>('all');
  const nav = useNavigate();
  const q = useApi<SquadStatus>(clubPath(`squad-status/${date ? `?date=${date}` : ''}`), [date]);
  const s = q.data;
  const counts = { modify: 0, monitor: 0, ready: 0 };
  s?.players.forEach((p) => { counts[p.level] += 1; });
  const rows = (s?.players || []).filter((p) => filter === 'all' || p.level === filter);
  const md1 = s?.days_since_match === 1 && s.last_match;
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
            {(['modify', 'monitor', 'ready'] as const).map((l) => (
              <button key={l} className="kpi" aria-pressed={filter === l} onClick={() => setFilter(filter === l ? 'all' : l)}
                style={filter === l ? { background: LEVEL[l].bg, borderColor: LEVEL[l].color } : undefined}>
                <span className="row small" style={{ color: 'var(--text-2)' }}><span className="dot" style={{ background: LEVEL[l].color }} />{t(`lvl_${l}`)}</span>
                <b>{counts[l]}</b><span className="small muted">{t(`hint_${l}`)}</span>
              </button>
            ))}
          </div>
          {md1 && s && (
            <section className="card">
              <div className="head"><h2>{t('md1_groups')}</h2><span className="small muted">{s.last_match!.name}</span></div>
              <div className="grid" style={{ '--min': '240px' } as React.CSSProperties}>
                {[[t('recovery'), t('played60'), (m: number) => m >= 60, 'rgba(95,208,224,0.16)', '#9be3ec'],
                  [t('topup'), t('under60'), (m: number) => m < 60, 'rgba(255,122,69,0.14)', '#ffb08f']].map(([title, hint, fn, bg, fg]) => {
                  const ps = s.players.filter((p) => (fn as (m: number) => boolean)(p.last_match_minutes)).sort((a, b) => (a.shirt_number || 99) - (b.shirt_number || 99));
                  return (
                    <div key={title as string} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      <span><b style={{ fontWeight: 500 }}>{title as string}</b> <span className="muted small">{hint as string} · {ps.length}</span></span>
                      <div className="row" style={{ gap: 6 }}>{ps.map((p) => <Link key={p.player_id} to={`/players/${p.player_id}`} className="small" style={{ padding: '4px 8px', borderRadius: 8, background: bg as string, color: fg as string }}>{p.shirt_number ?? ''} {p.name}</Link>)}</div>
                    </div>
                  );
                })}
              </div>
            </section>
          )}
          <section className="card flush">
            <div className="head"><h2>{t('nav_players')}</h2><span className="small muted">{t('status_rules')}</span></div>
            <div className="scroll">
              <table>
                <thead><tr>
                  <th>{t('col_status')}</th><th>#</th><th>{t('col_player')}</th><th>{t('col_why')}</th><th>{t('col_acwr_d')}</th>
                  <th>{t('col_acwr_h')}</th><th className="right">{t('col_week')}</th><th className="right">{t('col_vs_prev')}</th><th className="right">{t('col_last_match')}</th>
                </tr></thead>
                <tbody>
                  {rows.map((p) => (
                    <tr key={p.player_id} className="click" onClick={() => nav(`/players/${p.player_id}`)}>
                      <td><LevelBadge level={p.level} /></td>
                      <td className="muted">{p.shirt_number ?? ''}</td>
                      <td><Link to={`/players/${p.player_id}`} style={{ fontWeight: 500 }} onClick={(e) => e.stopPropagation()}>{p.name}</Link>{p.position === 'GK' && <span className="small faint"> GK</span>}</td>
                      <td style={{ whiteSpace: 'normal', minWidth: 220, maxWidth: 380, color: 'var(--text-2)' }}>{p.reasons.length ? p.reasons.map(reasonText).join('; ') : t('in_range')}</td>
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
