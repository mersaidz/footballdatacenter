import { useState } from 'react';
import { Link } from 'react-router-dom';
import { clubPath, useApi } from '../api';
import { day, num, t, weekday } from '../i18n';
import { Seg, State } from '../components/ui';

type M = 'dist' | 'hsr' | 'spr' | 'acc';
interface Day { date: string; md: string; session_id: number | null; name: string; players: number; is_match?: boolean; pct?: Record<string, number> }
interface Cycle {
  match: { session_id: number; date: string; name: string } | null;
  matches: { session_id: number; date: string; name: string }[];
  days: Day[]; grid: { player_id: number; name: string; shirt_number: number | null; cells: (null | (Record<M, number | null> & { minutes: number; alternate: boolean }))[] }[];
}

const heat = (v: number | null | undefined) => v == null ? {} : { background: `rgba(0,159,180,${(Math.max(0.06, Math.min(1, v / 110)) * 0.85).toFixed(2)})` };

export default function Microcycle() {
  const [match, setMatch] = useState('');
  const [metric, setMetric] = useState<M>('dist');
  const q = useApi<Cycle>(clubPath(`microcycle/${match ? `?match=${match}` : ''}`), [match]);
  const c = q.data;
  const opts: { value: M; label: string }[] = [{ value: 'dist', label: t('m_dist') }, { value: 'hsr', label: t('m_hsr') }, { value: 'spr', label: t('m_spr') }, { value: 'acc', label: t('m_acc') }];
  return (
    <>
      <header className="top">
        <span>{t('nav_week')}</span><span className="grow" />
        {c && <select className="input" aria-label={t('week_into')} value={match || c.match?.session_id || ''} onChange={(e) => setMatch(e.target.value)}>
          {c.matches.map((m) => <option key={m.session_id} value={m.session_id}>{day(m.date)} · {m.name}</option>)}
        </select>}
      </header>
      <div className="page">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <div><h1>{t('week_title')}</h1>{c?.match && <p className="muted" style={{ margin: '6px 0 0' }}>{t('week_into')}: {c.match.name} · {day(c.match.date)}</p>}</div>
          <Seg label={t('metric')} value={metric} onChange={setMetric} options={opts} />
        </div>
        <State loading={q.loading && !c} error={q.error} empty={!!c && !c.match} onRetry={q.reload}>
          {c && <>
            <section className="card">
              <div className="head"><h2>{t('team_pct')}</h2><span className="small muted">100% = {t('match_demand').toLowerCase()}</span></div>
              <div style={{ display: 'grid', gridTemplateColumns: `repeat(${c.days.length}, minmax(0, 1fr))`, gap: 10, alignItems: 'end', height: 220 }}>
                {c.days.map((d) => {
                  const v = d.pct?.[metric];
                  return (
                    <div key={d.date} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, height: '100%', justifyContent: 'flex-end' }}>
                      <span className="small num">{v != null ? `${v}%` : ''}</span>
                      {d.session_id ? (
                        <Link to={`/sessions/${d.session_id}`} title={d.name} style={{ width: '70%', height: `${Math.min(100, v || 0) * 1.6}px`, minHeight: 3, borderRadius: '6px 6px 2px 2px', background: d.is_match ? 'var(--accent)' : 'var(--teal)', opacity: d.is_match ? 1 : 0.8 }} />
                      ) : <span className="small faint" style={{ height: 30 }}>{t('rest')}</span>}
                    </div>
                  );
                })}
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: `repeat(${c.days.length}, minmax(0, 1fr))`, gap: 10, borderTop: '1px solid var(--line)', paddingTop: 8 }}>
                {c.days.map((d) => <div key={d.date} className="small" style={{ textAlign: 'center' }}><b style={{ fontWeight: 500 }}>{d.md || '—'}</b><div className="faint">{weekday(d.date)} {day(d.date)}</div></div>)}
              </div>
            </section>
            <section className="card flush">
              <div className="head"><h2>{t('grid_title')}</h2><span className="small muted">{t('grid_hint')}</span></div>
              <div className="scroll">
                <table>
                  <thead><tr><th>#</th><th>{t('col_player')}</th>{c.days.map((d) => <th key={d.date} className="right">{d.md || weekday(d.date)}</th>)}</tr></thead>
                  <tbody>
                    {c.grid.map((g) => (
                      <tr key={g.player_id}>
                        <td className="muted">{g.shirt_number ?? ''}</td>
                        <td><Link to={`/players/${g.player_id}`} style={{ fontWeight: 500 }}>{g.name}</Link></td>
                        {g.cells.map((cell, i) => (
                          <td key={i} className="right" title={cell ? `${cell.minutes}′` : t('no_session')}>
                            {cell ? <span className="heat num" style={heat(cell[metric])}>{num(cell[metric])}{cell.alternate ? ' *' : ''}</span> : <span className="faint">·</span>}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </>}
        </State>
      </div>
    </>
  );
}
