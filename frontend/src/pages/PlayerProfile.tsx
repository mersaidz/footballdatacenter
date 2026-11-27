import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ApiError, api, clubPath, MetricSetItem, SessionDetail, SquadStatus, useApi } from '../api';
import { day, num, t } from '../i18n';
import { acwrColor, Bars, CAT_COLOR, LEVEL, LineChart, State } from '../components/ui';
import { posLabel } from './Players';
import { reasonText } from './Today';
import PitchMap, { MapData } from '../components/PitchMap';
import PlayerWellnessTab, { CheckinCard, usePlayerWellness } from './PlayerWellness';
import { answerWord, SCORE_COLOR } from '../components/Checkin';
import { AvailabilityActions, Episode, episodeNote } from '../components/Availability';

interface History {
  player: { id: number; name: string; shirt_number: number | null; position: string; foot: string };
  days: { date: string; distance: number; hsr: number; md: string; is_match: boolean; session_id: number | null }[];
  acwr_distance: (number | null)[]; acwr_hsr: (number | null)[] | null;
  md_profile: { md: string; sessions: number; dist: number | null; hsr: number | null; spr: number | null; acc: number | null }[];
  match_log: { session_id: number; date: string; name: string; minutes: number; distance: number; hsr: number; sprint: number; distance_p90: number | null; vmax: number | null }[];
  reference: Record<string, number>;
  totals: { sessions: number; matches: number; match_minutes: number; top_speed: number | null; flagged: number };
}
type Shot = { x: number; y: number; xg: number; goal: boolean; match_id: number };
type Carry = { x: number; y: number; end_x: number; end_y: number; match_id: number };
interface Football {
  competition: string; season: string; demo_link: { source_player: string; squad?: string } | null; main_position: string; peers: string;
  peer_count: number; minutes: number; matches: number;
  groups: { key: string; label: string; kpis: { label: string; kpi: string; per90: number; percentile: number | null; unit: string }[] }[];
  match_log: { match_id: number; date: string; home: boolean; opponent: string; score: string; result: string; minutes: number; position: string; xg: number; shots: number; goals: number; packing: number; carrying_m: number; ball_losses: number }[];
  shots: Shot[]; carries: Carry[]; average_position: { x: number; y: number } | null;
  passes?: MapData['passes']; heat?: MapData['heat'];
}

const heat = (v: number | null) => v == null ? {} : { background: `rgba(0,159,180,${(Math.max(0.06, Math.min(1, v / 110)) * 0.85).toFixed(2)})` };
const GROUP_COLOR: Record<string, string> = { attacking: '#ff7a45', progression: '#5fd0e0', defending: '#a78bfa' };
const IMPECT_POS: Record<string, string> = { GOALKEEPER: 'GK', CENTRAL_DEFENDER: 'CB', LEFT_WINGBACK_DEFENDER: 'FB', RIGHT_WINGBACK_DEFENDER: 'FB',
  DEFENSE_MIDFIELD: 'DM', CENTRAL_MIDFIELD: 'CM', ATTACKING_MIDFIELD: 'AM', LEFT_WINGER: 'W', RIGHT_WINGER: 'W', CENTER_FORWARD: 'CF' };
const last = (a: (number | null)[] | null | undefined) => (a && a.length ? a[a.length - 1] : null);

function Pitch({ shots, carries, avg, arrows, label }: { shots: Shot[]; carries: Carry[]; avg: { x: number; y: number } | null; arrows?: boolean; label: string }) {
  const circle = (x: number, y: number, r: number) => `M${x - r} ${y}a${r} ${r} 0 1 0 ${2 * r} 0a${r} ${r} 0 1 0 ${-2 * r} 0`;
  const r = (s: Shot) => 0.9 + Math.sqrt(s.xg) * 3.2;
  const head = (c: Carry) => {
    const a = Math.atan2(c.end_y - c.y, c.end_x - c.x), h = 1.8;
    return `M${c.end_x} ${c.end_y}L${c.end_x - h * Math.cos(a - 0.45)} ${c.end_y - h * Math.sin(a - 0.45)}L${c.end_x - h * Math.cos(a + 0.45)} ${c.end_y - h * Math.sin(a + 0.45)}Z`;
  };
  return (
    <figure style={{ margin: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
      <svg viewBox="-2 -2 109 72" role="img" aria-label={label} style={{ width: '100%', background: '#12261b', borderRadius: 8 }}>
        <g fill="none" stroke="rgba(255,255,255,0.35)" strokeWidth="0.4"><rect x="0" y="0" width="105" height="68" /><line x1="52.5" y1="0" x2="52.5" y2="68" />
          <circle cx="52.5" cy="34" r="9.15" /><rect x="0" y="13.84" width="16.5" height="40.32" /><rect x="88.5" y="13.84" width="16.5" height="40.32" />
          <rect x="0" y="24.84" width="5.5" height="18.32" /><rect x="99.5" y="24.84" width="5.5" height="18.32" /></g>
        <path d={carries.map((c) => `M${c.x} ${c.y}L${c.end_x} ${c.end_y}`).join('')} stroke="#5fd0e0" strokeWidth={arrows ? 0.7 : 0.35} opacity={arrows ? 0.9 : 0.55} strokeLinecap="round" />
        {arrows && <path d={carries.map(head).join('')} fill="#5fd0e0" />}
        <path d={shots.filter((s) => !s.goal).map((s) => circle(s.x, s.y, r(s))).join('')} fill="none" stroke="#fafafa" strokeWidth="0.4" />
        <path d={shots.filter((s) => s.goal).map((s) => circle(s.x, s.y, r(s))).join('')} fill="#ff7a45" />
        {avg && <circle cx={avg.x} cy={avg.y} r="2.4" fill="#fbbf24" stroke="#12261b" strokeWidth="0.8" />}
      </svg>
      <figcaption className="row small muted" style={{ gap: 14 }}>
        <span className="row" style={{ gap: 6 }}><span className="dot" style={{ background: '#fbbf24' }} />{t('leg_avg')}</span>
        <span className="row" style={{ gap: 6 }}><span className="dot" style={{ background: '#ff7a45' }} />{t('leg_goal')}</span>
        <span className="row" style={{ gap: 6 }}><span className="dot" style={{ border: '1px solid #fafafa' }} />{t('leg_shot')}</span>
        <span style={{ color: '#5fd0e0' }}>→ {t('leg_carry')}</span>
        <span>{t('attack_lr')}</span>
      </figcaption>
    </figure>
  );
}

const Signal = ({ label, value, note, color, src }: { label: string; value: string; note: string; color: string; src: string }) => (
  <div style={{ borderRadius: 12, background: 'rgba(var(--fg-rgb),0.03)', border: '1px solid rgba(var(--fg-rgb),0.08)', padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 6 }}>
    <span className="row small muted" style={{ gap: 6 }}><span className="dot" style={{ background: color }} />{label}</span>
    <b className="num" style={{ fontSize: 20, fontWeight: 600, lineHeight: 1.1 }}>{value}</b>
    <span className="small" style={{ color: 'var(--text-2)' }}>{note}</span>
    <span className="small faint">{src}</span>
  </div>
);

function LastMatchPhysical({ sessionId, playerId }: { sessionId: number; playerId: number }) {
  const sets = useApi<MetricSetItem[]>(clubPath('metric-sets/'));
  const [setId, setSetId] = useState('default');
  const q = useApi<SessionDetail>(clubPath(`sessions/${sessionId}/?metric_set=${setId}`), [sessionId, setId]);
  const d = q.data;
  const me = d?.rows.find((r) => r.player_id === playerId);
  return (
    <section className="card">
      <div className="head"><div><h2>{t('last_match_phys')}</h2>{d && <span className="small muted">{d.session.name} · {day(d.session.date)}</span>}</div>
        <span className="small muted">{t('source_real')}</span></div>
      <div className="row" role="group" aria-label={t('metric_view')}>
        {(sets.data || []).map((s) => <button key={s.id} className="pill" aria-pressed={String(s.id) === setId || (setId === 'default' && s.id === d?.metric_set.id)} onClick={() => setSetId(String(s.id))}>{s.name}</button>)}
      </div>
      <State loading={q.loading && !d} error={q.error}>
        {d && me && (
          <div className="grid" style={{ '--min': '130px' } as React.CSSProperties}>
            {d.metric_set.metrics.map((m) => {
              const v = me.values[m.key];
              const all = d.rows.map((r) => r.values[m.key]).filter((x): x is number => x != null).sort((a, b) => b - a);
              const rank = v == null ? null : all.indexOf(v) + 1;
              const pct = v == null || !all[0] ? 0 : Math.max(3, (v / all[0]) * 100);
              return (
                <div key={m.key} title={m.label} style={{ borderRadius: 10, background: 'rgba(var(--fg-rgb),0.03)', border: '1px solid rgba(var(--fg-rgb),0.07)', padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <span className="row small muted" style={{ gap: 6 }}><span className="dot" style={{ width: 6, height: 6, background: CAT_COLOR[m.category] || '#a3a3a3' }} />{m.short_label}</span>
                  <b className="num" style={{ fontSize: 20, fontWeight: 600, color: v == null ? 'var(--faint)' : undefined }}>{num(v, m.unit === 'km/h' ? 1 : 0)} <span className="small faint" style={{ fontWeight: 300 }}>{m.unit}</span></b>
                  <span className="bar"><span style={{ width: `${pct}%`, background: CAT_COLOR[m.category] || '#a3a3a3' }} /></span>
                  <span className="small faint">{v == null ? t('not_measured') : m.key === 'duration' ? t('minutes_on_pitch') : t('rank_in_squad', { r: rank!, n: all.length })}</span>
                </div>
              );
            })}
          </div>
        )}
      </State>
    </section>
  );
}

function LatestOnTheBall({ f }: { f: Football }) {
  const m = f.match_log[0];
  if (!m) return null;
  const shots = f.shots.filter((s) => s.match_id === m.match_id);
  const carries = f.carries.filter((c) => c.match_id === m.match_id);
  const tiles: [string, string, string][] = [
    ['xG', num(m.xg, 2), t('xg_note', { s: m.shots, g: m.goals })], ['Packing', num(m.packing), t('packing_note')],
    [t('col_carry'), num(m.carrying_m), t('carry_note')], [t('prog_carries'), String(carries.length), '10 m+'],
    [t('col_losses'), String(m.ball_losses), t('losses_note')], [t('col_min'), `${m.minutes}′`, posLabel(IMPECT_POS[m.position] || '')],
  ];
  return (
    <section className="card">
      <div className="head"><div><h2>{t('latest_ball')}</h2>
        <span className="small muted">{day(m.date, { day: '2-digit', month: '2-digit', year: '2-digit' })} · {m.home ? t('home') : t('away')}: {m.opponent} · {m.score} ({m.result})</span></div>
        <span className="small" style={{ border: '1px dashed rgba(var(--fg-rgb),0.28)', borderRadius: 999, padding: '3px 9px', color: 'var(--muted)' }}>IMPECT{f.demo_link ? ' · demo' : ''}</span></div>
      <div className="row" style={{ alignItems: 'flex-start', gap: 16 }}>
        <div style={{ flex: '1 1 280px' }}><Pitch shots={shots} carries={carries} avg={f.average_position} arrows label={t('latest_ball')} /></div>
        <div className="grid" style={{ '--min': '120px', flex: '1 1 200px' } as React.CSSProperties}>
          {tiles.map(([l, v, n]) => <div key={l} style={{ display: 'flex', flexDirection: 'column', gap: 2 }}><span className="small muted">{l}</span><b className="num" style={{ fontSize: 20, fontWeight: 600 }}>{v}</b><span className="small faint">{n}</span></div>)}
        </div>
      </div>
    </section>
  );
}

function FootballTab({ f }: { f: Football }) {
  const [match, setMatch] = useState<number | null>(null);
  return <>
    {f.demo_link && <div className="notice">{t('fb_demo', { src: f.demo_link.source_player, squad: `${f.demo_link.squad || ''}, ${f.competition} ${f.season}` })}</div>}
    <div className="grid" style={{ '--min': '420px' } as React.CSSProperties}>
      <section className="card">
        <div className="head"><div><h2>{t('fb_profile')}</h2><span className="small muted">{t('fb_peers', { n: f.peer_count, p: posLabel(IMPECT_POS[f.main_position] || '') })}</span></div>
          <span className="small muted">{f.competition} {f.season} · {t('fb_minutes', { m: num(f.minutes), n: f.matches })}</span></div>
        {f.groups.filter((g) => !(f.main_position === 'GOALKEEPER' && g.key === 'attacking')).map((g) => (
          <div key={g.key} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <span className="small" style={{ color: GROUP_COLOR[g.key], fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase' }}>{g.label}</span>
            {g.kpis.map((k) => (
              <div key={k.kpi} style={{ display: 'grid', gridTemplateColumns: 'minmax(140px,1.4fr) 64px minmax(80px,2fr) 28px', gap: 10, alignItems: 'center' }}>
                <span style={{ color: 'var(--text-2)' }}>{k.label}</span>
                <span className="right num">{k.unit === '%' ? `${num(k.per90, 1)}%` : num(k.per90, k.per90 >= 100 ? 0 : 2)}</span>
                <span className="bar" style={{ height: 8 }}><span style={{ width: `${k.percentile ?? 0}%`, background: GROUP_COLOR[g.key], opacity: 0.35 + (k.percentile ?? 0) / 160 }} /></span>
                <span className="small muted right num">{k.percentile ?? '—'}</span>
              </div>
            ))}
          </div>
        ))}
      </section>
      <section className="card" id="season-map"><div className="head"><h2>{t('season_map')}</h2><span className="small muted">IMPECT</span></div>
        <PitchMap data={f as unknown as MapData} match={match} onMatch={setMatch} /></section>
    </div>
    <section className="card flush">
      <div className="head"><h2>{t('fb_log')}</h2><span className="small muted">IMPECT</span></div>
      <div className="scroll" style={{ maxHeight: 440, overflowY: 'auto' }}>
        <table>
          <thead><tr><th>{t('col_date')}</th><th>{t('col_opp')}</th><th>{t('col_score')}</th><th className="right">{t('col_min')}</th><th className="right">{t('col_xg')}</th><th className="right">{t('col_shots')}</th><th className="right">{t('col_goals')}</th><th className="right">{t('col_packing')}</th><th className="right">{t('col_carry')}</th><th className="right">{t('col_losses')}</th></tr></thead>
          <tbody>{f.match_log.map((m) => (
            <tr key={m.match_id} className="click" aria-selected={match === m.match_id}
              style={match === m.match_id ? { background: 'rgba(255,122,69,0.08)' } : undefined}
              onClick={() => { setMatch(match === m.match_id ? null : m.match_id); document.getElementById('season-map')?.scrollIntoView({ behavior: 'smooth', block: 'center' }); }}><td>{day(m.date, { day: '2-digit', month: '2-digit', year: '2-digit' })}</td><td>{m.opponent} <span className="small faint">{m.home ? t('home') : t('away')}</span></td>
              <td><span className="tag" style={{ color: 'var(--ink)', background: ({ W: '#4ade80', D: '#a3a3a3', L: '#f87171' } as Record<string, string>)[m.result] || '#a3a3a3' }}>{m.result}</span> {m.score}</td>
              <td className="right">{m.minutes}′</td><td className="right">{num(m.xg, 2)}</td><td className="right">{m.shots}</td><td className="right">{m.goals}</td>
              <td className="right">{num(m.packing)}</td><td className="right">{num(m.carrying_m)}</td><td className="right">{m.ball_losses}</td></tr>
          ))}</tbody>
        </table>
      </div>
    </section>
  </>;
}

const Pending = ({ title, text }: { title: string; text: string }) => (
  <section className="card" style={{ border: '1px dashed rgba(var(--fg-rgb),0.22)', background: 'transparent' }}>
    <div className="head"><h2>{title}</h2><span className="small faint">{t('not_connected')}</span></div>
    <p className="muted" style={{ margin: 0, lineHeight: 1.6 }}>{text}</p>
  </section>
);

export default function PlayerProfile() {
  const { id = '' } = useParams();
  const nav = useNavigate();
  const [tab, setTab] = useState<'overview' | 'load' | 'football' | 'wellness'>('overview');
  const q = useApi<History>(clubPath(`players/${id}/load-history/`), [id]);
  const status = useApi<SquadStatus>(clubPath('squad-status/'));
  const avail = useApi<{ results: Episode[] }>(clubPath(`availability/?player=${id}&current=true`), [id]);
  const [fb, setFb] = useState<Football | null | 'none'>(null);
  useEffect(() => {
    setFb(null);
    api<Football>(clubPath(`players/${id}/football/`)).then(setFb).catch((e: ApiError) => setFb(e.status === 404 ? 'none' : null));
  }, [id]);
  const w = usePlayerWellness(id);
  const h = q.data;
  const p = h?.player;
  const sleep = w.data?.latest?.sleep_hours != null && w.data.latest.sleep_quality ? w.data.latest : null;
  const st = useMemo(() => status.data?.players.find((x) => String(x.player_id) === id), [status.data, id]);
  const loadReason = st?.reasons.find((r) => !r.code.startsWith('wellness_'));
  const open = avail.data?.results?.[0];
  const football = fb && fb !== 'none' ? fb : null;
  const wk = (from: number, to?: number) => (h ? h.days.slice(from, to).reduce((a, d) => a + d.distance, 0) : 0);
  const now = wk(-7), prev = wk(-14, -7);
  return (
    <>
      <header className="top"><Link to="/players">{t('nav_players')}</Link><span>/</span><span style={{ color: 'var(--text)' }}>{p?.name}</span></header>
      <div className="page">
        <State loading={q.loading && !h} error={q.error} onRetry={q.reload}>
          {h && p && <>
            <section className="card" style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 24, alignItems: 'center', background: 'linear-gradient(180deg,var(--raised),var(--card))' }}>
              <div style={{ display: 'flex', gap: 18, alignItems: 'center', flex: '1 1 340px' }}>
                <div className="hero-num"><b>{p.shirt_number ?? '—'}</b><span className="small" style={{ color: 'var(--accent-text)', fontWeight: 600 }}>{p.position || ''}</span></div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <h1 style={{ fontSize: 28 }}>{p.name}</h1>
                  <span className="row" style={{ gap: 8 }}>
                    {st && <span className="badge" style={{ color: LEVEL[st.level].color, background: LEVEL[st.level].bg }}><span className="dot" style={{ background: LEVEL[st.level].color, width: 7, height: 7 }} />{t(`lvl_${st.level}`)}</span>}
                    <span className="small" style={{ border: '1px solid var(--line)', borderRadius: 999, padding: '3px 10px' }}>{posLabel(p.position)}</span>
                    {p.foot && <span className="small" style={{ border: '1px solid var(--line)', borderRadius: 999, padding: '3px 10px' }}>{t(`foot_${p.foot}` as never)}</span>}
                  </span>
                  <span className="small muted">{h.totals.sessions} {t('sessions_n').toLowerCase()} · {h.totals.matches} {t('matches_n').toLowerCase()} · {h.totals.match_minutes} {t('minutes_short')} · {t('top_speed').toLowerCase()} {num(h.totals.top_speed, 1)} km/h</span>
                </div>
              </div>
              <div className="grid" style={{ '--min': '130px', flex: '1 1 440px' } as React.CSSProperties}>
                <Signal label={t('tab_load')} value={num(st?.acwr_distance ?? last(h.acwr_distance), 2)} note={loadReason ? reasonText(loadReason) : t('in_range')}
                  color={st ? LEVEL[st.level].color : acwrColor(last(h.acwr_distance))} src="OpenField" />
                <Signal label={t('sig_hrv')} value="—" note={t('not_connected')} color="var(--faint)" src="Whoop / Oura" />
                {sleep ? <Signal label={t('sig_sleep')} value={`${num(sleep.sleep_hours, 1)} ${t('hours_short')}`} note={answerWord('sleep_quality', sleep.sleep_quality!)}
                    color={SCORE_COLOR[sleep.sleep_quality!]} src={t('checkin')} />
                  : <Signal label={t('sig_sleep')} value="—" note={t('not_connected')} color="var(--faint)" src="Whoop / Oura" />}
                <Signal label={t('sig_avail')} value={open ? t(open.status === 'modified' ? 'st_modified' : 'st_unavailable') : t('available')}
                  note={episodeNote(open)} color={open ? (open.status === 'modified' ? 'var(--amber)' : 'var(--red)') : 'var(--green)'} src={t('nav_players')} />
              </div>
              <div style={{ flex: '1 1 100%', display: 'flex', justifyContent: 'flex-end' }}>
                <AvailabilityActions playerId={p.id} playerName={p.name} episode={open || null} onChanged={() => { avail.reload(); status.reload(); }} />
              </div>
            </section>
            <div className="tabs" role="tablist">
              {(['overview', 'load', 'football', 'wellness'] as const).map((k) => <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>{t(`tab_${k}`)}</button>)}
            </div>

            {tab === 'overview' && <>
              <div className="grid" style={{ '--min': '300px' } as React.CSSProperties}>
                <section className="card">
                  <div className="head"><h2>{t('tab_load')}</h2><span className="small muted">{t('source_real')}</span></div>
                  <div className="row" style={{ alignItems: 'baseline', gap: 10 }}><b className="num" style={{ fontSize: 36, fontWeight: 700, color: acwrColor(last(h.acwr_distance)) }}>{num(last(h.acwr_distance), 2)}</b><span className="muted">{st?.is_gk ? 'ACWR PlayerLoad' : t('col_acwr_d')}</span></div>
                  <div style={{ position: 'relative', height: 8, borderRadius: 4, background: 'rgba(var(--fg-rgb),0.08)' }}>
                    <span style={{ position: 'absolute', left: '32%', width: '20%', top: 0, bottom: 0, background: 'rgba(74,222,128,0.25)' }} />
                    <span style={{ position: 'absolute', left: '60%', top: -3, bottom: -3, width: 2, background: 'rgba(248,113,113,0.7)' }} />
                    <span style={{ position: 'absolute', top: -4, width: 16, height: 16, marginLeft: -8, borderRadius: '50%', border: '3px solid var(--card)', background: acwrColor(last(h.acwr_distance)), left: `${Math.min(100, ((last(h.acwr_distance) || 0) / 2.5) * 100)}%` }} />
                  </div>
                  <div className="grid" style={{ '--min': '110px' } as React.CSSProperties}>
                    {[[t('col_acwr_h'), h.acwr_hsr ? num(last(h.acwr_hsr), 2) : '—'], [t('this_week'), `${num(now / 1000, 1)} km`],
                      [t('col_vs_prev'), prev ? `${now >= prev ? '+' : ''}${Math.round((now / prev - 1) * 100)}%` : '—'], [t('match_demand'), `${num((h.reference.dist || 0) / 1000, 1)} km`],
                      ...(st?.max_speed ? [[t('vmax_exposure'), t('days_ago', { n: st.max_speed.days }), t('vmax_top', { v: num(st.max_speed.top, 1) })]] : [])].map(([l, v, hint]) => (
                      <div key={l}><span className="small muted">{l}</span><b className="num" style={{ display: 'block', fontSize: 16, fontWeight: 600,
                        color: l === t('vmax_exposure') && (st?.max_speed?.days ?? 0) >= 7 ? 'var(--amber)' : undefined }}>{v}</b>
                        {hint && <span className="small faint">{hint}</span>}</div>
                    ))}
                  </div>
                </section>
                {w.data ? <CheckinCard w={w.data} player={{ id: p.id, name: p.name }} onSaved={() => { w.reload(); status.reload(); }} /> : <Pending title={t('checkin')} text={t('loading')} />}
                <Pending title={t('recovery')} text={t('recovery_soon')} />
              </div>
              <div className="grid" style={{ '--min': '440px' } as React.CSSProperties}>
                {h.match_log[0] ? <LastMatchPhysical sessionId={h.match_log[0].session_id} playerId={p.id} /> : <section className="card muted">{t('no_match_data')}</section>}
                {football ? <LatestOnTheBall f={football} /> : <section className="card muted">{fb === 'none' ? t('fb_none') : t('loading')}</section>}
              </div>
            </>}

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

            {tab === 'football' && (football ? <FootballTab f={football} /> : <div className="card muted">{fb === 'none' ? t('fb_none') : t('loading')}</div>)}
            {tab === 'wellness' && <>
              <PlayerWellnessTab player={{ id: p.id, name: p.name }} />
              <Pending title={t('recovery')} text={t('recovery_soon')} /></>}
          </>}
        </State>
      </div>
    </>
  );
}
