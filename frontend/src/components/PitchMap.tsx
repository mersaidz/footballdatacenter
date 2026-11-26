// Interactive season map: shots (zoomed to the attacking half), progressive carries and passes
// with arrows, and an action heat map. Hover for minute / match / xG; filter to one match.
import { useMemo, useRef, useState } from 'react';
import { day, num, t } from '../i18n';
import { Seg } from './ui';

export type Shot = { x: number; y: number; end_x: number | null; end_y: number | null; xg: number; goal: boolean; match_id: number; minute: number; kind: string; body_part: string; pressure: boolean };
export type Arrow = { x: number; y: number; end_x: number; end_y: number; match_id: number; minute: number; bypassed?: number | null };
export interface MapMatch { match_id: number; date: string; home: boolean; opponent: string; score: string; result: string }
export interface MapData {
  shots: Shot[]; carries: Arrow[]; passes?: Arrow[]; average_position: { x: number; y: number } | null;
  heat?: { cols: number; rows: number; season: number[][]; matches: Record<string, number[][]> };
  match_log: MapMatch[];
}
type Layer = 'shots' | 'carries' | 'passes' | 'heat';
type Hover = { kind: 'shot'; item: Shot; px: number; py: number } | { kind: 'arrow'; item: Arrow; px: number; py: number } | null;

const COLOR = { carries: '#5fd0e0', passes: '#c4b5fd', goal: '#ff7a45', shot: '#fafafa', avg: '#fbbf24' };
const rShot = (xg: number) => 0.9 + Math.sqrt(xg) * 3.4;

function Markings() {
  const line = { fill: 'none', stroke: 'rgba(255,255,255,0.38)', strokeWidth: 0.35 };
  return (
    <g {...line}>
      <rect x="0" y="0" width="105" height="68" /><line x1="52.5" y1="0" x2="52.5" y2="68" />
      <circle cx="52.5" cy="34" r="9.15" /><circle cx="52.5" cy="34" r="0.4" fill="rgba(255,255,255,0.5)" />
      <rect x="0" y="13.84" width="16.5" height="40.32" /><rect x="88.5" y="13.84" width="16.5" height="40.32" />
      <rect x="0" y="24.84" width="5.5" height="18.32" /><rect x="99.5" y="24.84" width="5.5" height="18.32" />
      <circle cx="11" cy="34" r="0.4" fill="rgba(255,255,255,0.5)" /><circle cx="94" cy="34" r="0.4" fill="rgba(255,255,255,0.5)" />
      <path d="M16.5 26.7 A9.15 9.15 0 0 1 16.5 41.3" /><path d="M88.5 26.7 A9.15 9.15 0 0 0 88.5 41.3" />
      <rect x="-1.5" y="30.34" width="1.5" height="7.32" /><rect x="105" y="30.34" width="1.5" height="7.32" />
    </g>
  );
}

export default function PitchMap({ data, match, onMatch }: { data: MapData; match: number | null; onMatch: (m: number | null) => void }) {
  const [layer, setLayer] = useState<Layer>('shots');
  const [hover, setHover] = useState<Hover>(null);
  const box = useRef<HTMLDivElement>(null);
  const matches = useMemo(() => Object.fromEntries(data.match_log.map((m) => [m.match_id, m])), [data.match_log]);
  const inMatch = <T extends { match_id: number }>(xs: T[]) => (match ? xs.filter((x) => x.match_id === match) : xs);
  const shots = inMatch(data.shots);
  const arrows = inMatch(layer === 'passes' ? data.passes || [] : data.carries);
  const heat = data.heat ? (match ? data.heat.matches[String(match)] : data.heat.season) : null;
  const heatTotal = heat ? heat.flat().reduce((a, b) => a + b, 0) : 0;
  const heatMax = heat ? Math.max(1, ...heat.flat()) : 1;
  const half = layer === 'shots';
  const vb = half ? '50 -2 57 72' : '-2 -2 109 72';
  const at = (e: React.MouseEvent) => {
    const r = box.current!.getBoundingClientRect();
    return { px: e.clientX - r.left, py: e.clientY - r.top };
  };
  const mLabel = (id: number) => {
    const m = matches[id];
    return m ? `${day(m.date, { day: '2-digit', month: '2-digit', year: '2-digit' })} · ${m.home ? t('home') : t('away')}: ${m.opponent} ${m.score}` : '';
  };
  const goals = shots.filter((s) => s.goal).length;
  const xg = shots.reduce((a, s) => a + s.xg, 0);
  const gain = arrows.length ? arrows.reduce((a, c) => a + (c.end_x - c.x), 0) / arrows.length : 0;
  const summary = layer === 'shots'
    ? [[t('layer_shots'), String(shots.length)], [t('col_goals'), String(goals)], ['xG', num(xg, 2)], [t('xg_per_shot'), num(shots.length ? xg / shots.length : 0, 2)]]
    : layer === 'heat' ? [[t('layer_heat'), t('actions_n', { n: num(heatTotal) })]]
    : [[layer === 'passes' ? t('layer_passes') : t('layer_carries'), String(arrows.length)], [t('avg_gain'), t('gained', { m: num(gain) })]];
  const arrowColor = layer === 'passes' ? COLOR.passes : COLOR.carries;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <Seg label={t('season_map')} value={layer} onChange={(v) => { setLayer(v); setHover(null); }} options={[
          { value: 'shots', label: t('layer_shots') }, { value: 'carries', label: t('layer_carries') },
          { value: 'passes', label: t('layer_passes') }, { value: 'heat', label: t('layer_heat') }]} />
        <select className="input" aria-label={t('whole_season')} value={match ?? ''} onChange={(e) => onMatch(e.target.value ? Number(e.target.value) : null)} style={{ maxWidth: 260 }}>
          <option value="">{t('whole_season')}</option>
          {data.match_log.map((m) => <option key={m.match_id} value={m.match_id}>{mLabel(m.match_id)}</option>)}
        </select>
      </div>
      <div className="row" style={{ gap: 18 }}>
        {summary.map(([l, v]) => <span key={l}><span className="small muted">{l} </span><b className="num" style={{ fontWeight: 600 }}>{v}</b></span>)}
      </div>
      <div ref={box} style={{ position: 'relative' }} onMouseLeave={() => setHover(null)}>
        <svg viewBox={vb} role="img" aria-label={`${t('season_map')}: ${summary.map((s) => s.join(' ')).join(', ')}`} style={{ width: '100%', display: 'block', borderRadius: 10, background: '#10241a' }}>
          <defs>
            <marker id="arr-c" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="3.2" markerHeight="3.2" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill={COLOR.carries} /></marker>
            <marker id="arr-p" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="3.2" markerHeight="3.2" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill={COLOR.passes} /></marker>
            <linearGradient id="fade-c" x1="0" x2="1"><stop offset="0" stopColor={arrowColor} stopOpacity="0.1" /><stop offset="1" stopColor={arrowColor} stopOpacity="0.9" /></linearGradient>
          </defs>
          {Array.from({ length: 12 }, (_, i) => <rect key={i} x={i * 8.75} y="0" width="8.75" height="68" fill={i % 2 ? '#132b1f' : '#10241a'} />)}
          {layer === 'heat' && heat && heat.map((row, ry) => row.map((v, cx) => {
            const w = 105 / heat[0].length, h = 68 / heat.length, share = heatTotal ? v / heatTotal : 0;
            return (
              <g key={`${ry}-${cx}`}>
                <rect x={cx * w} y={ry * h} width={w} height={h} fill="#ff7a45" opacity={v ? Math.pow(v / heatMax, 1.6) * 0.85 : 0} />
                {share >= 0.03 && <text x={cx * w + w / 2} y={ry * h + h / 2 + 1.1} textAnchor="middle" fontSize="2.6" fill="#fff" opacity="0.9">{Math.round(share * 100)}%</text>}
              </g>
            );
          }))}
          <Markings />
          {(layer === 'carries' || layer === 'passes') && arrows.map((c, i) => {
            const active = hover?.kind === 'arrow' && hover.item === c;
            return (
              <g key={i}>
                <line x1={c.x} y1={c.y} x2={c.end_x} y2={c.end_y} stroke={arrowColor} strokeOpacity={hover && !active ? 0.12 : active ? 1 : 0.45}
                  strokeWidth={active ? 0.9 : 0.45} markerEnd={`url(#${layer === 'passes' ? 'arr-p' : 'arr-c'})`} strokeLinecap="round" />
                <line x1={c.x} y1={c.y} x2={c.end_x} y2={c.end_y} stroke="transparent" strokeWidth="2.4" style={{ cursor: 'pointer' }}
                  onMouseEnter={(e) => setHover({ kind: 'arrow', item: c, ...at(e) })} onClick={() => onMatch(c.match_id)} />
              </g>
            );
          })}
          {layer === 'shots' && shots.map((s, i) => {
            const active = hover?.kind === 'shot' && hover.item === s;
            return (
              <g key={i} style={{ cursor: 'pointer' }} onMouseEnter={(e) => setHover({ kind: 'shot', item: s, ...at(e) })} onClick={() => onMatch(s.match_id)}>
                {active && s.end_x != null && <line x1={s.x} y1={s.y} x2={s.end_x} y2={s.end_y!} stroke={s.goal ? COLOR.goal : '#fff'} strokeWidth="0.35" strokeDasharray="1 0.8" />}
                <circle cx={s.x} cy={s.y} r={rShot(s.xg)} fill={s.goal ? COLOR.goal : 'rgba(250,250,250,0.08)'} stroke={s.goal ? COLOR.goal : COLOR.shot}
                  strokeWidth={active ? 0.7 : 0.35} opacity={hover && !active ? 0.35 : 1} />
              </g>
            );
          })}
          {data.average_position && !match && <circle cx={data.average_position.x} cy={data.average_position.y} r="1.8" fill={COLOR.avg} stroke="#10241a" strokeWidth="0.6" />}
        </svg>
        {hover && (
          <div role="tooltip" style={{ position: 'absolute', left: Math.min(hover.px + 14, (box.current?.clientWidth || 400) - 230), top: Math.max(0, hover.py - 10),
            width: 220, background: 'rgba(17,17,17,0.96)', border: '1px solid var(--line)', borderRadius: 10, padding: '10px 12px', pointerEvents: 'none', fontSize: 12, lineHeight: 1.5 }}>
            <b style={{ fontWeight: 600 }}>{hover.item.minute}′</b> <span className="muted">{mLabel(hover.item.match_id)}</span>
            {hover.kind === 'shot' ? <div>
              <span style={{ color: hover.item.goal ? COLOR.goal : 'var(--text-2)', fontWeight: 600 }}>{hover.item.goal ? t('goal_word') : t('no_goal')}</span> · xG {num(hover.item.xg, 2)}
              <div className="muted">{[t(`shot_${hover.item.kind}` as never), t(`body_${hover.item.body_part}` as never), hover.item.pressure ? t('under_pressure') : '']
                .filter((x) => x && !x.startsWith('shot_') && !x.startsWith('body_')).join(' · ')}</div>
            </div> : <div>
              {t('gained', { m: num(hover.item.end_x - hover.item.x) })}
              {hover.item.bypassed ? <div className="muted">{t('bypassed_n', { n: num(hover.item.bypassed) })}</div> : null}
            </div>}
          </div>
        )}
      </div>
      <div className="row small muted" style={{ gap: 14 }}>
        {layer === 'shots' && <>
          <span className="row" style={{ gap: 6 }}><span className="dot" style={{ background: COLOR.goal }} />{t('goal_word')}</span>
          <span className="row" style={{ gap: 6 }}><span className="dot" style={{ border: '1px solid #fafafa' }} />{t('no_goal')}</span>
          <span className="row" style={{ gap: 6 }}>{t('xg_size')}:
            <svg width="62" height="16" aria-hidden="true">{[0.05, 0.2, 0.5].map((x, i) => <circle key={x} cx={8 + i * 20} cy="8" r={rShot(x) * 1.1} fill="none" stroke="#a3a3a3" strokeWidth="0.8" />)}</svg>
            <span className="faint">0,05 · 0,2 · 0,5</span></span>
        </>}
        {layer === 'carries' && <span style={{ color: COLOR.carries }}>→ {t('leg_carry')}</span>}
        {layer === 'passes' && <span style={{ color: COLOR.passes }}>→ {t('leg_pass')}</span>}
        {layer === 'heat' && <span>{t('heat_hint')}</span>}
        {!match && data.average_position && <span className="row" style={{ gap: 6 }}><span className="dot" style={{ background: COLOR.avg }} />{t('leg_avg')}</span>}
        <span>{t('attack_lr')}</span>
        {match && <button className="pill" onClick={() => onMatch(null)}>{t('show_all')}</button>}
      </div>
      <span className="small faint">{t('map_hint')}</span>
    </div>
  );
}
