// The player's side: one page on his phone, opened from a personal link. No login, no app store.
import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { CheckinValues, Questionnaire, RpePicker } from '../components/Checkin';
import { day, getLang, LANGS, Lang, setLang, t } from '../i18n';

interface Home {
  player: { name: string; first_name: string; shirt_number: number | null; club: string };
  today: string; checkin: CheckinValues | null; rpe_today: number | null;
  sessions: { id: number; date: string; name: string; md: string; type: string; rpe: number | null }[];
}

async function call<T>(token: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(`/api/p/${encodeURIComponent(token)}/${path}?lang=${getLang()}`, {
    method: body ? 'POST' : 'GET', headers: { 'Content-Type': 'application/json', 'Accept-Language': getLang() },
    body: body ? JSON.stringify(body) : undefined,
  });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.detail || Object.values(d).flat().join(' ') || r.statusText);
  return d as T;
}

/** "Add to Home Screen" should reopen this player's page, not the staff app. */
function useInstallable(token: string, name: string | undefined) {
  useEffect(() => {
    if (!name) return;
    const add = (tag: string, attrs: Record<string, string>) => {
      const el = document.createElement(tag); Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
      el.setAttribute('data-player', '1'); document.head.appendChild(el);
    };
    add('link', { rel: 'manifest', href: `/api/p/${encodeURIComponent(token)}/manifest/` });
    add('meta', { name: 'apple-mobile-web-app-capable', content: 'yes' });
    add('meta', { name: 'apple-mobile-web-app-title', content: 'FDC' });
    add('meta', { name: 'theme-color', content: '#0a0a0a' });
    add('link', { rel: 'apple-touch-icon', href: '/static/icon-192.png' });
    document.title = `FDC · ${name}`;
    return () => document.querySelectorAll('[data-player]').forEach((el) => el.remove());
  }, [token, name]);
}

export default function PlayerApp() {
  const { token = '' } = useParams();
  const [home, setHome] = useState<Home | null>(null);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [rpeMsg, setRpeMsg] = useState('');
  const [, setLangTick] = useState(0);
  const load = () => call<Home>(token, '').then((h) => { setHome(h); setErr(''); }).catch((e: Error) => setErr(e.message));
  useEffect(() => { load(); }, [token]); // eslint-disable-line react-hooks/exhaustive-deps
  useInstallable(token, home?.player.first_name);

  const sendCheckin = async (v: CheckinValues) => {
    setBusy(true);
    try { await call(token, 'checkin/', v); setEditing(false); await load(); window.scrollTo({ top: 0, behavior: 'smooth' }); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const sendRpe = async (rpe: number, sessionId?: number) => {
    setBusy(true);
    try { await call(token, 'rpe/', sessionId ? { session_id: sessionId, rpe } : { rpe }); setRpeMsg(t('rpe_saved', { v: rpe })); await load(); }
    catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };

  const changeLang = (l: Lang) => { setLang(l); document.documentElement.lang = l; setLangTick((x) => x + 1); };
  if (err && !home) return <div className="pa"><div className="card" role="alert" style={{ marginTop: 40 }}>{err}</div></div>;
  if (!home) return <div className="pa"><div className="state">{t('loading')}</div></div>;
  const toRate = home.sessions.length ? home.sessions : null;
  return (
    <div className="pa">
      <header className="row" style={{ justifyContent: 'space-between', flexWrap: 'nowrap' }}>
        <span className="small muted">{home.player.club}</span>
        <div className="seg" role="group" aria-label={t('language')}>
          {LANGS.map((l) => <button key={l.code} type="button" aria-pressed={getLang() === l.code} onClick={() => changeLang(l.code)}>{l.label}</button>)}
        </div>
      </header>
      <div>
        <h1 style={{ fontSize: 26 }}>{t('pa_hello', { n: home.player.first_name })}</h1>
        <p className="muted" style={{ margin: '6px 0 0', lineHeight: 1.5 }}>{day(home.today, { weekday: 'long', day: 'numeric', month: 'long' })}</p>
      </div>
      {err && <div role="alert" className="notice" style={{ borderColor: 'var(--red)' }}>{err}</div>}

      <section className="card">
        <div className="head"><h2>{t('pa_morning')}</h2>{home.checkin && !editing && <span className="badge" style={{ color: 'var(--green)', background: 'rgba(74,222,128,0.1)' }}>✓</span>}</div>
        {home.checkin && !editing ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <p style={{ margin: 0, fontSize: 16 }}>{t('pa_thanks')}</p>
            <button className="pill" style={{ alignSelf: 'flex-start' }} onClick={() => setEditing(true)}>{t('pa_edit')}</button>
          </div>
        ) : (
          <>
            <p className="muted small" style={{ margin: 0, lineHeight: 1.5 }}>{t('pa_intro')}</p>
            <Questionnaire initial={home.checkin} onSubmit={sendCheckin} busy={busy} big />
            <p className="faint small" style={{ margin: 0, lineHeight: 1.5 }}>{t('pa_private')}</p>
          </>
        )}
      </section>

      <section className="card">
        <div className="head"><h2>{t('pa_after')}</h2></div>
        {(toRate || [null]).map((s) => {
          const value = s ? s.rpe : home.rpe_today;
          return (
            <div key={s ? s.id : 'today'} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div><b style={{ fontWeight: 500 }}>{s ? (s.date === home.today ? t('rpe_today') : `${s.name} · ${day(s.date)}`) : t('rpe_today')}</b>
                <div className="small muted">{t('rpe_q')}</div></div>
              <RpePicker value={value} busy={busy} onPick={(r) => sendRpe(r, s?.id)} />
            </div>
          );
        })}
        {rpeMsg && <div role="status" className="small" style={{ color: 'var(--green)' }}>{rpeMsg}</div>}
        <p className="faint small" style={{ margin: 0 }}>{t('rpe_hint')}</p>
      </section>
      <p className="faint small" style={{ textAlign: 'center', lineHeight: 1.5 }}>{t('pa_install')}</p>
    </div>
  );
}
