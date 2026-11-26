import { useState } from 'react';
import { Link } from 'react-router-dom';
import { clubPath, SquadStatus, useApi } from '../api';
import { t } from '../i18n';
import { LEVEL, State } from '../components/ui';

export const posLabel = (p: string) => (p ? t(`pos_${p}` as never) : t('pos_none'));

export default function Players() {
  const [qtext, setQ] = useState('');
  const q = useApi<SquadStatus>(clubPath('squad-status/'));
  const list = (q.data?.players || [])
    .filter((p) => !qtext || p.name.toLowerCase().includes(qtext.toLowerCase()))
    .sort((a, b) => (a.shirt_number ?? 99) - (b.shirt_number ?? 99) || a.name.localeCompare(b.name));
  return (
    <>
      <header className="top"><span>{t('nav_players')}</span><span className="grow" />
        <input className="input" type="search" placeholder={t('search')} aria-label={t('search')} value={qtext} onChange={(e) => setQ(e.target.value)} />
      </header>
      <div className="page">
        <h1>{t('players_title')}</h1>
        <State loading={q.loading} error={q.error} empty={!!q.data && !list.length} onRetry={q.reload}>
          <div className="grid" style={{ '--min': '220px' } as React.CSSProperties}>
            {list.map((p) => (
              <Link key={p.player_id} to={`/players/${p.player_id}`} className="card" style={{ flexDirection: 'row', alignItems: 'center', gap: 14, padding: 14 }}>
                <span className="num" style={{ fontSize: 26, fontWeight: 700, color: 'var(--accent-text)', width: 40, textAlign: 'center' }}>{p.shirt_number ?? '—'}</span>
                <span style={{ display: 'flex', flexDirection: 'column', gap: 4, minWidth: 0 }}>
                  <b style={{ fontWeight: 500 }}>{p.name}</b>
                  <span className="small muted">{posLabel(p.position)}</span>
                  <span className="row small" style={{ color: LEVEL[p.level].color }}><span className="dot" style={{ background: LEVEL[p.level].color }} />{t(`lvl_${p.level}`)}</span>
                </span>
              </Link>
            ))}
          </div>
        </State>
      </div>
    </>
  );
}
