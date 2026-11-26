import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { clubPath, SessionSummary, useApi } from '../api';
import { day, num, t, weekday } from '../i18n';
import { Seg, State } from '../components/ui';

function monday(iso: string) {
  const d = new Date(iso + 'T12:00:00');
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return d.toISOString().slice(0, 10);
}

export function TypeBadge({ type, md }: { type: string; md?: string }) {
  const match = type === 'match';
  return (
    <span className="row" style={{ gap: 6 }}>
      {md && <span className="tag" style={{ background: match ? 'var(--accent-soft)' : 'rgba(var(--fg-rgb),0.08)', color: match ? 'var(--accent-text)' : 'var(--text-2)' }}>{md}</span>}
      <span className="small muted">{match ? t('t_match') : t('t_training')}</span>
    </span>
  );
}

export default function Sessions() {
  const [type, setType] = useState<'all' | 'match' | 'training'>('all');
  const [from, setFrom] = useState(''); const [to, setTo] = useState('');
  const params = new URLSearchParams();
  if (type !== 'all') params.set('type', type);
  if (from) params.set('from', from);
  if (to) params.set('to', to);
  const q = useApi<SessionSummary[]>(clubPath(`sessions/?${params}`), [type, from, to]);
  const nav = useNavigate();
  const weeks = useMemo(() => {
    const out: { week: string; items: SessionSummary[] }[] = [];
    for (const s of q.data || []) {
      const w = monday(s.date);
      if (!out.length || out[out.length - 1].week !== w) out.push({ week: w, items: [] });
      out[out.length - 1].items.push(s);
    }
    return out;
  }, [q.data]);
  return (
    <>
      <header className="top"><span>{t('nav_sessions')}</span></header>
      <div className="page">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <h1>{t('sessions_title')}</h1>
          <div className="row">
            <Seg label={t('sessions_title')} value={type} onChange={setType}
              options={[{ value: 'all', label: t('f_all') }, { value: 'match', label: t('f_matches') }, { value: 'training', label: t('f_trainings') }]} />
            <label className="small muted" htmlFor="from">{t('from')}</label>
            <input id="from" className="input" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
            <label className="small muted" htmlFor="to">{t('to')}</label>
            <input id="to" className="input" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
          </div>
        </div>
        <State loading={q.loading && !q.data} error={q.error} empty={q.data?.length === 0} onRetry={q.reload}>
          {weeks.map((w) => (
            <section key={w.week} className="card flush">
              <div className="head"><h2>{t('week_of', { d: day(w.week, { day: 'numeric', month: 'long' }) })}</h2><span className="small muted">{t('avg_full')}</span></div>
              <div className="scroll">
                <table>
                  <thead><tr>
                    <th>{t('col_date')}</th><th>{t('col_session')}</th><th></th><th className="right">{t('nav_players')}</th>
                    <th className="right">{t('col_dur')}</th><th className="right">{t('col_dist')}</th><th className="right">{t('col_hsr')}</th><th className="right">{t('col_spr')}</th>
                  </tr></thead>
                  <tbody>
                    {w.items.map((s) => (
                      <tr key={s.id} className="click" tabIndex={0} onClick={() => nav(`/sessions/${s.id}`)} onKeyDown={(e) => e.key === 'Enter' && nav(`/sessions/${s.id}`)}>
                        <td><span className="muted" style={{ display: 'inline-block', width: 28 }}>{weekday(s.date)}</span> {day(s.date)}</td>
                        <td style={{ fontWeight: 500 }}>{s.name || '—'}</td>
                        <td><TypeBadge type={s.type} md={s.md} /></td>
                        <td className="right">{s.players}</td>
                        <td className="right">{s.duration != null ? `${s.duration}′` : '—'}</td>
                        <td className="right">{num(s.distance)} <span className="faint small">m</span></td>
                        <td className="right">{num(s.hsr)}</td>
                        <td className="right">{num(s.sprint)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ))}
        </State>
      </div>
    </>
  );
}
