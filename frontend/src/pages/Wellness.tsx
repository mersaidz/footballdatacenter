// Coach's diary: what the players said this morning, entering answers for a player, and the players' personal links.
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import qrcode from 'qrcode-generator';
import { api, ApiError, clubPath, useApi } from '../api';
import { scoreText, answerWord, areaLabel, CheckinValues, ITEMS, Questionnaire, RpePicker, SCORE_COLOR } from '../components/Checkin';
import { InfoTip, State } from '../components/ui';
import { day, Key, num, t } from '../i18n';

export type FeelLevel = 'ok' | 'low' | 'very_low';
export interface Answer extends Partial<CheckinValues> {
  date: string; total: number; z: number | null; level: FeelLevel; normal: number | null; flags?: string[]; source?: string;
}
interface SquadWellness {
  date: string; details: boolean; answered: number; squad: number; low: number; very_low: number;
  rows: { player_id: number; name: string; shirt_number: number | null; position: string; answer: Answer | null }[];
}
interface LinkRow { player_id: number; name: string; shirt_number: number | null; active: boolean; created_at: string | null; last_used_at: string | null; last_answer: string | null }

export const FEEL = {
  ok: { color: 'var(--green)', bg: 'rgba(74,222,128,0.10)' },
  low: { color: 'var(--amber)', bg: 'rgba(251,191,36,0.12)' },
  very_low: { color: 'var(--red)', bg: 'rgba(248,113,113,0.12)' },
} as const;

export function FeelBadge({ a }: { a: Answer | null }) {
  if (!a) return <span className="small faint">{t('wl_none')}</span>;
  const f = FEEL[a.level];
  return (
    <span className="badge" style={{ color: f.color, background: f.bg }} title={a.normal != null ? t('wl_usual', { n: num(a.normal, 0) }) : undefined}>
      <span className="dot" style={{ background: f.color, width: 7, height: 7 }} />{a.total}/25 · {t(`wl_${a.level}` as Key)}
    </span>
  );
}

const ScoreCell = ({ v }: { v?: number }) => (v ? <span className="score" style={{ color: scoreText(v), background: `${SCORE_COLOR[v]}1f` }}>{v}</span> : <span className="faint">—</span>);

/** Modal: staff fill in the questionnaire (and RPE) after talking to the player. */
export function EntryDialog({ player, date, initial, onClose }:
  { player: { id: number; name: string }; date: string; initial?: Partial<CheckinValues> | null; onClose: (saved: boolean) => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [rpe, setRpe] = useState<number | null>(null);
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && onClose(saved);
    window.addEventListener('keydown', esc); return () => window.removeEventListener('keydown', esc);
  }, [onClose, saved]);
  const save = async (v: CheckinValues) => {
    setBusy(true); setErr('');
    try { await api(clubPath('wellness/'), { method: 'POST', body: JSON.stringify({ ...v, player_id: player.id, date }) }); onClose(true); }
    catch (e) { setErr((e as ApiError).detail); } finally { setBusy(false); }
  };
  const saveRpe = async (r: number) => {
    setBusy(true); setErr('');
    try { await api(clubPath('rpe/'), { method: 'POST', body: JSON.stringify({ player_id: player.id, date, rpe: r }) }); setRpe(r); setSaved(true); }
    catch (e) { setErr((e as ApiError).detail); } finally { setBusy(false); }
  };
  return (
    <div className="overlay" role="dialog" aria-modal="true" aria-label={t('wl_enter')} onClick={(e) => e.target === e.currentTarget && onClose(saved)}>
      <div className="card dialog">
        <div className="head">
          <div><h2>{player.name}</h2><span className="small muted">{t('wl_enter')} · {day(date, { day: 'numeric', month: 'long' })}</span></div>
          <button className="pill" onClick={() => onClose(saved)}>{t('close')}</button>
        </div>
        {err && <div role="alert" style={{ color: 'var(--red)' }}>{err}</div>}
        <Questionnaire initial={initial} onSubmit={save} busy={busy} submitLabel={t('save')} />
        <div style={{ borderTop: '1px solid var(--line-soft)', paddingTop: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <b style={{ fontWeight: 500 }}>RPE · {t('rpe_q')}</b>
          <RpePicker value={rpe} onPick={saveRpe} busy={busy} />
          {rpe != null && <span className="small" style={{ color: 'var(--green)' }}>{t('rpe_saved', { v: rpe })}</span>}
        </div>
      </div>
    </div>
  );
}

function Qr({ text }: { text: string }) {
  const svg = useMemo(() => { const q = qrcode(0, 'M'); q.addData(text); q.make(); return q.createSvgTag({ cellSize: 4, margin: 2, scalable: true }); }, [text]);
  return <div className="qr" aria-label="QR" dangerouslySetInnerHTML={{ __html: svg }} />;
}

const SERVER_KEY = 'fdc.phone_host';
function phoneHost() { try { return localStorage.getItem(SERVER_KEY) || window.location.origin; } catch { return window.location.origin; } }

function Links() {
  const q = useApi<LinkRow[]>(clubPath('player-links/'));
  const [host, setHost] = useState(phoneHost());
  const [fresh, setFresh] = useState<{ name: string; path: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const local = /127\.0\.0\.1|localhost/.test(host);
  const issue = async (r: LinkRow) => {
    const d = await api<{ path: string }>(clubPath('player-links/'), { method: 'POST', body: JSON.stringify({ player_id: r.player_id }) });
    setFresh({ name: r.name, path: d.path }); setCopied(false); q.reload();
  };
  const revoke = async (r: LinkRow) => { await api(clubPath(`player-links/${r.player_id}/revoke/`), { method: 'POST' }); q.reload(); };
  const url = fresh ? `${host.replace(/\/$/, '')}${fresh.path}` : '';
  return (
    <>
      <section className="card">
        <p className="muted" style={{ margin: 0, lineHeight: 1.6 }}>{t('wl_links_hint')}</p>
        <label className="row small muted" style={{ gap: 10 }}>{t('wl_server')}
          <input className="input" style={{ minWidth: 260 }} value={host} onChange={(e) => { setHost(e.target.value); try { localStorage.setItem(SERVER_KEY, e.target.value); } catch { /* ignore */ } }} />
        </label>
        {local && <div className="notice small">{t('wl_server_hint')}</div>}
      </section>
      {fresh && (
        <section className="card" style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 20, alignItems: 'center', borderColor: 'rgba(255,122,69,0.45)' }}>
          <Qr text={url} />
          <div style={{ flex: '1 1 320px', display: 'flex', flexDirection: 'column', gap: 10 }}>
            <h2>{t('wl_link_for', { n: fresh.name })}</h2>
            <code className="link-box">{url}</code>
            <div className="row">
              <button className="btn" onClick={() => { navigator.clipboard?.writeText(url).then(() => setCopied(true)); }}>{copied ? t('wl_copied') : t('wl_copy')}</button>
              <button className="pill" onClick={() => setFresh(null)}>{t('close')}</button>
            </div>
            <span className="small muted" style={{ lineHeight: 1.5 }}>{t('wl_link_once')}</span>
          </div>
        </section>
      )}
      <section className="card flush">
        <State loading={q.loading && !q.data} error={q.error} onRetry={q.reload}>
          <div className="scroll"><table>
            <thead><tr><th>#</th><th>{t('col_player')}</th><th>{t('wl_links')}</th><th>{t('wl_last_used')}</th><th>{t('wl_last_answer')}</th><th /></tr></thead>
            <tbody>{(q.data || []).map((r) => (
              <tr key={r.player_id}>
                <td className="muted">{r.shirt_number ?? ''}</td><td style={{ fontWeight: 500 }}>{r.name}</td>
                <td>{r.active ? <span className="badge" style={{ color: 'var(--green)', background: 'rgba(74,222,128,0.1)' }}>{t('wl_active')}</span> : <span className="faint small">{t('wl_no_link')}</span>}</td>
                <td className="muted">{r.last_used_at ? day(r.last_used_at.slice(0, 10)) : '—'}</td>
                <td className="muted">{r.last_answer ? day(r.last_answer) : '—'}</td>
                <td className="right"><span className="row" style={{ justifyContent: 'flex-end' }}>
                  <button className="pill" onClick={() => issue(r)}>{r.active ? t('wl_renew') : t('wl_new_link')}</button>
                  {r.active && <button className="pill" onClick={() => revoke(r)}>{t('wl_revoke')}</button>}
                </span></td>
              </tr>
            ))}</tbody>
          </table></div>
        </State>
      </section>
    </>
  );
}

export default function Wellness() {
  const [date, setDate] = useState('');
  const [tab, setTab] = useState<'answers' | 'links'>('answers');
  const [entry, setEntry] = useState<SquadWellness['rows'][number] | null>(null);
  const q = useApi<SquadWellness>(clubPath(`wellness/${date ? `?date=${date}` : ''}`), [date]);
  const w = q.data;
  return (
    <>
      <header className="top">
        <span>{t('nav_wellness')}</span><span className="grow" />
        <label className="small" htmlFor="wdate">{t('wl_for_date')}</label>
        <input id="wdate" className="input" type="date" value={date || w?.date || ''} onChange={(e) => setDate(e.target.value)} />
      </header>
      <div className="page">
        <div className="head" style={{ alignItems: 'flex-end' }}>
          <h1>{t('wl_title')}</h1>
          {w?.details && <div className="tabs" role="tablist" style={{ border: 0 }}>
            {(['answers', 'links'] as const).map((k) => <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>{t(k === 'answers' ? 'wl_answers' : 'wl_links')}</button>)}
          </div>}
        </div>
        <State loading={q.loading && !w} error={q.error} onRetry={q.reload}>
          {w && tab === 'answers' && <>
            <div className="grid" style={{ '--min': '200px' } as React.CSSProperties}>
              <div className="kpi" style={{ cursor: 'default' }}><span className="small" style={{ color: 'var(--text-2)' }}>{t('wl_answers')}</span>
                <b>{w.answered}<span className="muted" style={{ fontSize: 18, fontWeight: 400 }}> / {w.squad}</span></b>
                <div className="bar"><span style={{ width: `${w.squad ? (w.answered / w.squad) * 100 : 0}%`, background: 'var(--accent)' }} /></div></div>
              {(['very_low', 'low'] as const).map((l) => (
                <div key={l} className="kpi" style={{ cursor: 'default' }}>
                  <span className="row small" style={{ color: 'var(--text-2)' }}><span className="dot" style={{ background: FEEL[l].color }} />{t(`wl_${l}`)}</span>
                  <b>{w[l]}</b><span className="small muted">{t(l === 'low' ? 'lvl_hold' : 'lvl_reduce')}</span></div>
              ))}
            </div>
            {!w.details && <div className="notice small">{t('wl_coach_note')}</div>}
            <section className="card flush">
              <div className="head"><h2>{t('wl_answered', { a: w.answered, n: w.squad })}</h2><InfoTip label={t('wl_total')} text={t('wl_rules')} /></div>
              <div className="scroll"><table>
                <thead><tr>
                  <th>#</th><th>{t('col_player')}</th><th>{t('col_feel')}</th>
                  {w.details && <>{ITEMS.map((i) => <th key={i} className="right" title={t(`q_${i}` as Key)}>{t(`i_${i}` as Key)}</th>)}
                    <th className="right">{t('col_sleep_h')}</th><th>{t('col_sore')}</th><th>{t('col_comment')}</th><th>{t('col_source')}</th><th /></>}
                </tr></thead>
                <tbody>{w.rows.map((r) => {
                  const a = r.answer;
                  return (
                    <tr key={r.player_id}>
                      <td className="muted">{r.shirt_number ?? ''}</td>
                      <td><Link to={`/players/${r.player_id}`} style={{ fontWeight: 500 }}>{r.name}</Link></td>
                      <td><FeelBadge a={a} />{a?.normal != null && <span className="small faint"> · {t('wl_usual', { n: num(a.normal, 0) })}</span>}</td>
                      {w.details && <>
                        {ITEMS.map((i) => <td key={i} className="right" title={a?.[i] ? answerWord(i, a[i]!) : ''}><ScoreCell v={a?.[i]} /></td>)}
                        <td className="right">{a?.sleep_hours ?? '—'}</td>
                        <td style={{ whiteSpace: 'normal', minWidth: 150, color: 'var(--text-2)' }}>{a?.sore_areas?.map(areaLabel).join(', ') || ''}</td>
                        <td style={{ whiteSpace: 'normal', minWidth: 160, maxWidth: 320, color: 'var(--text-2)' }}>{a?.comment || ''}</td>
                        <td className="small muted">{a?.source ? t(`src_${a.source}` as Key) : ''}</td>
                        <td className="right"><button className="pill" onClick={() => setEntry(r)}>{t('wl_enter_short')}</button></td>
                      </>}
                    </tr>
                  );
                })}</tbody>
              </table></div>
            </section>
          </>}
          {w && tab === 'links' && <Links />}
        </State>
      </div>
      {entry && w && <EntryDialog player={{ id: entry.player_id, name: entry.name }} date={w.date} initial={entry.answer}
        onClose={(saved) => { setEntry(null); if (saved) q.reload(); }} />}
    </>
  );
}
