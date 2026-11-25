"""
The contract every provider connector implements.

A connector does two things only:
  1. fetch   — talk to the provider and return raw JSON (no DB access);
  2. normalise — turn raw JSON into the dataclasses below.

Two families share the base class:
  - EventDataConnector    — matches, lineups, on-ball events (StatsBomb, IMPECT, Wyscout)
  - PhysicalDataConnector — activities and per-athlete load (OpenField, see openfield.py)

The ingest services (providers.services.ingest / physical_ingest) consume the
dataclasses and own all database writes. Swapping StatsBomb Open Data for a club's real
IMPECT/OpenField keys therefore means writing one new connector class;
nothing downstream changes.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable


@dataclass(frozen=True)
class NormalizedCompetition:
    external_id: str
    name: str
    country: str = ''
    gender: str = 'male'


@dataclass(frozen=True)
class NormalizedSeason:
    external_id: str
    name: str


@dataclass(frozen=True)
class NormalizedTeam:
    external_id: str
    name: str
    gender: str = 'male'
    country: str = ''


@dataclass(frozen=True)
class NormalizedPlayer:
    external_id: str
    full_name: str
    known_name: str = ''
    date_of_birth: date | None = None
    nationality: str = ''


@dataclass(frozen=True)
class NormalizedMatch:
    external_id: str
    competition: NormalizedCompetition | None
    season: NormalizedSeason | None
    home_team: NormalizedTeam
    away_team: NormalizedTeam
    kickoff: datetime
    status: str
    home_score: int | None = None
    away_score: int | None = None
    stage: str = ''
    venue: str = ''


@dataclass(frozen=True)
class NormalizedAppearance:
    team_external_id: str
    player: NormalizedPlayer
    started: bool
    position: str = ''
    shirt_number: int | None = None
    minute_on: int | None = None
    minute_off: int | None = None   # None = played until the final whistle


@dataclass(frozen=True)
class NormalizedEvent:
    external_id: str
    sequence: int
    period: int
    minute: int
    second: int
    period_ms: int
    event_type: str
    team_external_id: str
    player_external_id: str | None = None
    outcome: str = ''
    possession: int | None = None
    under_pressure: bool = False
    x: float | None = None
    y: float | None = None
    end_x: float | None = None
    end_y: float | None = None
    xg: float | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class FetchedResource:
    """Raw provider response + the identifiers needed to store it in RawPayload."""
    resource_type: str
    external_id: str
    payload: Any
    provider_api_version: str = ''


class BaseConnector(abc.ABC):
    provider: str = ''
    schema_version: str = '1'

    def __init__(self, account=None):
        self.account = account


class EventDataConnector(BaseConnector):
    """Match-centric providers: StatsBomb, IMPECT, Wyscout."""

    # --- fetch -----------------------------------------------------------------
    @abc.abstractmethod
    def fetch_matches(self, competition_id: str, season_id: str) -> FetchedResource: ...

    @abc.abstractmethod
    def fetch_lineups(self, match_id: str) -> FetchedResource: ...

    @abc.abstractmethod
    def fetch_events(self, match_id: str) -> FetchedResource: ...

    # --- normalise -------------------------------------------------------------
    @abc.abstractmethod
    def normalize_matches(self, payload: Any) -> list[NormalizedMatch]: ...

    @abc.abstractmethod
    def normalize_lineups(self, payload: Any) -> list[NormalizedAppearance]: ...

    @abc.abstractmethod
    def normalize_events(self, payload: Any) -> Iterable[NormalizedEvent]: ...


# --- physical data -------------------------------------------------------------

@dataclass(frozen=True)
class NormalizedActivity:
    """One recorded session in a tracking system (training or match)."""
    external_id: str
    name: str
    start: datetime
    end: datetime | None
    day_code: str = ''          # e.g. "MD-1", taken from the provider when it has one
    is_match: bool = False
    tags: dict[str, list[str]] = field(default_factory=dict)   # tag type → tag names


@dataclass(frozen=True)
class NormalizedLoad:
    activity_external_id: str
    athlete_external_id: str
    duration_min: float | None = None
    total_distance_m: float | None = None
    hsr_distance_m: float | None = None
    sprint_distance_m: float | None = None
    sprint_count: int | None = None
    accelerations: int | None = None
    decelerations: int | None = None
    max_speed_kmh: float | None = None
    player_load: float | None = None
    extra_metrics: dict[str, Any] = field(default_factory=dict)


class PhysicalDataConnector(BaseConnector):
    """Tracking providers: Catapult OpenField (GPS/LPS), later others."""

    @abc.abstractmethod
    def fetch_athletes(self) -> FetchedResource: ...

    @abc.abstractmethod
    def fetch_activities(self, start: datetime, end: datetime) -> FetchedResource: ...

    @abc.abstractmethod
    def fetch_activity_stats(self, activity_ids: list[str]) -> FetchedResource: ...

    @abc.abstractmethod
    def normalize_athletes(self, payload: Any) -> list[NormalizedPlayer]: ...

    @abc.abstractmethod
    def normalize_activities(self, payload: Any) -> list[NormalizedActivity]: ...

    @abc.abstractmethod
    def normalize_stats(self, payload: Any) -> list[NormalizedLoad]: ...
