import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Navigate, NavLink, Route, Routes, useNavigate } from 'react-router-dom';
import './styles.css';
import { api, auth, useApi } from './api';
import { getLang, LANGS, Lang, setLang, t } from './i18n';
import { Icon, ICONS, State } from './components/ui';
import Today from './pages/Today';
import Sessions from './pages/Sessions';
import SessionDetail from './pages/SessionDetail';
import Microcycle from './pages/Microcycle';
import Players from './pages/Players';
import PlayerProfile from './pages/PlayerProfile';
import Settings from './pages/Settings';

document.documentElement.lang = getLang();

export interface Membership { club_id: number; club_name: string; club_slug: string; role: string }

function Login() {
  const [email, setEmail] = useState(''); const [password, setPassword] = useState('');
  const [err, setErr] = useState(''); const [busy, setBusy] = useState(false);
  const nav = useNavigate();
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setErr('');
    try { await auth.login(email, password); nav('/'); } catch { setErr(t('bad_credentials')); } finally { setBusy(false); }
  };
  return (
    <div className="login">
      <form className="card" onSubmit={submit}>
        <div className="brand"><Logo /><div><b>Football Data Center</b><span>{t('brand_sub')}</span></div></div>
        <h1>{t('login_title')}</h1>
        <label className="small muted" htmlFor="email">{t('email')}</label>
        <input id="email" className="input" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <label className="small muted" htmlFor="pw">{t('password')}</label>
        <input id="pw" className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        {err && <div role="alert" style={{ color: 'var(--red)' }}>{err}</div>}
        <button className="btn" disabled={busy}>{t('login_btn')}</button>
        <LangSwitch />
      </form>
    </div>
  );
}

const Logo = () => <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#ff7a45" strokeWidth="1.5" aria-hidden="true"><path d="M12 2 20 6.5v11L12 22 4 17.5v-11L12 2z" /><path d="M12 8l4 4-4 4-4-4 4-4z" /></svg>;

export function LangSwitch({ onChange }: { onChange?: (l: Lang) => void }) {
  const cur = getLang();
  return (
    <div className="seg" role="group" aria-label={t('language')}>
      {LANGS.map((l) => (
        <button key={l.code} type="button" aria-pressed={cur === l.code} onClick={() => {
          setLang(l.code); onChange?.(l.code);
          if (auth.loggedIn()) api('me/', { method: 'PATCH', body: JSON.stringify({ language: l.code }) }).catch(() => undefined);
          window.location.reload();
        }}>{l.label}</button>
      ))}
    </div>
  );
}

function Shell() {
  const clubs = useApi<Membership[]>('clubs/');
  const me = useApi<{ email: string; full_name: string; language: Lang }>('me/');
  useEffect(() => {
    if (me.data && me.data.language !== getLang() && !localStorage.getItem('fdc.lang')) { setLang(me.data.language); window.location.reload(); }
  }, [me.data]);
  useEffect(() => {
    if (clubs.data?.length && !clubs.data.find((c) => c.club_id === auth.club())) auth.setClub(clubs.data[0].club_id);
  }, [clubs.data]);
  if (clubs.loading || !clubs.data) return <State loading={clubs.loading} error={clubs.error} onRetry={clubs.reload} />;
  if (!clubs.data.length) return <div className="state">{t('no_club')}</div>;
  const club = clubs.data.find((c) => c.club_id === auth.club()) || clubs.data[0];
  if (auth.club() !== club.club_id) auth.setClub(club.club_id);
  const links: [string, string, keyof typeof ICONS][] = [
    ['/', t('nav_today'), 'today'], ['/sessions', t('nav_sessions'), 'sessions'], ['/week', t('nav_week'), 'week'],
    ['/players', t('nav_players'), 'players'], ['/settings', t('nav_settings'), 'settings'],
  ];
  return (
    <div className="app">
      <nav className="side" aria-label="Main">
        <div className="brand"><Logo /><div><b>Football Data Center</b><span>{club.club_name}</span></div></div>
        {links.map(([to, label, icon]) => (
          <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => `nav${isActive ? ' active' : ''}`}>
            <Icon d={ICONS[icon]} />{label}
          </NavLink>
        ))}
        <div className="side-foot">
          {clubs.data.length > 1 && (
            <select className="input" value={club.club_id} aria-label={t('club')} onChange={(e) => { auth.setClub(Number(e.target.value)); window.location.href = '/'; }}>
              {clubs.data.map((c) => <option key={c.club_id} value={c.club_id}>{c.club_name}</option>)}
            </select>
          )}
          <LangSwitch />
          <span>{me.data?.full_name || me.data?.email}</span>
          <button className="pill" onClick={auth.logout}><Icon d={ICONS.logout} />{t('logout')}</button>
        </div>
      </nav>
      <main className="main">
        <Routes>
          <Route path="/" element={<Today />} />
          <Route path="/sessions" element={<Sessions />} />
          <Route path="/sessions/:id" element={<SessionDetail />} />
          <Route path="/week" element={<Microcycle />} />
          <Route path="/players" element={<Players />} />
          <Route path="/players/:id" element={<PlayerProfile />} />
          <Route path="/settings" element={<Settings role={club.role} />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </main>
    </div>
  );
}

// Evaluated on every navigation (not once when App first renders), so logging in takes effect at once.
const Protected = () => (auth.loggedIn() ? <Shell /> : <Navigate to="/login" replace />);
const LoginRoute = () => (auth.loggedIn() ? <Navigate to="/" replace /> : <Login />);

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginRoute />} />
        <Route path="/*" element={<Protected />} />
      </Routes>
    </BrowserRouter>
  );
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>);
