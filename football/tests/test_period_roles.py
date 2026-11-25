"""Period role resolution: names in any language, club vocabulary, tags, match structure."""
from datetime import datetime, timedelta, timezone

import pytest

from football.services.period_roles import PeriodInput, classify, dictionary_role, normalize

T0 = datetime(2026, 8, 16, 18, 0, tzinfo=timezone.utc)


def p(key, name, start_min, length_min, **kw):
    return PeriodInput(key=key, name=name, start=T0 + timedelta(minutes=start_min),
                       end=T0 + timedelta(minutes=start_min + length_min), **kw)


@pytest.mark.parametrize('name,role', [
    ('1st Half', 'first_half'), ('2nd Half', 'second_half'), ('1half', 'first_half'), ('2half', 'second_half'),
    ('2ndHalf', 'second_half'), ('H1', 'first_half'), ('2H', 'second_half'), ('Half 1', 'first_half'),
    ('1 тайм', 'first_half'), ('2 тайм', 'second_half'), ('Первый тайм', 'first_half'), ('Второй тайм', 'second_half'),
    ('Primeira parte', 'first_half'), ('2ª Parte', 'second_half'), ('1º Tempo', 'first_half'),
    ('Segundo tiempo', 'second_half'), ('Halbzeit 2', 'second_half'),
    ('ET1', 'extra_time_1'), ('Extra time 2', 'extra_time_2'), ('Дополнительный тайм 1', 'extra_time_1'),
    ('Prolongamento 2', 'extra_time_2'), ('Penalties', 'penalties'),
    ('Warm Up', 'warm_up'), ('Разминка', 'warm_up'), ('Aquecimento', 'warm_up'), ('Échauffement', 'warm_up'),
    ('Return to Play session', 'rehab'), ('Top up', 'top_up'), ('Добор', 'top_up'), ('Cool down', 'recovery'),
    ('Rondo_19v3_centercircle', None), ('Set Pieces', None), ('1', None), ('Running', None),
])
def test_dictionary(name, role):
    assert dictionary_role(name) == role


def test_normalize_keeps_cyrillic_and_strips_latin_accents():
    assert normalize('2ª Parte') == '2 a parte'
    assert normalize('Второй тайм') == 'второй тайм'
    assert normalize('Rondo_19v3') == 'rondo 19 v 3'


def test_real_match_layout():
    d = classify([p('wu', 'Warm Up', 0, 17), p('h1', '1st Half', 20, 50), p('h2', '2nd Half', 85, 52)], is_match=True)
    assert {k: v.role for k, v in d.items()} == {'wu': 'warm_up', 'h1': 'first_half', 'h2': 'second_half'}
    assert all(v.source == 'dictionary' for v in d.values())


def test_bare_numbers_resolved_by_structure():
    d = classify([p('a', 'Pre', 0, 20), p('b', '1', 25, 47), p('c', '2', 87, 49)], is_match=True)
    assert (d['b'].role, d['b'].source) == ('first_half', 'structure')
    assert (d['c'].role, d['c'].source) == ('second_half', 'structure')
    assert (d['a'].role, d['a'].source) == ('warm_up', 'structure')


def test_one_named_half_finds_the_other():
    d = classify([p('h1', '1 тайм', 0, 46), p('x', 'B', 60, 48)], is_match=True)
    assert d['x'].role == 'second_half' and d['x'].source == 'structure'


def test_extra_time_by_structure():
    d = classify([p('h1', '1st Half', 0, 47), p('h2', '2nd Half', 62, 48), p('e1', 'A', 115, 15),
                  p('e2', 'B', 132, 16)], is_match=True)
    assert (d['e1'].role, d['e2'].role) == ('extra_time_1', 'extra_time_2')


def test_nested_segments_not_double_counted():
    d = classify([p('h1', '1st Half', 0, 47), p('h1a', '1st Half 0-15', 0, 15), p('h1b', '15-30', 15, 15),
                  p('h2', '2nd Half', 62, 48)], is_match=True)
    assert d['h1'].role == 'first_half'
    assert d['h1a'].role == 'segment' and d['h1b'].role == 'segment'


def test_unrecognised_match_period_goes_to_review():
    d = classify([p('h1', '1st Half', 0, 47), p('h2', '2nd Half', 62, 48), p('x', 'Analysis', 120, 5)], is_match=True)
    assert (d['x'].role, d['x'].source) == ('unknown', 'none')


def test_training_defaults_to_drill_and_has_no_halves():
    d = classify([p('a', 'Rondo', 0, 15), p('b', '1st half of game', 15, 20), p('c', 'Warm Up', 40, 10)],
                 is_match=False)
    assert d['a'].role == 'drill' and d['b'].role == 'drill' and d['c'].role == 'warm_up'
    assert d['a'].source == 'default'


def test_precedence_manual_tag_club_dictionary():
    periods = [
        p('m', 'Warm Up', 0, 10, manual_role='drill'),
        p('t', 'Warm Up', 10, 10, tags={'Period Type': ['1st Half']}),
        p('c', 'Блок 1', 20, 10),
        p('d', 'Warm Up', 30, 10),
    ]
    d = classify(periods, is_match=False, club_map={'блок 1': 'top_up'}, tag_type='Period Type')
    assert (d['m'].role, d['m'].source) == ('drill', 'manual')
    assert d['t'].source == 'tag'
    assert (d['c'].role, d['c'].source) == ('top_up', 'club')
    assert (d['d'].role, d['d'].source) == ('warm_up', 'dictionary')
