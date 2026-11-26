// The questionnaire itself — the same form on the player's phone and when staff enter answers for him.
import { useState } from 'react';
import { Key, t } from '../i18n';

export const ITEMS = ['sleep_quality', 'energy', 'soreness', 'stress', 'mood'] as const;
export type Item = typeof ITEMS[number];
export const AREAS = ['head_neck', 'shoulder', 'chest', 'upper_back', 'lower_back', 'abdomen', 'groin', 'hip', 'quad', 'hamstring',
  'adductor', 'knee', 'calf', 'shin', 'ankle', 'foot', 'achilles'] as const;

export interface CheckinValues {
  sleep_quality: number; energy: number; soreness: number; stress: number; mood: number;
  sleep_hours: number | null; sore_areas: string[]; comment: string;
}

/** 1 = worst … 5 = best for every item. */
export const SCORE_COLOR = ['', '#f87171', '#fb923c', '#fbbf24', '#a3e635', '#4ade80'];
export const answerWord = (item: Item, v: number) => t(`a_${item}` as Key).split('|')[v - 1] || '';
export const areaLabel = (code: string) => t('areas').split('|')[AREAS.indexOf(code as typeof AREAS[number])] || code;

/** CR-10: green → red. */
export const rpeColor = (v: number) => (v <= 2 ? '#4ade80' : v <= 4 ? '#a3e635' : v <= 6 ? '#fbbf24' : v <= 8 ? '#fb923c' : '#f87171');

function Scale({ item, value, onChange, big }: { item: Item; value: number | null; onChange: (v: number) => void; big?: boolean }) {
  return (
    <fieldset className="q">
      <legend><span>{t(`q_${item}` as Key)}</span>{value ? <b style={{ color: SCORE_COLOR[value] }}>{answerWord(item, value)}</b> : null}</legend>
      <div className="scale" role="radiogroup" aria-label={t(`q_${item}` as Key)}>
        {[1, 2, 3, 4, 5].map((v) => (
          <button key={v} type="button" role="radio" aria-checked={value === v} aria-label={`${v} — ${answerWord(item, v)}`}
            onClick={() => onChange(v)} className={big ? 'big' : ''}
            style={value === v ? { background: SCORE_COLOR[v], borderColor: SCORE_COLOR[v], color: '#0a0a0a' } : undefined}>{v}</button>
        ))}
      </div>
      <div className="scale-ends small faint"><span>{answerWord(item, 1)}</span><span>{answerWord(item, 5)}</span></div>
    </fieldset>
  );
}

export function Questionnaire({ initial, onSubmit, busy, big, submitLabel }:
  { initial?: Partial<CheckinValues> | null; onSubmit: (v: CheckinValues) => void; busy?: boolean; big?: boolean; submitLabel?: string }) {
  const [v, setV] = useState<Record<Item, number | null>>({
    sleep_quality: initial?.sleep_quality ?? null, energy: initial?.energy ?? null, soreness: initial?.soreness ?? null,
    stress: initial?.stress ?? null, mood: initial?.mood ?? null,
  });
  const [hours, setHours] = useState<number>(initial?.sleep_hours ?? 8);
  const [areas, setAreas] = useState<string[]>(initial?.sore_areas ?? []);
  const [comment, setComment] = useState(initial?.comment ?? '');
  const done = ITEMS.every((i) => v[i] != null);
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!done) return;
    onSubmit({ ...(v as Record<Item, number>), sleep_hours: hours, sore_areas: (v.soreness ?? 5) < 5 ? areas : [], comment });
  };
  const toggle = (a: string) => setAreas((xs) => (xs.includes(a) ? xs.filter((x) => x !== a) : [...xs, a]));
  return (
    <form className="checkin" onSubmit={submit}>
      <Scale item="sleep_quality" value={v.sleep_quality} onChange={(x) => setV({ ...v, sleep_quality: x })} big={big} />
      <div className="q">
        <span>{t('q_sleep_hours')}</span>
        <div className="row" style={{ gap: 12, flexWrap: 'nowrap' }}>
          <button type="button" className="step" aria-label="−" onClick={() => setHours((h) => Math.max(0, h - 0.5))}>−</button>
          <b className="num" style={{ fontSize: 26, minWidth: 80, textAlign: 'center' }}>{hours.toFixed(1)} <span className="small muted">{t('hours_short')}</span></b>
          <button type="button" className="step" aria-label="+" onClick={() => setHours((h) => Math.min(16, h + 0.5))}>+</button>
        </div>
      </div>
      {(['energy', 'soreness'] as const).map((i) => <Scale key={i} item={i} value={v[i]} onChange={(x) => setV({ ...v, [i]: x })} big={big} />)}
      {v.soreness != null && v.soreness < 5 && (
        <div className="q">
          <span>{t('q_areas')}</span>
          <div className="row" style={{ gap: 6 }}>
            {AREAS.map((a) => <button key={a} type="button" className="chip" aria-pressed={areas.includes(a)} onClick={() => toggle(a)}>{areaLabel(a)}</button>)}
          </div>
        </div>
      )}
      {(['stress', 'mood'] as const).map((i) => <Scale key={i} item={i} value={v[i]} onChange={(x) => setV({ ...v, [i]: x })} big={big} />)}
      <label className="q">
        <span>{t('q_comment')}</span>
        <textarea className="input" rows={3} maxLength={1000} value={comment} onChange={(e) => setComment(e.target.value)} />
      </label>
      <button className="btn" disabled={!done || busy} style={big ? { minHeight: 52, fontSize: 16 } : undefined}>{submitLabel || t('pa_send')}</button>
    </form>
  );
}

export function RpePicker({ value, onPick, busy }: { value: number | null; onPick: (v: number) => void; busy?: boolean }) {
  const words = t('rpe_scale').split('|');
  return (
    <div className="rpe" role="radiogroup" aria-label={t('rpe_q')}>
      {Array.from({ length: 11 }, (_, i) => 10 - i).map((r) => (
        <button key={r} type="button" role="radio" aria-checked={value === r} disabled={busy} onClick={() => onPick(r)}
          style={value === r ? { background: rpeColor(r), borderColor: rpeColor(r), color: '#0a0a0a' } : undefined}>
          <b className="num" style={{ color: value === r ? '#0a0a0a' : rpeColor(r) }}>{r}</b><span>{words[r]}</span>
        </button>
      ))}
    </div>
  );
}
