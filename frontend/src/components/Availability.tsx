// Medical staff mark a player out or on modified training; coaches see the status, reason and date.
import { useEffect, useState } from 'react';
import { api, ApiError, auth, clubPath, useApi } from '../api';
import { day, Key, t } from '../i18n';

export interface Episode {
  id: number; status: 'available' | 'modified' | 'unavailable'; reason: string; start_date: string;
  expected_return: string | null; actual_return: string | null; diagnosis?: string; clinical_notes?: string;
}
const REASONS = ['injury', 'illness', 'load_management', 'personal', 'suspension', 'international'] as const;
const MEDICAL = ['physio', 'doctor'];

const today = () => { const d = new Date(); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10); };

/** Can this user edit availability? (The server checks it again.) */
export function useCanEditMedical() {
  const clubs = useApi<{ club_id: number; role: string }[]>('clubs/');
  return !!clubs.data?.find((c) => c.club_id === auth.club() && MEDICAL.includes(c.role));
}

export const reasonWord = (r: string) => t(`av_${r || 'other'}` as Key);

function Dialog({ playerId, playerName, episode, onClose }:
  { playerId: number; playerName: string; episode: Episode | null; onClose: (saved: boolean) => void }) {
  const [status, setStatus] = useState<'modified' | 'unavailable'>(episode?.status === 'modified' ? 'modified' : 'unavailable');
  const [reason, setReason] = useState(episode?.reason || 'injury');
  const [start, setStart] = useState(episode?.start_date || today());
  const [expected, setExpected] = useState(episode?.expected_return || '');
  const [diagnosis, setDiagnosis] = useState(episode?.diagnosis || '');
  const [notes, setNotes] = useState(episode?.clinical_notes || '');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && onClose(false);
    window.addEventListener('keydown', esc); return () => window.removeEventListener('keydown', esc);
  }, [onClose]);
  const save = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setErr('');
    const body = { player: playerId, status, reason, start_date: start, expected_return: expected || null, diagnosis, clinical_notes: notes };
    try {
      await api(clubPath(episode ? `availability/${episode.id}/` : 'availability/'), { method: episode ? 'PATCH' : 'POST', body: JSON.stringify(body) });
      onClose(true);
    } catch (x) { setErr((x as ApiError).detail); } finally { setBusy(false); }
  };
  return (
    <div className="overlay" role="dialog" aria-modal="true" aria-label={t('av_change')} onClick={(e) => e.target === e.currentTarget && onClose(false)}>
      <form className="card dialog" onSubmit={save}>
        <div className="head">
          <div><h2>{playerName}</h2><span className="small muted">{t('av_change')}</span></div>
          <button type="button" className="pill" onClick={() => onClose(false)}>{t('close')}</button>
        </div>
        {err && <div role="alert" style={{ color: 'var(--red)' }}>{err}</div>}
        <div className="seg" role="group" aria-label={t('av_status')}>
          {(['unavailable', 'modified'] as const).map((k) => (
            <button key={k} type="button" aria-pressed={status === k} onClick={() => setStatus(k)}>{t(k === 'modified' ? 'st_modified' : 'lvl_out')}</button>
          ))}
        </div>
        <label className="q"><span>{t('av_reason')}</span>
          <select className="input" value={reason} onChange={(e) => setReason(e.target.value)}>
            {REASONS.map((r) => <option key={r} value={r}>{reasonWord(r)}</option>)}
          </select>
        </label>
        <div className="grid" style={{ '--min': '200px' } as React.CSSProperties}>
          <label className="q"><span>{t('av_start')}</span><input className="input" type="date" value={start} onChange={(e) => setStart(e.target.value)} required /></label>
          <label className="q"><span>{t('av_expected')}</span><input className="input" type="date" value={expected} min={start} onChange={(e) => setExpected(e.target.value)} /></label>
        </div>
        <label className="q"><span>{t('av_diagnosis')}</span><input className="input" value={diagnosis} maxLength={300} onChange={(e) => setDiagnosis(e.target.value)} /></label>
        <label className="q"><span>{t('av_notes')}</span><textarea className="input" rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} /></label>
        <p className="small muted" style={{ margin: 0 }}>{t('av_medical_only')}</p>
        <button className="btn" disabled={busy}>{t('save')}</button>
      </form>
    </div>
  );
}

/** Status line + actions for the player profile. */
export function AvailabilityActions({ playerId, playerName, episode, onChanged }:
  { playerId: number; playerName: string; episode: Episode | null; onChanged: () => void }) {
  const canEdit = useCanEditMedical();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  if (!canEdit) return null;
  const back = async () => {
    if (!episode) return;
    setBusy(true);
    try { await api(clubPath(`availability/${episode.id}/`), { method: 'PATCH', body: JSON.stringify({ actual_return: today() }) }); onChanged(); }
    finally { setBusy(false); }
  };
  return (
    <>
      <span className="row" style={{ gap: 8 }}>
        <button type="button" className="pill" onClick={() => setOpen(true)}>{episode ? t('av_change') : t('av_set')}</button>
        {episode && <button type="button" className="pill" disabled={busy} onClick={back}>{t('av_returned')}</button>}
      </span>
      {open && <Dialog playerId={playerId} playerName={playerName} episode={episode} onClose={(saved) => { setOpen(false); if (saved) onChanged(); }} />}
    </>
  );
}

export function episodeNote(e: Episode | undefined) {
  if (!e) return t('no_injury');
  return [reasonWord(e.reason), e.expected_return ? `→ ${day(e.expected_return)}` : t('av_since', { d: day(e.start_date) })].join(', ');
}
