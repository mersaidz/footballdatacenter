// UI strings in Russian (default), English and Kazakh. Abbreviations analysts use
// in every language (HSR, ACWR, xG, RPE, MDL, RHIE, S&C, packing) are not translated.
export type Lang = 'ru' | 'en' | 'kk';
const KEY = 'fdc.lang';

const D = {
  ru: {
    tab_overview: 'Обзор', sig_hrv: 'HRV', sig_sleep: 'Сон', sig_avail: 'Доступность', not_connected: 'Не подключено', available: 'Доступен', no_injury: 'Открытых травм нет', st_unavailable: 'Недоступен', st_modified: 'Облегчённая тренировка', this_week: 'Эта неделя', last_match_phys: 'Последний матч · физика', latest_ball: 'Последний матч · с мячом', rank_in_squad: '{r} из {n} в составе', not_measured: 'Не измерялось', minutes_on_pitch: 'минут на поле', leg_avg: 'Средняя позиция', leg_goal: 'Гол', leg_shot: 'Удар (размер — xG)', leg_carry: 'Прогрессивное ведение (10 м+)', attack_lr: 'Атака слева направо', checkin: 'Утренний опросник', recovery_soon: 'HRV, пульс покоя и сон из Whoop / Oura появятся после подключения.', checkin_soon: 'Ответы игроков (сон, энергия, болезненность, стресс, настроение) и RPE после сессии появятся после подключения приложения игрока.', packing_note: 'соперников обыграно', carry_note: 'метров к воротам', losses_note: 'потери мяча', prog_carries: 'Прогрессивные ведения', xg_note: '{s} ударов, {g} голов', no_match_data: 'Нет данных о матчах', source_real: 'OpenField · реальные', 
    brand_sub: 'Платформа данных клуба', nav_today: 'Сегодня', nav_sessions: 'Сессии', nav_week: 'Микроцикл', nav_players: 'Игроки',
    nav_settings: 'Настройки', logout: 'Выйти', loading: 'Загрузка…', error: 'Не удалось загрузить', retry: 'Повторить', empty: 'Пока пусто',
    login_title: 'Вход', email: 'Эл. почта', password: 'Пароль', login_btn: 'Войти', bad_credentials: 'Неверная почта или пароль',
    no_club: 'У вас нет доступа ни к одному клубу. Попросите администратора добавить вас.',
    // today
    today_title: 'Статус состава', as_of: 'На дату', day_after: 'День после матча', days_after: 'дн. после матча',
    lvl_modify: 'Коррекция', lvl_monitor: 'Наблюдение', lvl_ready: 'Готов', all: 'Все',
    hint_modify: 'Скорректировать сессию', hint_monitor: 'Проверить перед тренировкой', hint_ready: 'Тренируется по плану',
    col_status: 'Статус', col_player: 'Игрок', col_why: 'Почему', col_acwr_d: 'ACWR дистанция', col_acwr_h: 'ACWR HSR',
    col_week: 'Км за неделю', col_vs_prev: 'К прошлой неделе', col_last_match: 'Последний матч', in_range: 'В норме',
    r_acwr_dist_high: 'ACWR дистанции {v}', r_acwr_hsr_high: 'ACWR HSR {v}', r_acwr_dist_rising: 'ACWR дистанции растёт: {v}',
    r_underloaded: 'Недогружен, ACWR {v}', r_low_hsr: 'Мало HSR, ACWR {v}', r_no_session: 'Нет сессий с {d}',
    r_short_history: 'короткая история (с {d})', md1_groups: 'Группы на MD+1', recovery: 'Восстановление', topup: 'Добор',
    played60: '60′+ на поле', under60: 'меньше 60′',
    status_rules: 'Коррекция — ACWR выше 1,5. Наблюдение — ACWR 1,3–1,5, ниже 0,8, HSR ниже 0,6 или нет сессий 3+ дня. ACWR — экспоненциальная нагрузка 7 дней к 28.',
    // sessions
    sessions_title: 'История сессий', f_all: 'Все', f_matches: 'Матчи', f_trainings: 'Тренировки', from: 'С', to: 'По',
    week_of: 'Неделя с {d}', players_n: 'игроков: {n}', avg_full: 'среднее по полностью участвовавшим',
    t_match: 'Матч', t_training: 'Тренировка', minutes_short: 'мин', col_dur: 'Время', col_dist: 'Дистанция', col_hsr: 'HSR', col_spr: 'Спринт',
    // session detail
    whole_session: 'Вся сессия', previous: 'Предыдущая', next: 'Следующая', metric_view: 'Набор метрик',
    disp_absolute: 'Итог', disp_per_min: 'За мин', disp_per_90: 'На 90', not_play: 'не игровое время',
    part_full: 'ПОЛН', part_partial: 'ЧАСТ', part_alternate: 'ИНД', gps_spike: 'Всплеск GPS: скорость скрыта',
    sort_hint: 'Нажмите на колонку, чтобы отсортировать', back_sessions: 'Все сессии',
    // week
    week_title: 'Микроцикл', week_into: 'Неделя перед матчем', team_pct: 'Команда, % от требований матча',
    grid_title: 'Игроки × дни', grid_hint: '% от собственных требований матча игрока (на 90 минут)', no_session: 'нет сессии',
    rest: 'Выходной', metric: 'Метрика', m_dist: 'Дистанция', m_hsr: 'HSR', m_spr: 'Спринт', m_acc: 'Ускорения',
    // players
    players_title: 'Игроки', search: 'Поиск', pos_GK: 'Вратарь', pos_CB: 'Центральный защитник', pos_FB: 'Крайний защитник',
    pos_DM: 'Опорный полузащитник', pos_CM: 'Центральный полузащитник', pos_AM: 'Атакующий полузащитник', pos_W: 'Вингер',
    pos_CF: 'Нападающий', pos_none: 'Позиция не указана', foot_left: 'Левая нога', foot_right: 'Правая нога', foot_both: 'Обе ноги',
    tab_load: 'Нагрузка', tab_football: 'Футбол', tab_wellness: 'Самочувствие',
    acwr_chart: 'ACWR (EWMA 7/28)', acwr_band: 'Зелёная зона 0,8–1,3 · красная линия 1,5', daily_distance: 'Дистанция по дням',
    match_day: 'Матч', md_profile: 'Профиль по MD-дням', md_profile_hint: 'Средняя тренировка в % от его требований матча',
    match_log: 'Матчи', sessions_n: 'Сессии', matches_n: 'Матчи', match_minutes: 'Минут в матчах', top_speed: 'Макс. скорость',
    gps_flagged: 'Всплесков GPS', match_demand: 'Требования матча (на 90)', col_date: 'Дата', col_session: 'Сессия', col_min: 'Мин',
    col_p90: 'На 90', col_vmax: 'Vmax',
    fb_demo: 'Демо-связь: это реальные данные IMPECT игрока {src} ({squad}), привязанные для проверки платформы. Данные: IMPECT open data, только для анализа и исследований.',
    fb_none: 'По этому игроку пока нет событийных данных (IMPECT / Wyscout).', fb_profile: 'Профиль против лиги',
    fb_peers: 'На 90 · перцентиль среди {n} игроков позиции «{p}» с 450+ минутами', fb_minutes: '{m} минут · {n} матчей',
    fb_log: 'Матчи с мячом', season_map: 'Карта сезона: удары и ведения', col_opp: 'Соперник', col_score: 'Счёт', col_xg: 'xG', col_shots: 'Удары', col_goals: 'Голы',
    col_packing: 'Packing', col_carry: 'Ведение, м', col_losses: 'Потери', home: 'дома', away: 'в гостях',
    wellness_soon: 'Утренний опросник, RPE и данные Whoop / Oura появятся здесь после подключения модуля самочувствия.',
    // settings
    settings_title: 'Настройки', language: 'Язык интерфейса', profile: 'Профиль', name: 'Имя', save: 'Сохранить', saved: 'Сохранено',
    metric_sets: 'Наборы метрик', club_sets: 'Клубные', my_sets: 'Мои', make_default: 'Сделать по умолчанию', is_default: 'по умолчанию',
    delete: 'Удалить', new_set: 'Новый набор', set_name: 'Название', create: 'Создать', presets: 'Готовые наборы', install: 'Установить',
    installed: 'установлен', choose_metrics: 'Выберите до 12 метрик', role: 'Роль', club: 'Клуб', cancel: 'Отмена',
  },
  en: {
    tab_overview: 'Overview', sig_hrv: 'HRV', sig_sleep: 'Sleep', sig_avail: 'Availability', not_connected: 'Not connected', available: 'Available', no_injury: 'No open injury', st_unavailable: 'Unavailable', st_modified: 'Modified training', this_week: 'This week', last_match_phys: 'Last match · physical', latest_ball: 'Latest match · on the ball', rank_in_squad: '{r} of {n} in the squad', not_measured: 'Not measured', minutes_on_pitch: 'minutes on the pitch', leg_avg: 'Average position', leg_goal: 'Goal', leg_shot: 'Shot (size = xG)', leg_carry: 'Progressive carry (10 m+)', attack_lr: 'Attacking left to right', checkin: 'Morning check-in', recovery_soon: 'HRV, resting heart rate and sleep from Whoop / Oura appear once connected.', checkin_soon: 'Player answers (sleep, energy, soreness, stress, mood) and session RPE appear once the player app is connected.', packing_note: 'opponents bypassed', carry_note: 'metres towards goal', losses_note: 'turnovers', prog_carries: 'Progressive carries', xg_note: '{s} shots, {g} goals', no_match_data: 'No match data', source_real: 'OpenField · real', 
    brand_sub: 'Club data platform', nav_today: 'Today', nav_sessions: 'Sessions', nav_week: 'Microcycle', nav_players: 'Players',
    nav_settings: 'Settings', logout: 'Log out', loading: 'Loading…', error: 'Could not load', retry: 'Retry', empty: 'Nothing here yet',
    login_title: 'Sign in', email: 'Email', password: 'Password', login_btn: 'Sign in', bad_credentials: 'Wrong email or password',
    no_club: 'You don’t have access to any club yet. Ask an admin to add you.',
    today_title: 'Squad Status', as_of: 'As of', day_after: 'Day after the match', days_after: 'days after the match',
    lvl_modify: 'Modify', lvl_monitor: 'Monitor', lvl_ready: 'Ready', all: 'All',
    hint_modify: 'Adjust today’s session', hint_monitor: 'Check before training', hint_ready: 'Train as planned',
    col_status: 'Status', col_player: 'Player', col_why: 'Why', col_acwr_d: 'ACWR distance', col_acwr_h: 'ACWR HSR',
    col_week: 'Week km', col_vs_prev: 'vs prev week', col_last_match: 'Last match', in_range: 'Within range',
    r_acwr_dist_high: 'Distance ACWR {v}', r_acwr_hsr_high: 'HSR ACWR {v}', r_acwr_dist_rising: 'Distance ACWR rising: {v}',
    r_underloaded: 'Underloaded, ACWR {v}', r_low_hsr: 'Low HSR exposure, ACWR {v}', r_no_session: 'No session since {d}',
    r_short_history: 'short history (since {d})', md1_groups: 'MD+1 groups', recovery: 'Recovery', topup: 'Top-up',
    played60: '60′+ played', under60: 'under 60′',
    status_rules: 'Modify: ACWR above 1.5. Monitor: ACWR 1.3–1.5, below 0.8, HSR below 0.6 or no session for 3+ days. ACWR = exponentially weighted 7 vs 28 days.',
    sessions_title: 'Session History', f_all: 'All', f_matches: 'Matches', f_trainings: 'Training', from: 'From', to: 'To',
    week_of: 'Week of {d}', players_n: '{n} players', avg_full: 'average of full participants',
    t_match: 'Match', t_training: 'Training', minutes_short: 'min', col_dur: 'Time', col_dist: 'Distance', col_hsr: 'HSR', col_spr: 'Sprint',
    whole_session: 'Whole session', previous: 'Previous', next: 'Next', metric_view: 'Metric view',
    disp_absolute: 'Total', disp_per_min: 'Per min', disp_per_90: 'Per 90', not_play: 'not playing time',
    part_full: 'FULL', part_partial: 'PART', part_alternate: 'ALT', gps_spike: 'GPS spike: speed hidden',
    sort_hint: 'Click a column to sort', back_sessions: 'All sessions',
    week_title: 'Microcycle', week_into: 'Week into the match', team_pct: 'Team, % of match demand',
    grid_title: 'Players × days', grid_hint: '% of the player’s own match demand (per 90)', no_session: 'no session',
    rest: 'Rest day', metric: 'Metric', m_dist: 'Distance', m_hsr: 'HSR', m_spr: 'Sprint', m_acc: 'Accelerations',
    players_title: 'Players', search: 'Search', pos_GK: 'Goalkeeper', pos_CB: 'Centre-back', pos_FB: 'Full-back',
    pos_DM: 'Defensive midfielder', pos_CM: 'Central midfielder', pos_AM: 'Attacking midfielder', pos_W: 'Winger',
    pos_CF: 'Centre-forward', pos_none: 'Position not set', foot_left: 'Left foot', foot_right: 'Right foot', foot_both: 'Both feet',
    tab_load: 'Load', tab_football: 'Football', tab_wellness: 'Wellness',
    acwr_chart: 'ACWR (EWMA 7/28)', acwr_band: 'Green zone 0.8–1.3 · red line 1.5', daily_distance: 'Daily distance',
    match_day: 'Match', md_profile: 'Match-day profile', md_profile_hint: 'Average session as % of his match demand',
    match_log: 'Matches', sessions_n: 'Sessions', matches_n: 'Matches', match_minutes: 'Match minutes', top_speed: 'Top speed',
    gps_flagged: 'GPS spikes', match_demand: 'Match demand (per 90)', col_date: 'Date', col_session: 'Session', col_min: 'Min',
    col_p90: 'Per 90', col_vmax: 'Vmax',
    fb_demo: 'Demo link: these are {src}’s real IMPECT numbers ({squad}), attached to test the platform. Data: IMPECT open data, analysis and research only.',
    fb_none: 'No event data for this player yet (IMPECT / Wyscout).', fb_profile: 'Profile vs league',
    fb_peers: 'Per 90 · percentile among {n} players at “{p}” with 450+ minutes', fb_minutes: '{m} minutes · {n} matches',
    fb_log: 'On-the-ball match log', season_map: 'Season map: shots and carries', col_opp: 'Opponent', col_score: 'Score', col_xg: 'xG', col_shots: 'Shots', col_goals: 'Goals',
    col_packing: 'Packing', col_carry: 'Carrying, m', col_losses: 'Losses', home: 'home', away: 'away',
    wellness_soon: 'Morning check-in, RPE and Whoop / Oura data will appear here once the wellness module is connected.',
    settings_title: 'Settings', language: 'Interface language', profile: 'Profile', name: 'Name', save: 'Save', saved: 'Saved',
    metric_sets: 'Metric views', club_sets: 'Club', my_sets: 'Mine', make_default: 'Make default', is_default: 'default',
    delete: 'Delete', new_set: 'New view', set_name: 'Name', create: 'Create', presets: 'Ready-made views', install: 'Install',
    installed: 'installed', choose_metrics: 'Pick up to 12 metrics', role: 'Role', club: 'Club', cancel: 'Cancel',
  },
  kk: {
    tab_overview: 'Шолу', sig_hrv: 'HRV', sig_sleep: 'Ұйқы', sig_avail: 'Қолжетімділік', not_connected: 'Қосылмаған', available: 'Дайын', no_injury: 'Ашық жарақат жоқ', st_unavailable: 'Дайын емес', st_modified: 'Жеңілдетілген жаттығу', this_week: 'Осы апта', last_match_phys: 'Соңғы матч · физика', latest_ball: 'Соңғы матч · доппен', rank_in_squad: 'құрамда {n} ішінде {r}-орын', not_measured: 'Өлшенбеген', minutes_on_pitch: 'алаңдағы минут', leg_avg: 'Орташа позиция', leg_goal: 'Гол', leg_shot: 'Соққы (өлшемі — xG)', leg_carry: 'Прогрессивті доп жүргізу (10 м+)', attack_lr: 'Шабуыл солдан оңға', checkin: 'Таңғы сауалнама', recovery_soon: 'Whoop / Oura-дан HRV, тыныштықтағы пульс және ұйқы қосылғаннан кейін шығады.', checkin_soon: 'Ойыншы жауаптары (ұйқы, қуат, ауырсыну, стресс, көңіл-күй) және сессия RPE ойыншы қосымшасы қосылғаннан кейін шығады.', packing_note: 'қарсылас өтілді', carry_note: 'қақпаға қарай метр', losses_note: 'доп жоғалту', prog_carries: 'Прогрессивті доп жүргізу', xg_note: '{s} соққы, {g} гол', no_match_data: 'Матч деректері жоқ', source_real: 'OpenField · нақты', 
    brand_sub: 'Клубтың деректер платформасы', nav_today: 'Бүгін', nav_sessions: 'Сессиялар', nav_week: 'Микроцикл', nav_players: 'Ойыншылар',
    nav_settings: 'Баптаулар', logout: 'Шығу', loading: 'Жүктелуде…', error: 'Жүктеу мүмкін болмады', retry: 'Қайталау', empty: 'Әзірге бос',
    login_title: 'Кіру', email: 'Эл. пошта', password: 'Құпиясөз', login_btn: 'Кіру', bad_credentials: 'Пошта немесе құпиясөз қате',
    no_club: 'Сізде әзірге ешбір клубқа қол жеткізу жоқ. Әкімшіден қосуды сұраңыз.',
    today_title: 'Құрам жағдайы', as_of: 'Күні', day_after: 'Матчтан кейінгі күн', days_after: 'күн матчтан кейін',
    lvl_modify: 'Түзету', lvl_monitor: 'Бақылау', lvl_ready: 'Дайын', all: 'Барлығы',
    hint_modify: 'Бүгінгі сессияны түзету', hint_monitor: 'Жаттығу алдында тексеру', hint_ready: 'Жоспар бойынша',
    col_status: 'Күйі', col_player: 'Ойыншы', col_why: 'Себебі', col_acwr_d: 'ACWR қашықтық', col_acwr_h: 'ACWR HSR',
    col_week: 'Апталық км', col_vs_prev: 'Өткен аптаға', col_last_match: 'Соңғы матч', in_range: 'Қалыпты',
    r_acwr_dist_high: 'Қашықтық ACWR {v}', r_acwr_hsr_high: 'HSR ACWR {v}', r_acwr_dist_rising: 'Қашықтық ACWR өсуде: {v}',
    r_underloaded: 'Жүктеме аз, ACWR {v}', r_low_hsr: 'HSR аз, ACWR {v}', r_no_session: '{d} бастап сессия жоқ',
    r_short_history: 'қысқа тарих ({d} бастап)', md1_groups: 'MD+1 топтары', recovery: 'Қалпына келу', topup: 'Толықтыру',
    played60: '60′+ алаңда', under60: '60′-тан аз',
    status_rules: 'Түзету — ACWR 1,5-тен жоғары. Бақылау — ACWR 1,3–1,5, 0,8-ден төмен, HSR 0,6-дан төмен немесе 3+ күн сессия жоқ. ACWR — 7 күннің 28 күнге экспоненциалды қатынасы.',
    sessions_title: 'Сессиялар тарихы', f_all: 'Барлығы', f_matches: 'Матчтар', f_trainings: 'Жаттығулар', from: 'Бастап', to: 'Дейін',
    week_of: '{d} аптасы', players_n: 'ойыншы: {n}', avg_full: 'толық қатысқандардың орташасы',
    t_match: 'Матч', t_training: 'Жаттығу', minutes_short: 'мин', col_dur: 'Уақыт', col_dist: 'Қашықтық', col_hsr: 'HSR', col_spr: 'Спринт',
    whole_session: 'Бүкіл сессия', previous: 'Алдыңғы', next: 'Келесі', metric_view: 'Метрика жиынтығы',
    disp_absolute: 'Жиыны', disp_per_min: 'Минутына', disp_per_90: '90-ға', not_play: 'ойын уақыты емес',
    part_full: 'ТОЛЫҚ', part_partial: 'ІШІНАРА', part_alternate: 'ЖЕКЕ', gps_spike: 'GPS ауытқуы: жылдамдық жасырылды',
    sort_hint: 'Сұрыптау үшін бағанды басыңыз', back_sessions: 'Барлық сессиялар',
    week_title: 'Микроцикл', week_into: 'Матч алдындағы апта', team_pct: 'Команда, матч талабының %',
    grid_title: 'Ойыншылар × күндер', grid_hint: 'Ойыншының өз матч талабының % (90 минутқа)', no_session: 'сессия жоқ',
    rest: 'Демалыс', metric: 'Метрика', m_dist: 'Қашықтық', m_hsr: 'HSR', m_spr: 'Спринт', m_acc: 'Үдеулер',
    players_title: 'Ойыншылар', search: 'Іздеу', pos_GK: 'Қақпашы', pos_CB: 'Орталық қорғаушы', pos_FB: 'Қапталдағы қорғаушы',
    pos_DM: 'Тірек жартылай қорғаушы', pos_CM: 'Орталық жартылай қорғаушы', pos_AM: 'Шабуылшы жартылай қорғаушы', pos_W: 'Қанат ойыншысы',
    pos_CF: 'Шабуылшы', pos_none: 'Позиция көрсетілмеген', foot_left: 'Сол аяқ', foot_right: 'Оң аяқ', foot_both: 'Екі аяқ',
    tab_load: 'Жүктеме', tab_football: 'Футбол', tab_wellness: 'Көңіл-күй',
    acwr_chart: 'ACWR (EWMA 7/28)', acwr_band: 'Жасыл аймақ 0,8–1,3 · қызыл сызық 1,5', daily_distance: 'Күндік қашықтық',
    match_day: 'Матч', md_profile: 'MD күндері бойынша профиль', md_profile_hint: 'Орташа жаттығу, оның матч талабының %',
    match_log: 'Матчтар', sessions_n: 'Сессиялар', matches_n: 'Матчтар', match_minutes: 'Матчтағы минуттар', top_speed: 'Ең жоғары жылдамдық',
    gps_flagged: 'GPS ауытқулары', match_demand: 'Матч талабы (90-ға)', col_date: 'Күні', col_session: 'Сессия', col_min: 'Мин',
    col_p90: '90-ға', col_vmax: 'Vmax',
    fb_demo: 'Демо-байланыс: бұл {src} ойыншысының нақты IMPECT деректері ({squad}), платформаны тексеру үшін байланыстырылған. Деректер: IMPECT open data, тек талдау мен зерттеуге.',
    fb_none: 'Бұл ойыншы бойынша оқиға деректері әлі жоқ (IMPECT / Wyscout).', fb_profile: 'Лигамен салыстыру',
    fb_peers: '90-ға · «{p}» позициясындағы 450+ минут ойнаған {n} ойыншы арасындағы перцентиль', fb_minutes: '{m} минут · {n} матч',
    fb_log: 'Доппен матчтар', season_map: 'Маусым картасы: соққылар мен доп жүргізу', col_opp: 'Қарсылас', col_score: 'Есеп', col_xg: 'xG', col_shots: 'Соққылар', col_goals: 'Голдар',
    col_packing: 'Packing', col_carry: 'Доп жүргізу, м', col_losses: 'Жоғалтулар', home: 'үйде', away: 'қонақта',
    wellness_soon: 'Таңғы сауалнама, RPE және Whoop / Oura деректері көңіл-күй модулі қосылғаннан кейін осында шығады.',
    settings_title: 'Баптаулар', language: 'Интерфейс тілі', profile: 'Профиль', name: 'Аты', save: 'Сақтау', saved: 'Сақталды',
    metric_sets: 'Метрика жиынтықтары', club_sets: 'Клубтық', my_sets: 'Менікі', make_default: 'Әдепкі ету', is_default: 'әдепкі',
    delete: 'Жою', new_set: 'Жаңа жиынтық', set_name: 'Атауы', create: 'Жасау', presets: 'Дайын жиынтықтар', install: 'Орнату',
    installed: 'орнатылған', choose_metrics: '12-ге дейін метрика таңдаңыз', role: 'Рөлі', club: 'Клуб', cancel: 'Болдырмау',
  },
} as const;

export type Key = keyof typeof D.ru;
export const LANGS: { code: Lang; label: string }[] = [{ code: 'ru', label: 'RU' }, { code: 'en', label: 'EN' }, { code: 'kk', label: 'KZ' }];

export function getLang(): Lang {
  try { const v = localStorage.getItem(KEY); if (v === 'ru' || v === 'en' || v === 'kk') return v; } catch { /* ignore */ }
  return 'ru';
}
export function setLang(l: Lang) { try { localStorage.setItem(KEY, l); } catch { /* ignore */ } }

export function t(key: Key, vars: Record<string, string | number> = {}): string {
  const s: string = (D[getLang()] as Record<string, string>)[key] ?? D.ru[key] ?? key;
  return s.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? ''));
}

const LOCALE = { ru: 'ru-RU', en: 'en-GB', kk: 'kk-KZ' };
export const num = (v: number | null | undefined, digits = 0) =>
  v == null ? '—' : v.toLocaleString(LOCALE[getLang()], { minimumFractionDigits: digits, maximumFractionDigits: digits });
export const day = (iso: string, opts: Intl.DateTimeFormatOptions = { day: '2-digit', month: '2-digit' }) =>
  new Date(iso + (iso.length === 10 ? 'T12:00:00' : '')).toLocaleDateString(LOCALE[getLang()], opts);
export const weekday = (iso: string) => day(iso, { weekday: 'short' });
