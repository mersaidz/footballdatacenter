"""Russian by default, English and Kazakh on request: ?lang= → saved preference → Accept-Language."""
import pytest

from clubs.models import StaffMembership

pytestmark = pytest.mark.django_db


def denied(client, club, **extra):
    return client.get(f'/api/clubs/{club.pk}/metrics/catalogue/', **extra)


def test_russian_by_default(make_member, club):
    _, scout = make_member(club, 'scout')
    r = denied(scout, club)
    assert r.status_code == 403 and r.data['detail'] == 'Ваша роль в клубе не даёт доступа к этим данным.'
    assert r['Content-Language'] == 'ru'


def test_saved_language_and_query_override(make_member, club):
    user, scout = make_member(club, 'scout')
    r = scout.patch('/api/me/', {'language': 'kk'}, format='json')
    assert r.status_code == 200 and r.data['language'] == 'kk'
    assert [lang['code'] for lang in r.data['languages']] == ['ru', 'en', 'kk']
    assert denied(scout, club).data['detail'].startswith('Клубтағы рөліңіз')
    assert denied(scout, club, QUERY_STRING='lang=en').data['detail'] == \
        'Your role in this club does not grant access to this data.'


def test_unknown_language_rejected(make_member, club):
    _, c = make_member(club, 'head_coach')
    assert c.patch('/api/me/', {'language': 'de'}, format='json').status_code == 400
    assert c.patch('/api/me/', {'email': 'x@y.z'}, format='json').data['email'] != 'x@y.z'   # read-only


def test_choice_labels_follow_language():
    from django.utils import translation
    with translation.override('ru'):
        assert str(StaffMembership.Role.HEAD_COACH.label) == 'Главный тренер'
    with translation.override('kk'):
        assert str(StaffMembership.Role.HEAD_COACH.label) == 'Бас бапкер'
    with translation.override('en'):
        assert str(StaffMembership.Role.HEAD_COACH.label) == 'Head coach'


def test_every_backend_string_is_translated():
    import polib
    from django.conf import settings
    for lang in ('ru', 'kk'):
        po = polib.pofile(str(settings.BASE_DIR / 'locale' / lang / 'LC_MESSAGES' / 'django.po'))
        assert po.untranslated_entries() == [], lang
