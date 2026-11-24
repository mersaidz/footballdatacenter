import pytest

from providers.connectors.statsbomb import to_metres


def test_coordinates_rescaled_to_metres():
    assert to_metres([120, 80]) == (105.0, 68.0)
    assert to_metres([60, 40]) == (52.5, 34.0)
    assert to_metres(None) == (None, None)


def test_normalize_matches(sb_connector):
    matches = sb_connector.normalize_matches(sb_connector.fetch_matches('1', '2').payload)
    m = matches[0]
    assert m.external_id == '100' and m.home_team.name == 'FC Astana'
    assert m.kickoff.isoformat() == '2024-05-12T17:30:00+00:00'
    assert m.status == 'played' and m.home_score == 2 and m.venue == 'Astana Arena'
    assert m.competition.name == 'Premier League' and m.season.name == '2024'


def test_normalize_lineups(sb_connector):
    apps = sb_connector.normalize_lineups(sb_connector.fetch_lineups('100').payload)
    by_id = {a.player.external_id: a for a in apps}
    assert '1004' not in by_id  # unused substitute
    assert by_id['1001'].started and by_id['1001'].minute_off == 70
    assert not by_id['1003'].started and by_id['1003'].minute_on == 70 and by_id['1003'].minute_off is None


def test_normalize_events(sb_connector):
    events = list(sb_connector.normalize_events(sb_connector.fetch_events('100').payload))
    by_id = {e.external_id: e for e in events}
    assert 'e-0' not in by_id                       # Starting XI is bookkeeping
    assert by_id['e-1'].outcome == 'complete'       # implicit successful pass
    assert by_id['e-2'].outcome == 'incomplete' and by_id['e-2'].under_pressure
    shot = by_id['e-3']
    assert shot.event_type == 'shot' and shot.outcome == 'goal' and shot.xg == pytest.approx(0.31)
    assert 'freeze_frame' not in shot.attributes['shot']
    assert by_id['e-4'].event_type == 'goalkeeper' and by_id['e-4'].outcome == 'success'
    assert by_id['e-5'].event_type == 'other' and by_id['e-5'].attributes['provider_type'] == 'Shield'
    assert by_id['e-3'].period_ms == 33 * 60_000 + 5_000
