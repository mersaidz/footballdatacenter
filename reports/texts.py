"""
Words for printed reports, in the three platform languages. Kept beside the reports (not in gettext)
because they mirror the web app's own phrasing and change together with the report layouts.
"""
from __future__ import annotations

from datetime import date

T: dict[str, dict[str, str]] = {
    'ru': {
        'r_acwr_accdec_high': 'Рывков и торможений в {v} раза больше привычного', 'r_acwr_accdec_rising': 'Рывков и торможений быстро становится больше',
        'title': 'Статус состава', 'generated': 'Сформировано {t}', 'page': 'стр. {n}',
        'day_after': 'День после матча: {m}', 'days_after': '{n} дн. после матча: {m}',
        'lvl_reduce': 'Снизить нагрузку', 'lvl_hold': 'Не наращивать', 'lvl_build': 'Догрузить', 'lvl_plan': 'По плану',
        'lvl_out': 'Не тренируется',
        'hint_reduce': 'Скачок нагрузки, повышенный риск травмы', 'hint_hold': 'Нагрузка растёт быстро, держать уровень',
        'hint_build': 'Недогружен или возвращается', 'hint_plan': 'Всё в норме',
        'answered': 'Опрос: ответили {a} из {n}', 'not_training': 'Не тренируются: {n}',
        'md1': 'Тренировка после матча (MD+1)', 'recovery': 'Восстановительная', 'topup': 'Компенсаторная',
        'played60': 'сыграли 60′+', 'under60': 'меньше 60′', 'keepers': 'Вратари', 'keepers_hint': 'отдельно, с тренером вратарей',
        'col_status': 'Статус', 'col_no': '№', 'col_player': 'Игрок', 'col_why': 'Почему', 'col_feel': 'Самочувствие',
        'col_acwr_d': 'ACWR дист.', 'col_acwr_h': 'ACWR HSR', 'col_week': 'Км за 7 дн.', 'col_vs_prev': 'К пред. неделе',
        'col_last': 'Матч, мин', 'col_pos': 'Позиция', 'col_feel_total': 'Опрос, сумма', 'col_feel_usual': 'Обычно',
        'col_avail': 'Доступность', 'col_return': 'Вернётся', 'col_date': 'Дата',
        'feel_ok': 'в норме', 'feel_low': 'ниже нормы', 'feel_very_low': 'сильно ниже', 'feel_none': 'нет ответа',
        'in_range': 'В норме', 'gk_pl': 'PL',
        'r_acwr_dist_high': 'Нагрузка в {v} раза выше привычной', 'r_acwr_hsr_high': 'Скоростного бега в {v} раза больше привычного',
        'r_acwr_dist_rising': 'Нагрузка быстро растёт', 'r_acwr_hsr_rising': 'Скоростного бега больше привычного',
        'r_underloaded': 'Мало нагрузки: {v} от привычной', 'r_low_hsr': 'Мало скоростного бега', 'r_no_session': 'Нет тренировок с {d}',
        'r_wellness_low': 'Самочувствие ниже обычного', 'r_wellness_very_low': 'Самочувствие сильно ниже обычного',
        'r_no_topup_today': 'Нагрузки мало, но сегодня не догружаем',
        'r_unavailable': '{why}, вернётся ~{d}', 'r_unavailable_nodate': '{why}, срок не известен',
        'r_modified': 'Облегчённая тренировка: {why}', 'r_returning': 'Вернулся {d}: наращивать постепенно',
        'r_no_max_speed': 'Не бегал на 90% макс. скорости {v} дн.: добавить спринт',
        'r_gk_dives_high': 'Нагрузка нырков в {v} раза выше привычной', 'r_gk_dives_rising': 'Нагрузка нырков быстро растёт',
        'av_injury': 'травма', 'av_illness': 'болезнь', 'av_load_management': 'управление нагрузкой', 'av_personal': 'личные причины',
        'av_suspension': 'дисквалификация', 'av_international': 'сборная', 'av_other': 'без причины',
        'st_modified': 'облегчённая', 'st_unavailable': 'не тренируется',
        'rules': 'Снизить нагрузку: ACWR выше 1,5. Не наращивать: 1,3–1,5 или самочувствие ниже обычного. Догрузить: ниже 0,8, '
                 'мало HSR, 3+ дня без тренировок или давно не было бега на 90% Vmax. ACWR: нагрузка 7 дней к 28 (EWMA). '
                 'Ускорения и торможения (от 3 м/с²) по тем же порогам. Вратари: PlayerLoad вместо дистанции. Ответы на опрос в отчёт не попадают, только общий уровень.',
        'sheet': 'Статус', 'weekdays': 'пн вт ср чт пт сб вс',
    },
    'en': {
        'r_acwr_accdec_high': 'Accelerations and decelerations {v}× his usual', 'r_acwr_accdec_rising': 'Accelerations and decelerations rising fast',
        'title': 'Squad status', 'generated': 'Generated {t}', 'page': 'page {n}',
        'day_after': 'Day after the match: {m}', 'days_after': '{n} days after the match: {m}',
        'lvl_reduce': 'Reduce load', 'lvl_hold': 'Hold load', 'lvl_build': 'Build up', 'lvl_plan': 'As planned', 'lvl_out': 'Not training',
        'hint_reduce': 'Load spike, higher injury risk', 'hint_hold': 'Load rising fast, hold the level',
        'hint_build': 'Under-loaded or returning', 'hint_plan': 'All in range',
        'answered': 'Check-in: {a} of {n} answered', 'not_training': 'Not training: {n}',
        'md1': 'Session after the match (MD+1)', 'recovery': 'Recovery', 'topup': 'Top-up',
        'played60': 'played 60′+', 'under60': 'under 60′', 'keepers': 'Goalkeepers', 'keepers_hint': 'separately, with the GK coach',
        'col_status': 'Status', 'col_no': '#', 'col_player': 'Player', 'col_why': 'Why', 'col_feel': 'Wellness',
        'col_acwr_d': 'ACWR dist.', 'col_acwr_h': 'ACWR HSR', 'col_week': 'Km, 7 days', 'col_vs_prev': 'vs prev. week',
        'col_last': 'Match, min', 'col_pos': 'Position', 'col_feel_total': 'Check-in total', 'col_feel_usual': 'Usual',
        'col_avail': 'Availability', 'col_return': 'Back', 'col_date': 'Date',
        'feel_ok': 'normal', 'feel_low': 'below normal', 'feel_very_low': 'well below', 'feel_none': 'no answer',
        'in_range': 'In range', 'gk_pl': 'PL',
        'r_acwr_dist_high': 'Load {v}× his usual', 'r_acwr_hsr_high': 'High-speed running {v}× his usual',
        'r_acwr_dist_rising': 'Load rising fast', 'r_acwr_hsr_rising': 'More high-speed running than usual',
        'r_underloaded': 'Underloaded: {v} of his usual', 'r_low_hsr': 'Little high-speed running', 'r_no_session': 'No sessions since {d}',
        'r_wellness_low': 'Feeling below his usual', 'r_wellness_very_low': 'Feeling well below his usual',
        'r_no_topup_today': 'Underloaded, but no top-up today',
        'r_unavailable': '{why}, back ~{d}', 'r_unavailable_nodate': '{why}, return date unknown',
        'r_modified': 'Modified training: {why}', 'r_returning': 'Back since {d}: build up gradually',
        'r_no_max_speed': 'No run at 90% of top speed for {v} days: add a sprint',
        'r_gk_dives_high': 'Dive load {v}× his usual', 'r_gk_dives_rising': 'Dive load rising fast',
        'av_injury': 'injury', 'av_illness': 'illness', 'av_load_management': 'load management', 'av_personal': 'personal',
        'av_suspension': 'suspension', 'av_international': 'international duty', 'av_other': 'no reason given',
        'st_modified': 'modified', 'st_unavailable': 'not training',
        'rules': 'Reduce: ACWR above 1.5. Hold: 1.3–1.5 or feeling below usual. Build: below 0.8, little HSR, 3+ days without '
                 'sessions or no run at 90% Vmax for a week. ACWR: 7-day to 28-day load (EWMA). Accelerations and decelerations (from 3 m/s²) use the same thresholds. Keepers: PlayerLoad instead of '
                 'distance. Check-in answers are not printed, only the overall level.',
        'sheet': 'Status', 'weekdays': 'Mon Tue Wed Thu Fri Sat Sun',
    },
    'kk': {
        'r_acwr_accdec_high': 'Жылдамдату мен тежеу әдеттегіден {v} есе көп', 'r_acwr_accdec_rising': 'Жылдамдату мен тежеу тез көбейіп келеді',
        'title': 'Құрам мәртебесі', 'generated': 'Жасалды {t}', 'page': '{n}-бет',
        'day_after': 'Матчтан кейінгі күн: {m}', 'days_after': 'Матчтан кейін {n} күн: {m}',
        'lvl_reduce': 'Жүктемені азайту', 'lvl_hold': 'Арттырмау', 'lvl_build': 'Жүктемені қосу', 'lvl_plan': 'Жоспар бойынша',
        'lvl_out': 'Жаттықпайды',
        'hint_reduce': 'Жүктеменің секірісі, жарақат қаупі жоғары', 'hint_hold': 'Жүктеме тез өсуде, деңгейді ұстау',
        'hint_build': 'Жүктеме аз немесе оралып жатыр', 'hint_plan': 'Бәрі қалыпты',
        'answered': 'Сауалнама: {n} ішінен {a} жауап берді', 'not_training': 'Жаттықпайды: {n}',
        'md1': 'Матчтан кейінгі жаттығу (MD+1)', 'recovery': 'Қалпына келтіру', 'topup': 'Толықтыру',
        'played60': '60′+ ойнағандар', 'under60': '60′ аз', 'keepers': 'Қақпашылар', 'keepers_hint': 'бөлек, қақпашылар жаттықтырушысымен',
        'col_status': 'Мәртебе', 'col_no': '№', 'col_player': 'Ойыншы', 'col_why': 'Неліктен', 'col_feel': 'Хал-ахуал',
        'col_acwr_d': 'ACWR қаш.', 'col_acwr_h': 'ACWR HSR', 'col_week': 'Км, 7 күн', 'col_vs_prev': 'Алдыңғы аптаға',
        'col_last': 'Матч, мин', 'col_pos': 'Позиция', 'col_feel_total': 'Сауалнама жиыны', 'col_feel_usual': 'Әдетте',
        'col_avail': 'Қолжетімділік', 'col_return': 'Оралады', 'col_date': 'Күні',
        'feel_ok': 'қалыпты', 'feel_low': 'қалыптан төмен', 'feel_very_low': 'әлдеқайда төмен', 'feel_none': 'жауап жоқ',
        'in_range': 'Қалыпты', 'gk_pl': 'PL',
        'r_acwr_dist_high': 'Жүктеме әдеттегіден {v} есе жоғары', 'r_acwr_hsr_high': 'Жылдам жүгіріс әдеттегіден {v} есе көп',
        'r_acwr_dist_rising': 'Жүктеме тез өсіп келеді', 'r_acwr_hsr_rising': 'Жылдам жүгіріс әдеттегіден көп',
        'r_underloaded': 'Жүктеме аз: әдеттегінің {v} бөлігі', 'r_low_hsr': 'Жылдам жүгіріс аз', 'r_no_session': '{d} бастап жаттығу жоқ',
        'r_wellness_low': 'Хал-ахуалы әдеттегіден төмен', 'r_wellness_very_low': 'Хал-ахуалы әдеттегіден әлдеқайда төмен',
        'r_no_topup_today': 'Жүктеме аз, бірақ бүгін қоспаймыз',
        'r_unavailable': '{why}, ~{d} оралады', 'r_unavailable_nodate': '{why}, мерзімі белгісіз',
        'r_modified': 'Жеңілдетілген жаттығу: {why}', 'r_returning': '{d} оралды: біртіндеп арттыру',
        'r_no_max_speed': '{v} күн бойы макс. жылдамдықтың 90%-ына жүгірмеді: спринт қосу',
        'r_gk_dives_high': 'Сүңгу жүктемесі әдеттегіден {v} есе жоғары', 'r_gk_dives_rising': 'Сүңгу жүктемесі тез өсіп келеді',
        'av_injury': 'жарақат', 'av_illness': 'ауру', 'av_load_management': 'жүктемені басқару', 'av_personal': 'жеке себептер',
        'av_suspension': 'дисквалификация', 'av_international': 'құрама', 'av_other': 'себебі көрсетілмеген',
        'st_modified': 'жеңілдетілген', 'st_unavailable': 'жаттықпайды',
        'rules': 'Азайту: ACWR 1,5-тен жоғары. Арттырмау: 1,3–1,5 немесе хал-ахуал әдеттегіден төмен. Қосу: 0,8-ден төмен, HSR аз, '
                 '3+ күн жаттығусыз немесе апта бойы 90% Vmax жүгіріс болмаған. ACWR: 7 күндік жүктеменің 28 күндікке қатынасы (EWMA). '
                 'Жылдамдату мен тежеу (3 м/с²-тан) сол шектермен. Қақпашылар: қашықтықтың орнына PlayerLoad. Сауалнама жауаптары басылмайды, тек жалпы деңгей.',
        'sheet': 'Мәртебе', 'weekdays': 'дс сс ср бс жм сн жк',
    },
}


class Words:
    def __init__(self, lang: str):
        self.lang = lang if lang in T else 'ru'
        self.t = T[self.lang]

    def __call__(self, key: str, **kw) -> str:
        s = self.t.get(key) or T['ru'].get(key, key)
        return s.format(**kw) if kw else s

    def num(self, v, digits: int = 0) -> str:
        if v is None:
            return '—'
        s = f'{v:,.{digits}f}'.replace(',', ' ')
        return s if self.lang == 'en' else s.replace('.', ',')

    def day(self, iso: str | date | None) -> str:
        if not iso:
            return ''
        d = date.fromisoformat(iso) if isinstance(iso, str) else iso
        return d.strftime('%d.%m')

    def weekday(self, d: date) -> str:
        return self('weekdays').split()[d.weekday()]

    def reason(self, r: dict) -> str:
        code = r['code']
        if code.startswith('wellness_'):
            return self(f'r_{code}')                    # printed sheets never say what the player answered
        why = self(f"av_{r.get('reason') or 'other'}")
        if code == 'unavailable':
            s = self('r_unavailable', why=why, d=self.day(r['date'])) if r.get('date') else self('r_unavailable_nodate', why=why)
            return s[:1].upper() + s[1:]
        if code == 'modified':
            return self('r_modified', why=why)
        v = self.num(r.get('value'), 0 if code == 'no_max_speed' else 1) if r.get('value') is not None else ''
        return self(f'r_{code}', v=v, d=self.day(r.get('date')))

    def reasons(self, rs: list[dict]) -> str:
        """Same rules as the web app: at most two, HSR only when distance says nothing, 'no top-up' explains itself."""
        if not rs:
            return self('in_range')
        top = next((r for r in rs if r['code'] == 'no_topup_today'), None)
        if top:
            return '. '.join(self.reason(r) for r in [x for x in rs if x['code'].startswith('wellness_')][:1] + [top])
        dist = any(r['code'].startswith('acwr_dist') for r in rs)
        main = [r for r in rs if r['code'] != 'short_history' and not (dist and r['code'].startswith('acwr_hsr'))
                and not (r['code'] == 'low_hsr' and any(x['code'] == 'underloaded' for x in rs))]
        return '. '.join(self.reason(r) for r in main[:2]) or self('in_range')
