import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ApiError, api, clubPath, useApi } from '../api';
import { day, num, t } from '../i18n';
import { acwrColor, Bars, LineChart, State } from '../components/ui';
import { posLabel } from './Players';

interface History {
  player: { id: number; name: string; shirt_number: number | null; position: string; foot: string };
  days: { date: string; distance: number; hsr: number; md: string; is_match: boolean; session_id: number | null }[];
  acwr_distance: (number | null)[]; acwr_hsr: (number | null)[] | null;
  md_profile: { md: string; sessions: number; dist: number | null; hsr: number | null; spr: number | null; acc: number | null }[];
  match_log: { session_id: number; date: string; name: string; minutes: number; distance: number; hsr: number; sprint: number; distance_p90: number | null; vmax: number | null }[];
  reference: Record<string, number>;
  totals: { sessions: number; matches: number; match_minutes: number; top_speed: number | null; flagged: number };
}
interface Football {
  competition: string; season: string; demo_link: { source_player: string; squad?: string } | null; main_position: string; peers: string;
  peer_count: number; minutes: number; matches: number;
  groups: { label: string; kpis: { label: string; kpi: string; per90: number; percentile: number | null; unit: string }[] }[];
  match_log: { match_id: number; date: string; home: boolean; opponent: string; score: string; result: string; minutes: number; position: string; xg: number; shots: number; goals: number; packing: number; carrying_m: number; ball_losses: number }[];
  shots: { x: number; y: number; xg: number; goal: boolean }[]; carries: { x: number; y: number; end_x: number; end_y: number }[];
  average_position: { x: number; y: number } | null;
}

const heat = (v: number | null) => v == null ? {} : { background: `rgba(0,159,180,${(Math.max(0.06, Math.min(1, v / 110)) * 0.85).toFixed(2)})` };
const GROUP_COLOR = ['#ff7a45', '#5fd0e0', '#a78bfa'];

function Pitch({ f }: { f: Football }) {
  const circle = (x: number, y: number, r: number) => `M${x - r} ${y}a${r} ${r} 0 1 0 ${2 * r} 0a${r} ${r} 0 1 0 ${-2 * r} 0`;
  return (
    <svg viewBox="-2 -2 109 72" role="img" aria-label="Season map" style={{ width: '100%', background: '#12261b', borderRadius: 8 }}>
      <g fill="none" stroke="rgba(255,255,255,0.35)" strokeWidth="0.4"><rect x="0" y="0" width="105" height="68" /><line x1="52.5" y1="0" x2="52.5" y2="68" />
        <circle cx="52.5" cy="34" r="9.15" /><rect x="0" y="13.84" width="16.5" height="40.32" /><rect x="88.5" y="13.84" width="16.5" height="40.32" /></g>
      <path d={f.carries.map((c) => `M${c.x} ${c.y}L${c.end_x} ${c.end_y}`).join('')} stroke="#5fd0e0" strokeWidth="0.35" opacity="0.55" />
      <path d={f.shots.filter((s) => !s.goal).map((s) => circle(s.x, s.y, 0.9 + Math.sqrt(s.xg) * 3.2)).join('')} fill="none" stroke="#fafafa" strokeWidth="0.35" />
      <path d={f.shots.filter((s) => s.goal).map((s) => circle(s.x, s.y, 0.9 + Math.sqrt(s.xg) * 3.2)).join('')} fill="#ff7a45" />
      {f.average_position && <circle cx={f.average_position.x} cy={f.average_position.y} r="2.4" fill="#fbbf24" stroke="#12261b" strokeWidth="0.8" />}
    </svg>
  );
}

function FootballTab({ id }: { id: string }) {
  const [f, setF] = useState<Football | null>(null); const [err, setErr] = useState<string | null>(null); const [none, setNone] = useState(false);
  useEffect(() => {
    api<Football>(clubPath(`players/${id}/football/`)).then(setF).catch((e: ApiError) => (e.status === 404 ? setNone(true) : setErr(e.detail)));
  }, [id]);
  if (none) return <div className="card muted">{t('fb_none')}</div>;
  return (
    <State loading={!f && !err} error={err}>
      {f && <>
        {f.demo_link && <div className="notice">{t('fb_demo', { src: f.demo_link.source_player, squad: `${f.demo_link.squad || ''}, ${f.competition} ${f.season}` })}</div>}
        <div className="grid" style={{ '--min': '420px' } as React.CSSProperties}>
          <section className="card">
            <div className="head"><div><h2>{t('fb_profile')}</h2><span className="small muted">{t('fb_peers', { n: f.peer_count, p: posLabel(({ GOALKEEPER: 'GK', CENTRAL_DEFENDER: 'CB', LEFT_WINGBACK_DEFENDER: 'FB', RIGHT_WINGBACK_DEFENDER: 'FB', DEFENSE_MIDFIELD: 'DM', CENTRAL_MIDFIELD: 'CM', ATTACKING_MIDFIELD: 'AM', LEFT_WINGER: 'W', RIGHT_WINGER: 'W', CENTER_FORWARD: 'CF' } as Record<string, string>)[f.main_position] || '') })}</span></div>
              <span className="small muted">{f.competition} {f.season} · {t('fb_minutes', { m: num(f.minutes), n: f.matches })}</span></div>
            {f.groups.filter((g) => !(f.main_position === 'GOALKEEPER' && (g as { key?: string }).key === 'attacking')).map((g, gi) => (
              <div key={g.label} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <span className="small" style={{ color: GROUP_COLOR[gi % 3], fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase' }}>{g.label}</span>
                {g.kpis.map((k) => (
                  <div key={k.kpi} style={{ display: 'grid', gridTemplateColumns: 'minmax(140px,1.4fr) 64px minmax(80px,2fr) 28px', gap: 10, alignItems: 'center' }}>
                    <span style={{ color: 'var(--text-2)' }}>{k.label}</span>
                    <span className="right num">{k.unit === '%' ? `${num(k.per90, 1)}%` : num(k.per90, k.per90 >= 100 ? 0 : 2)}</span>
                    <span className="bar" style={{ height: 8 }}><span style={{ width: `${k.percentile ?? 0}%`, background: GROUP_COLOR[gi % 3], opacity: 0.35 + (k.percentile ?? 0) / 160 }} /></span>
                    <span className="small muted right num">{k.percentile ?? '—'}</span>
                  </div>
                ))}
              </div>
            ))}
          </section>
          <section className="card"><div className="head"><h2>{t('season_map')}</h2><span className="small muted">→</span></div><Pitch f={f} /></section>
        </div>
        <section className="card flush">
          <div className="head"><h2>{t('fb_log')}</h2><span className="small muted">IMPECT</span></div>
          <div className="scroll" style={{ maxHeight: 440, overflowY: 'auto' }}>
            <table>
              <thead><tr><th>{t('col_date')}</th><th>{t('col_opp')}</th><th>{t('col_score')}</th><th className="right">{t('col_min')}</th><th className="right">{t('col_xg')}</th><th className="right">{t('col_shots')}</th><th className="right">{t('col_goals')}</th><th className="right">{t('col_packing')}</th><th className="right">{t('col_carry')}</th><th className="right">{t('col_losses')}</th></tr></thead>
              <tbody>{f.match_log.map((m) => (
                <tr key={m.match_id}><td>{day(m.date, { day: '2-digit', month: '2-digit', year: '2-digit' })}</td><td>{m.opponent} <span className="small faint">{m.home ? t('home') : t('away')}</span></td>
                  <td><span className="tag" style={{ color: '#0a0a0a', background: { W: '#4ade80', D: '#a3a3a3', L: '#f87171' }[m.result] || '#a3a3a3' }}>{m.result}</span> {m.score}</td>
                  <td className="right">{m.minutes}′</td><td className="right">{num(m.xg, 2)}</td><td className="right">{m.shots}</td><td className="right">{m.goals}</td>
                  <td className="right">{num(m.packing)}</td><td className="right">{num(m.carrying_m)}</td><td className="right">{m.ball_losses}</td></tr>
              ))}</tbody>
            </table>
          </div>
        </section>
      </>}
    </State>
  );
}

export default function PlayerProfile() {
  const { id = '' } = useParams();
  const nav = useNavigate();
  const [tab, setTab] = useState<'load' | 'football' | 'wellness'>('load');
  const q = useApi<History>(clubPath(`players/${id}/load-history/`), [id]);
  const h = q.data;
  const p = h?.player;
  const last = (a: (number | null)[] | null | undefined) => (a && a.length ? a[a.length - 1] : null);
  return (
    <>
      <header className="top"><Link to="/players">{t('nav_players')}</Link><span>/</span><span style={{ color: 'var(--text)' }}>{p?.name}</span></header>
      <div className="page">
        <State loading={q.loading && !h} error={q.error} onRetry={q.reload}>
          {h && p && <>
            <section className="card" style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 24, alignItems: 'center' }}>
              <div className="hero-num"><b>{p.shirt_number ?? '—'}</b><span className="small" style={{ color: 'var(--accent-text)', fontWeight: 600 }}>{p.position || ''}</span></div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, flex: '1 1 260px' }}>
                <h1 style={{ fontSize: 28 }}>{p.name}</h1>
                <span className="row muted">{posLabel(p.position)}{p.foot && <> · {t(`foot_${p.foot}` as never)}</>}</span>
              </div>
              <div className="grid" style={{ '--min': '120px', flex: '2 1 480px' } as React.CSSProperties}>
                {[[t('col_acwr_d'), num(last(h.acwr_distance), 2), acwrColor(last(h.acwr_distance))], [t('sessions_n'), h.totals.sessions], [t('matches_n'), h.totals.matches],
                  [t('match_minutes'), h.totals.match_minutes], [t('top_speed'), h.totals.top_speed ? `${num(h.totals.top_speed, 1)} km/h` : '—'], [t('gps_flagged'), h.totals.flagged]].map(([l, v, c]) => (
                  <div key={l as string} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}><span className="small muted">{l}</span><b className="num" style={{ fontSize: 20, fontWeight: 600, color: c as string | undefined }}>{v}</b></div>
                ))}
              </div>
            </section>
            <div className="tabs" role="tablist">
              {(['load', 'football', 'wellness'] as const).map((k) => <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>{t(`tab_${k}`)}</button>)}
            </div>
            {tab === 'load' && <>
              <section className="card">
                <div className="head"><h2>{t('acwr_chart')}</h2><span className="row small muted">
                  <span><span className="dot" style={{ background: '#5fd0e0' }} /> {t('m_dist')} {num(last(h.acwr_distance), 2)}</span>
                  {h.acwr_hsr && <span><span className="dot" style={{ background: '#a78bfa' }} /> HSR {num(last(h.acwr_hsr), 2)}</span>}
                  <span>{t('acwr_band')}</span></span></div>
                <LineChart ariaLabel={t('acwr_chart')} labels={h.days.map((d) => day(d.date))} max={2.5} band={[0.8, 1.3]} threshold={1.5}
                  series={[...(h.acwr_hsr ? [{ values: h.acwr_hsr, color: '#a78bfa' }] : []), { values: h.acwr_distance, color: '#5fd0e0', width: 2.5 }]} />
              </section>
              <section className="card">
                <div className="head"><h2>{t('daily_distance')}</h2><span className="small muted">{t('match_demand')}: {num((h.reference.dist || 0) / 1000, 1)} km</span></div>
                <Bars refValue={h.reference.dist} refLabel={t('match_demand')} items={h.days.map((d, i) => ({
                  value: d.distance, color: d.is_match ? 'var(--accent)' : 'var(--teal)',
                  title: `${day(d.date)}${d.md ? ` · ${d.md}` : ''}: ${num(d.distance / 1000, 1)} km`, label: i % 4 === 0 ? day(d.date) : '',
                  onClick: d.session_id ? () => nav(`/sessions/${d.session_id}`) : undefined }))} />
              </section>
              <div className="grid" style={{ '--min': '420px' } as React.CSSProperties}>
                <section className="card flush">
                  <div className="head"><h2>{t('md_profile')}</h2><span className="small muted">{t('md_profile_hint')}</span></div>
                  <div className="scroll"><table>
                    <thead><tr><th>MD</th><th className="right">{t('sessions_n')}</th><th className="right">{t('m_dist')}</th><th className="right">HSR</th><th className="right">{t('m_spr')}</th><th className="right">{t('m_acc')}</th></tr></thead>
                    <tbody>{h.md_profile.map((r) => (
                      <tr key={r.md}><td>{r.md}</td><td className="right">{r.sessions}</td>
                        {(['dist', 'hsr', 'spr', 'acc'] as const).map((k) => <td key={k} className="right"><span className="heat" style={heat(r[k])}>{r[k] == null ? '—' : `${r[k]}%`}</span></td>)}</tr>
                    ))}</tbody>
                  </table></div>
                </section>
                <section className="card flush">
                  <div className="head"><h2>{t('match_log')}</h2><span className="small muted">OpenField</span></div>
                  <div className="scroll"><table>
                    <thead><tr><th>{t('col_date')}</th><th>{t('col_session')}</th><th className="right">{t('col_min')}</th><th className="right">{t('m_dist')}</th><th className="right">{t('col_p90')}</th><th className="right">HSR</th><th className="right">{t('col_vmax')}</th></tr></thead>
                    <tbody>{h.match_log.map((m) => (
                      <tr key={m.session_id} className="click" onClick={() => nav(`/sessions/${m.session_id}`)}>
                        <td>{day(m.date)}</td><td>{m.name}</td><td className="right">{m.minutes}′</td><td className="right">{num(m.distance / 1000, 1)}</td>
                        <td className="right">{m.distance_p90 ? num(m.distance_p90 / 1000, 1) : '—'}</td><td className="right">{num(m.hsr)}</td><td className="right">{num(m.vmax, 1)}</td></tr>
                    ))}</tbody>
                  </table></div>
                </section>
              </div>
            </>}
            {tab === 'football' && <FootballTab id={id} />}
            {tab === 'wellness' && <div className="card muted">{t('wellness_soon')}</div>}
          </>}
        </State>
      </div>
    </>
  );
}
