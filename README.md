# Football Data Center

A club-side football data platform: one place where a club's physical data (Catapult OpenField), event data (IMPECT, Wyscout, StatsBomb) and medical availability meet, behind one API with role-based access for the whole staff.

![Status](https://img.shields.io/badge/status-v0.2%20backend-blue)
![Tests](https://img.shields.io/badge/tests-166%20passing-green)
![Coverage](https://img.shields.io/badge/coverage-93%25-brightgreen)
![Django](https://img.shields.io/badge/django-6.0-darkgreen)

---

## The problem

A professional club pays for several data providers. Each has its own login, its own player IDs and its own export format. Physical data lives in OpenField, event data in IMPECT or Wyscout, and medical status in a spreadsheet the physio keeps. Answering a simple question like *"how did last week's training load relate to his output on Saturday?"* takes an analyst half a morning of CSV exports and VLOOKUPs.

Big clubs solve this with an in-house data centre built on the providers' APIs. This project is that data centre for clubs that can't hire a ten-person data team.

## Design principles

1. **Providers are plugins.** Every source implements one connector interface (`providers/connectors/base.py`): *fetch* raw JSON and *normalise* it into plain dataclasses. All database writes live in one provider-agnostic ingest service. Moving from open data to a club's real IMPECT/OpenField keys means writing one connector class. Nothing downstream changes.
2. **Identity resolution is a first-class problem.** The same player is `5503` in StatsBomb, a UUID in OpenField and `1234` in IMPECT. Joining physical and technical data is impossible until those IDs are reconciled, so the platform treats this as a core feature with a review queue, not an afterthought.
3. **Every row belongs to one club.** Data arrives under a club's own provider licence and must never leak into another tenant.
4. **Least privilege by role.** A scout, a head coach and a club doctor need very different slices of the same player.
5. **Raw data is never thrown away.** Provider responses are stored as received, so history can be re-parsed after a parser fix without re-downloading.

---

## What's built (v0.3)

| Area | What exists |
|---|---|
| **Tenancy** | `Club` → `Team` (own squads + opponents) → `Player`. `ClubOwnedModel` blocks cross-club foreign keys on every save, not only in forms. |
| **Staff & roles** | `StaffMembership` with 9 roles (club admin, sporting director, head/assistant coach, analyst, sports scientist, physio, doctor, scout). One user can work for several clubs. |
| **Domain model** | `Competition`, `Season`, `Match`, `MatchAppearance` (lineups + minutes), `TrainingSession` (with MD-codes), `Event` (normalised on-ball events), `PlayerLoad` (GPS metrics, match **xor** session, enforced in the DB), `PlayerAvailability` (encrypted diagnosis). |
| **Identity resolution** | `ExternalIdentity` maps any provider ID to an internal record. The resolver matches on DOB + name compatibility, falls back to accent/order-insensitive fuzzy matching, and refuses to guess when candidates are ambiguous. |
| **OpenField connector** | Catapult Connect API v6 (read-only): athletes, activities and per-athlete stats via `POST /stats`. Retries on 429/5xx, token never logged. Velocity-band → HSR/sprint mapping is configurable per club. |
| **Physical ingest** | Activities become training sessions with match-day codes (OpenField `DayCode` tag or computed). Match activities attach their loads to the event-data `Match` of the same day, which is the join between physical and technical data. |
| **Periods & participation** | Every activity is split into its periods (warm-up, halves, drills) with per-player load. A match's load counts **playing periods only**, so warm-up never inflates match demands or per-90. OpenField participation tags (Full / Part / Alternate) are stored so only full participants feed team norms. |
| **StatsBomb connector** | StatsBomb Open Data (free) over HTTP or from a local clone. Events are mapped to a common vocabulary and coordinates are rescaled to metres. |
| **Ingest pipeline** | Idempotent (re-runs give identical rows), atomic per match, raw payloads deduplicated by SHA-256, one failing match doesn't stop a season, and every sync is audited. |
| **API** | JWT auth; `/api/clubs/<id>/…` for teams, players, matches (+ lineups, filterable events), loads, availability and the identity review queue. |
| **Security** | Fernet field encryption for provider keys and medical text. Immutable audit log with secret-key guard. Soft-deleted users rejected on every request. Non-members get 404, not 403. Every read of a medical record is audited. |

### Verified on real data

Ingesting Argentina's full 2022 World Cup from StatsBomb Open Data takes about 10 seconds:

```
$ python manage.py ingest_statsbomb --club demo --create-club --competition 43 --season 106 --own-team Argentina
match #1: 3284 events, 31 appearances, 31 new players, 0 need review
...
match #7: 4354 events, 35 appearances, 18 new players, 0 need review
Done: 7 matches, 27538 events, 0 errors
```

Sanity checks against known facts: all 7 results and stages are correct. Messi has 7 appearances and **7 goals** (shoot-out kicks excluded via `period <= 4`). Re-running the command changes nothing.

### OpenField: built from the real API

Before writing the connector, `scripts/openfield_probe.py` (standard library only, read-only) mapped a live EU account. It recorded 16 endpoints with field names, types, units and rate limits (1001 requests per window, 150 for `/stats`), and wrote no tokens or personal data. The connector code is written against those recorded shapes, and the tests mock exactly them.

```
$ python manage.py sync_openfield --club demo --team "First Team" --days 90
```

| PlayerLoad field | OpenField slug(s) (default) |
|---|---|
| `total_distance_m` | `total_distance` |
| `hsr_distance_m` | sum of `velocity_band5..8_total_distance` |
| `sprint_distance_m` | sum of `velocity_band6..8_total_distance` |
| `accelerations` / `decelerations` | `gen2_acceleration_band7plus_…` / `gen2_acceleration_band2plus_total_effort_count` |
| `max_speed_kmh` | `max_vel` (m/s × 3.6) |
| `duration_min` | `field_time`, else `total_duration` (seconds / 60) |
| `player_load` | `total_player_load` |

**Speed thresholds travel with the data.** Where Band 5 and Band 6 start is an account setting in OpenField. The demo account uses 21 / 24 km/h, common in Iberian football. English literature uses 19.8 / 25.2. Every `PlayerLoad` stores the `hsr_threshold_kmh` / `sprint_threshold_kmh` it was measured with, set once per club via `sync_openfield --hsr-threshold 21 --sprint-threshold 24`. Comparing HSR across clubs or seasons without this is comparing different things.

**GPS spikes are flagged, not deleted.** A max speed above the player's personal best (OpenField `velocity_max`) + 10 %, or above 38 km/h for anyone, gets `quality_flags = ["max_speed_outlier"]`. The raw value stays for audit. Reports use `max_speed_for_reports` / `GET …/loads/?exclude_flagged=true`. On the demo account this flagged 11 of 442 loads: ten 47–53 km/h spikes, plus a 36 km/h reading from a player whose personal best is 27.8 km/h. A fixed cap alone would have missed that one. Clean values top out at 33.8 km/h. The flagged rows show 0 m of sprint distance, so OpenField's dwell-time filter had already kept the spikes out of the distance totals. Only the max-speed value was affected.

Slug mapping is also an account setting. Override per club with `ProviderAccount.config = {"metric_map": {"hsr_distance_m": ["velocity_band4_total_distance", …]}}`. Slugs that don't exist on an account are skipped automatically.

### Period roles: any naming, any language

Staff name periods however they like: "1st Half", "1half", "1 тайм", "Primeira parte", or just "1". `football/services/period_roles.py` resolves each period to a role. The first rule that answers wins:

| # | Source | Example |
|---|---|---|
| 1 | **Tag** on the period (tag type configurable, default `Period Type`) | tag "1st Half" → first half, whatever the name |
| 2 | **Club vocabulary**, learned from staff decisions | "Блок 1" → top-up, because an analyst said so once |
| 3 | **Dictionary** (EN, RU, PT, ES, DE, IT, FR) | `2ª Parte`, `Второй тайм`, `Halbzeit 2` → second half |
| 4 | **Match structure** | two consecutive 35–65' periods → halves, a short one before → warm-up, two ~15' after → extra time |
| 5 | **Default** (training only) | anything else in a session is a drill |

What is still unknown in a match goes to a review queue (`GET /periods/?needs_review=true`). One click (`POST /periods/{id}/assign_role/`) sets the role, teaches the club vocabulary, re-labels every period with the same name and recomputes the affected match loads. Staff decisions survive re-syncs. Sub-periods inside a half ("1st Half 0–15") become `segment` and are never counted twice.

On the demo account the J01 recording is Warm Up 16.8' + 1st Half 49.9' + 2nd Half 52.3'. Match load now covers 102', not 119'.

---

## Access matrix

Defined in one place, `clubs/permissions.py`, and pinned by a truth-table test.

| Role | Football data | Physical load | Availability status | Diagnosis & notes | Edit medical | Review ID links | Provider keys |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| Club admin | ✓ | | | | | ✓ | ✓ |
| Sporting director / Head & assistant coach / Sports scientist | ✓ | ✓ | ✓ | | | | |
| Analyst | ✓ | ✓ | ✓ | | | ✓ | |
| Physio / Doctor | ✓ | ✓ | ✓ | ✓ | ✓ | | |
| Scout | ✓ | | | | | | |

Two deliberate asymmetries:

- **Club admin cannot see medical data.** Administrative power is not clinical access, and health data is a GDPR special category.
- **Coaches see whether a player can train, not why.**

---

## Identity resolution

```
incoming provider player
        │
        ▼
 known ExternalIdentity? ──yes──► reuse (hot path)
        │ no
        ▼
 candidates in this club WITHOUT an ID from this provider
        │
        ├─ DOB equal + names compatible ──────► link, confirmed   (exact)
        ├─ DOB differs ───────────────────────► never the same person
        ├─ no DOB, near-identical name ───────► link, needs review (fuzzy)
        ├─ several equally good candidates ───► create new, needs review
        └─ nothing ───────────────────────────► create new, confirmed
```

A wrong merge is much worse than a duplicate. A duplicate is visible and easy to fix. A wrong merge silently mixes two players' loads. Every threshold therefore leans towards *create and flag*. Analysts work the queue at `GET /identities/?status=suggested`, then `POST …/confirm/` or `…/reject/`. A rejection creates a new player and moves that provider's events and appearances to them.

Names are compared accent- and order-insensitively, and long official names are handled. `"Lionel Messi"` vs `"Lionel Andrés Messi Cuccittini"` scores 0.95 (token subset). `"Silva"` vs `"Bernardo Silva"` does **not** match, because a single shared token is not enough.

## Conventions

- **Pitch coordinates:** metres on a 105 × 68 pitch, from the acting team's perspective. `x = 0` is the own goal line, `y = 0` is the acting team's left touchline.
- **Periods:** 1–2 regular time, 3–4 extra time, 5 penalty shoot-out. Shoot-out events are stored but excluded from match duration and minutes.
- **Minutes played** include stoppage time (derived from the last open-play event), so they are higher than "official" 90/120-minute counts.
- **Physical thresholds** follow common practice: HSR > 19.8 km/h, sprint > 25.2 km/h, accelerations/decelerations at ±3 m/s².

---

## API overview

```
POST /api/auth/token/                                 email + password → access/refresh JWT
GET  /api/clubs/                                      my clubs and my role in each

GET  /api/clubs/{id}/teams/?own=true
GET  /api/clubs/{id}/players/?team=&search=
GET  /api/clubs/{id}/matches/?team=
GET  /api/clubs/{id}/matches/{m}/lineups/
GET  /api/clubs/{id}/matches/{m}/events/?type=shot,pass&player=&team=
GET  /api/clubs/{id}/loads/?player=&match=&training_session=
GET  /api/clubs/{id}/availability/?current=true        (status only, or full record for medical staff)
POST /api/clubs/{id}/availability/                     (physio / doctor)
GET  /api/clubs/{id}/identities/?status=suggested
POST /api/clubs/{id}/identities/{i}/confirm/
POST /api/clubs/{id}/identities/{i}/reject/
```

## Quick start

**Fastest local setup (no Postgres needed).** [uv](https://docs.astral.sh/uv/) installs the right Python by itself:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh      # once
uv venv --python 3.13 && source .venv/bin/activate
uv pip install -r requirements-dev.txt
echo "DB_ENGINE=sqlite" >> .env                       # local file db.sqlite3
python manage.py migrate
python manage.py sync_openfield --club demo --create-club --team "First Team" --days 120
```

**Full setup.** Requires Python 3.12+ and PostgreSQL 15+.

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env        # fill DJANGO_SECRET_KEY and FERNET_KEY (commands inside)
createdb fdc
python manage.py migrate
python manage.py createsuperuser

# Load real data (StatsBomb Open Data, no key needed)
python manage.py ingest_statsbomb --list
python manage.py ingest_statsbomb --club demo --create-club --competition 43 --season 106 --own-team Argentina

# Give yourself a role in the demo club (Django admin → Staff memberships), then:
python manage.py runserver
pytest --cov
```

## Project layout

```
config/       settings, URLs, JWT soft-delete rule
core/         encryption, audit log, payload sanitiser (ported from Aurora)
accounts/     email-based User with soft delete
clubs/        Club, Team, Player, StaffMembership, role → capability matrix
football/     provider-agnostic domain model, match-day (MD) code service
providers/    ProviderAccount, RawPayload, ExternalIdentity,
              connectors/ (contracts, StatsBomb, OpenField),
              services/ (identity, event ingest, physical ingest)
scripts/      openfield_probe.py — API discovery, stdlib only
api/          DRF views, serializers, club-scoped permissions
```

## Roadmap

- **Next:** IMPECT connector (event data, slots into `EventDataConnector`). OpenField 10 Hz streams for custom thresholds and peak-intensity windows.
- **Metrics layer:** weekly load and ACWR, physical output per 90 relative to position, readiness traffic light, load ↔ technical-output joins.
- **Async sync:** Celery + scheduled pulls, provider webhooks.
- **Frontend:** a Monday-morning post-match report for S&C and a squad availability board for the head coach.
- **Ops:** Docker Compose, CI, deploy.

## Origin

Built on the security and data-integrity foundation of [Aurora](https://github.com/mersaidz/aurora-backend), my multi-wearable athlete data hub: encrypted fields, immutable audit trail, raw-payload preservation and soft-delete auth. The domain moved from one athlete with many devices to one club with many providers and many staff roles.

## License

Proprietary. All rights reserved. See [LICENSE](./LICENSE).
