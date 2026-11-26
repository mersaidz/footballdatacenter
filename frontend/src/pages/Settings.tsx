import { useState } from 'react';
import { api, clubPath, MetricCol, MetricSetItem, useApi } from '../api';
import { t } from '../i18n';
import { CAT_COLOR, State } from '../components/ui';
import { LangSwitch, ThemeSwitch } from '../main';

const MANAGERS = ['sports_scientist', 'analyst', 'club_admin'];

export default function Settings({ role }: { role: string }) {
  const me = useApi<{ email: string; full_name: string }>('me/');
  const sets = useApi<MetricSetItem[]>(clubPath('metric-sets/'));
  const presets = useApi<{ key: string; name: string; description: string; installed: boolean }[]>(clubPath('metric-sets/presets/'));
  const defs = useApi<(MetricCol & { enabled: boolean })[]>(clubPath('metrics/definitions/'));
  const [name, setName] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [draft, setDraft] = useState<{ name: string; keys: string[] } | null>(null);
  const canManage = MANAGERS.includes(role);
  const run = (p: Promise<unknown>) => p.then(() => { sets.reload(); presets.reload(); }).catch((e) => alertError(e));
  const alertError = (e: { detail?: string }) => window.setTimeout(() => setErr(e.detail || 'Error'));
  const [err, setErr] = useState('');
  const saveName = async () => {
    await api('me/', { method: 'PATCH', body: JSON.stringify({ full_name: name }) });
    setSaved(true); me.reload();
  };
  const toggle = (k: string) => setDraft((d) => d && ({ ...d, keys: d.keys.includes(k) ? d.keys.filter((x) => x !== k) : d.keys.length < 12 ? [...d.keys, k] : d.keys }));
  return (
    <>
      <header className="top"><span>{t('nav_settings')}</span></header>
      <div className="page" style={{ maxWidth: 960 }}>
        <h1>{t('settings_title')}</h1>
        <section className="card">
          <h2>{t('language')}</h2>
          <LangSwitch />
          <h2 style={{ marginTop: 8 }}>{t('theme')}</h2>
          <ThemeSwitch />
        </section>
        <section className="card">
          <h2>{t('profile')}</h2>
          <State loading={me.loading} error={me.error}>
            <span className="small muted">{me.data?.email} · {t('role')}: {role}</span>
            <div className="row">
              <label className="small muted" htmlFor="nm">{t('name')}</label>
              <input id="nm" className="input" value={name ?? me.data?.full_name ?? ''} onChange={(e) => { setName(e.target.value); setSaved(false); }} />
              <button className="btn" disabled={name == null} onClick={saveName}>{t('save')}</button>
              {saved && <span className="small" style={{ color: 'var(--green)' }}>{t('saved')}</span>}
            </div>
          </State>
        </section>
        <section className="card">
          <div className="head"><h2>{t('metric_sets')}</h2>
            <button className="pill" onClick={() => setDraft({ name: '', keys: [] })}>+ {t('new_set')}</button></div>
          {err && <div role="alert" style={{ color: 'var(--red)' }}>{err}</div>}
          <State loading={sets.loading} error={sets.error}>
            {[[t('club_sets'), (s: MetricSetItem) => s.is_club], [t('my_sets'), (s: MetricSetItem) => !s.is_club]].map(([label, fn]) => (
              <div key={label as string} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <span className="small muted">{label as string}</span>
                {(sets.data || []).filter(fn as (s: MetricSetItem) => boolean).map((s) => (
                  <div key={s.id} className="row" style={{ justifyContent: 'space-between', borderTop: '1px solid var(--line-soft)', paddingTop: 8 }}>
                    <span style={{ minWidth: 0 }}><b style={{ fontWeight: 500 }}>{s.name}</b>{s.is_default && <span className="small faint"> · {t('is_default')}</span>}
                      <span className="small muted" style={{ display: 'block' }}>{s.metrics.map((m) => m.short_label).join(' · ')}</span></span>
                    <span className="row">
                      {!s.is_default && (!s.is_club || canManage) && <button className="pill" onClick={() => run(api(clubPath(`metric-sets/${s.id}/make_default/`), { method: 'POST' }))}>{t('make_default')}</button>}
                      {(!s.is_club || canManage) && <button className="pill" onClick={() => run(api(clubPath(`metric-sets/${s.id}/`), { method: 'DELETE' }))}>{t('delete')}</button>}
                    </span>
                  </div>
                ))}
              </div>
            ))}
          </State>
          {draft && (
            <div className="card" style={{ background: '#121212' }}>
              <div className="row">
                <label className="small muted" htmlFor="sn">{t('set_name')}</label>
                <input id="sn" className="input grow" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
              </div>
              <span className="small muted">{t('choose_metrics')} · {draft.keys.length}/12</span>
              <div className="row" style={{ gap: 6 }}>
                {(defs.data || []).filter((d) => d.enabled).map((d) => (
                  <button key={d.key} className="pill" aria-pressed={draft.keys.includes(d.key)} onClick={() => toggle(d.key)}>
                    <span className="dot" style={{ background: CAT_COLOR[d.category] || '#a3a3a3', width: 6, height: 6 }} />{d.short_label || d.label}
                    {draft.keys.includes(d.key) && <span className="small faint">{draft.keys.indexOf(d.key) + 1}</span>}
                  </button>
                ))}
              </div>
              <div className="row">
                <button className="btn" disabled={!draft.name.trim() || !draft.keys.length} onClick={() => run(api(clubPath('metric-sets/'), {
                  method: 'POST', body: JSON.stringify({ name: draft.name.trim(), metric_keys: draft.keys, display: 'absolute', scope: 'personal' }) }).then(() => setDraft(null)))}>{t('create')}</button>
                <button className="pill" onClick={() => setDraft(null)}>{t('cancel')}</button>
              </div>
            </div>
          )}
        </section>
        {canManage && (
          <section className="card">
            <h2>{t('presets')}</h2>
            <State loading={presets.loading} error={presets.error}>
              {(presets.data || []).map((p) => (
                <div key={p.key} className="row" style={{ justifyContent: 'space-between', borderTop: '1px solid var(--line-soft)', paddingTop: 8 }}>
                  <span><b style={{ fontWeight: 500 }}>{p.name}</b><span className="small muted" style={{ display: 'block' }}>{p.description}</span></span>
                  {p.installed ? <span className="small faint">{t('installed')}</span>
                    : <button className="pill" onClick={() => run(api(clubPath('metric-sets/install_preset/'), { method: 'POST', body: JSON.stringify({ preset: p.key }) }))}>{t('install')}</button>}
                </div>
              ))}
            </State>
          </section>
        )}
      </div>
    </>
  );
}
