import { useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { clubPath, MetricSetItem, SessionDetail as Detail, useApi } from '../api';
import { day, num, t } from '../i18n';
import { CAT_COLOR, Icon, ICONS, Seg, State } from '../components/ui';
import { TypeBadge } from './Sessions';

const PART: Record<string, [string, string, string]> = {
  full: ['part_full', '#7fd6e2', 'rgba(0,159,180,0.16)'], partial: ['part_partial', '#d4d4d4', 'rgba(255,255,255,0.08)'],
  alternate: ['part_alternate', '#ffb08f', 'rgba(255,122,69,0.14)'],
};

export default function SessionDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const [setId, setSetId] = useState<string>('default');
  const [display, setDisplay] = useState<string>('');
  const [period, setPeriod] = useState<number | null>(null);
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(null);
  const sets = useApi<MetricSetItem[]>(clubPath('metric-sets/'));
  const q = useApi<Detail>(clubPath(`sessions/${id}/?metric_set=${setId}${display ? `&display=${display}` : ''}`), [id, setId, display]);
  const d = q.data;
  const rows = useMemo(() => {
    if (!d) return [];
    const val = (r: Detail['rows'][number], k: string) => (period ? r.periods[period]?.[k] : r.values[k]) ?? null;
    const list = d.rows.filter((r) => !period || r.periods[period]).map((r) => ({ ...r, v: (k: string) => val(r, k) }));
    if (sort) list.sort((a, b) => { const x = a.v(sort.key), y = b.v(sort.key); if (x == null) return 1; if (y == null) return -1; return (x - y) * sort.dir; });
    return list;
  }, [d, period, sort]);
  const max = useMemo(() => {
    const m: Record<string, number> = {};
    d?.metric_set.metrics.forEach((c) => { m[c.key] = Math.max(0, ...rows.map((r) => r.v(c.key) ?? 0)); });
    return m;
  }, [d, rows]);
  const unit = (u: string, agg: string) => (agg === 'sum' && d?.metric_set.display === 'per_90' ? `${u}/90` : agg === 'sum' && d?.metric_set.display === 'per_min' ? `${u}/min` : u);
  return (
    <>
      <header className="top">
        <Link to="/sessions" className="row"><Icon d={ICONS.left} />{t('back_sessions')}</Link>
        <span className="grow" />
        {d && <>
          <button className="pill" disabled={!d.session.previous_id} onClick={() => { setPeriod(null); nav(`/sessions/${d.session.previous_id}`); }}><Icon d={ICONS.left} />{t('previous')}</button>
          <button className="pill" disabled={!d.session.next_id} onClick={() => { setPeriod(null); nav(`/sessions/${d.session.next_id}`); }}>{t('next')}<Icon d={ICONS.right} /></button>
        </>}
      </header>
      <div className="page">
        <State loading={q.loading && !d} error={q.error} onRetry={q.reload}>
          {d && <>
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <h1>{d.session.name || t('col_session')}</h1>
                <span className="row muted">{day(d.session.date, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })} · <TypeBadge type={d.session.type} md={d.session.md} /></span>
              </div>
              <div className="row">
                <label className="small muted" htmlFor="set">{t('metric_view')}</label>
                <select id="set" className="input" value={setId} onChange={(e) => setSetId(e.target.value)}>
                  <option value="default">{d.metric_set.id == null ? 'Core' : `${d.metric_set.name}`}</option>
                  {(sets.data || []).filter((s) => String(s.id) !== String(d.metric_set.id)).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
                <Seg label={t('metric_view')} value={display || d.metric_set.display} onChange={setDisplay}
                  options={[{ value: 'absolute', label: t('disp_absolute') }, { value: 'per_min', label: t('disp_per_min') }, { value: 'per_90', label: t('disp_per_90') }]} />
              </div>
            </div>
            {d.periods.length > 0 && (
              <div className="row" role="group" aria-label="Periods">
                <button className="pill" aria-pressed={period === null} onClick={() => setPeriod(null)}>{t('whole_session')}</button>
                {d.periods.map((p) => (
                  <button key={p.id} className="pill" aria-pressed={period === p.id} onClick={() => setPeriod(p.id)} title={p.counts_as_play ? '' : t('not_play')}>
                    {p.role_label}<span className="small faint">{p.name !== p.role_label ? p.name : ''} {p.minutes != null ? `${num(p.minutes, 0)}′` : ''}</span>
                  </button>
                ))}
              </div>
            )}
            <section className="card flush">
              <div className="head"><h2>{t('nav_players')} · {rows.length}</h2><span className="small muted">{t('sort_hint')}</span></div>
              <div className="scroll">
                <table>
                  <thead><tr>
                    <th>#</th><th>{t('col_player')}</th>
                    {d.metric_set.metrics.map((c) => (
                      <th key={c.key} className="right" aria-sort={sort?.key === c.key ? (sort.dir === -1 ? 'descending' : 'ascending') : 'none'}>
                        <button className="sort" onClick={() => setSort({ key: c.key, dir: sort?.key === c.key && sort.dir === -1 ? 1 : -1 })} title={c.label}>
                          <span className="row" style={{ gap: 5, justifyContent: 'flex-end', color: sort?.key === c.key ? 'var(--text)' : undefined }}>
                            <span className="dot" style={{ background: CAT_COLOR[c.category] || '#a3a3a3', width: 6, height: 6 }} />{c.short_label}{sort?.key === c.key ? (sort.dir === -1 ? ' ↓' : ' ↑') : ''}
                          </span>
                          <span className="small faint" style={{ fontWeight: 300, textAlign: 'right' }}>{unit(c.unit, c.aggregation) || ' '}</span>
                        </button>
                      </th>
                    ))}
                  </tr></thead>
                  <tbody>
                    {rows.map((r) => {
                      const p = PART[r.participation];
                      return (
                        <tr key={r.player_id} className="click" onClick={() => nav(`/players/${r.player_id}`)}>
                          <td className="muted">{r.shirt_number ?? ''}</td>
                          <td><span style={{ fontWeight: 500 }}>{r.name}</span>
                            {p && <span className="tag" style={{ marginLeft: 6, color: p[1], background: p[2] }}>{t(p[0] as never)}</span>}
                            {r.flagged && <span className="tag" title={t('gps_spike')} style={{ marginLeft: 6, color: 'var(--amber)', background: 'rgba(251,191,36,0.12)' }}>GPS</span>}
                          </td>
                          {d.metric_set.metrics.map((c) => {
                            const v = r.v(c.key);
                            const pct = v == null || !max[c.key] ? 0 : Math.max(3, (v / max[c.key]) * 100);
                            return (
                              <td key={c.key} className="right">
                                <div style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4, minWidth: 54 }}>
                                  <span style={{ color: v == null ? 'var(--faint)' : undefined }}>{num(v, c.aggregation === 'sum' && d.metric_set.display !== 'absolute' ? 1 : (c.unit === 'km/h' ? 1 : 0))}</span>
                                  <span className="bar" style={{ width: 54 }}><span style={{ width: `${pct}%`, background: CAT_COLOR[c.category] || '#a3a3a3', opacity: 0.75 }} /></span>
                                </div>
                              </td>
                            );
                          })}
                        </tr>
                      );
                    })}
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
