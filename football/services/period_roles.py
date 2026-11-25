"""
What is this period? — resolving "1st Half", "1half", "1 тайм", "Primeira parte"
or just "1" to one role, whatever language and habit the staff use.

Resolution order, most to least trustworthy (the first that answers wins):

  1. tag        a provider tag of the club's chosen type (e.g. OpenField tag type
                "Period Type" with value "1st Half"). Names stop mattering.
  2. club       the club's own vocabulary, learned from staff decisions
                ("1 тайм" → first_half), see PeriodRoleMapping.
  3. dictionary multilingual patterns: EN / RU / PT / ES / DE / IT / FR.
  4. structure  matches only: two long consecutive periods are the halves, a short
                one right before them is the warm-up, two ~15' after are extra time.
  5. default    training only: anything unrecognised is a drill.
  else unknown → shown to analysts in the review queue; their answer becomes a
                club mapping (step 2) so the same name never asks twice.

Pure functions only: no database access, easy to test.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime

WARM_UP, FIRST, SECOND = 'warm_up', 'first_half', 'second_half'
ET1, ET2, PENALTIES, SEGMENT = 'extra_time_1', 'extra_time_2', 'penalties', 'segment'
TOP_UP, RECOVERY, REHAB, DRILL, UNKNOWN = 'top_up', 'recovery', 'rehab', 'drill', 'unknown'
HALVES = (FIRST, SECOND, ET1, ET2)
ALL_ROLES = {WARM_UP, FIRST, SECOND, ET1, ET2, PENALTIES, SEGMENT, TOP_UP, RECOVERY, REHAB, DRILL, UNKNOWN}

FIRST_WORDS = {'1', 'first', 'i', 'primeira', 'primeiro', 'primera', 'primer', 'primo', 'prima',
               'premiere', 'premier', 'erste', 'erster', 'ersten'}
SECOND_WORDS = {'2', 'second', 'ii', 'segunda', 'segundo', 'seconda', 'secondo', 'deuxieme', 'seconde',
                'zweite', 'zweiter', 'zweiten'}
FIRST_STEMS = ('перв',)
SECOND_STEMS = ('втор',)
HALF_WORDS = {'half', 'halves', 'h', 'ht', 'parte', 'tempo', 'mitad', 'tiempo', 'halbzeit', 'hz', 'period',
              'periodo', 'p', 't', 'temps', 'mi'}
TIME_WORDS = {'time', 'tiempo', 'tempo'}
# Ordinal suffixes split off by normalize(): '1st' → '1 st', '2ª' → '2 a'.
SUFFIX_TOKENS = {'st', 'nd', 'rd', 'th', 'a', 'o', 'er', 'eme', 'e', 'й', 'ый', 'ой'}
HALF_STEMS = ('тайм', 'полов', 'период')
EXTRA_WORDS = {'extra', 'et', 'aet', 'prolongacion', 'prolongamento', 'prorroga', 'prorrogacao', 'overtime',
               'ot', 'verlangerung', 'prolongation', 'supplementari', 'supplementare'}
EXTRA_STEMS = ('дополн', 'овертайм', 'экстра')

PATTERNS = [
    # 'penalty' / 'penalties' as a word, but not 'penaltybox' or 'penalty box' (a drill area).
    (PENALTIES, re.compile(r'\bpenalt(?:y|ies|is|i)\b(?! ?(?:box|area|spot))|пенальт|shoot ?out|elfmeter|'
                           r'\brigori\b|tirs au but')),
    (WARM_UP, re.compile(r'warm ?up|warming|warmup|\bwu\b|разминк|aquecimento|calentamiento|activaci|'
                         r'activation|aufwarm|riscaldamento|echauffement|pre ?match')),
    (REHAB, re.compile(r'return to play|\brtp\b|rehab|реабил|reintegr|individual return')),
    (TOP_UP, re.compile(r'top ?up|добор|compensat|complement|compensac|extra conditioning|subs? (work|top)')),
    (RECOVERY, re.compile(r'recovery|восстанов|regenera|recuperac|recupero|cool ?down|заминк')),
]

# Match structure heuristics (minutes).
HALF_MIN, HALF_MAX = 35, 65
MAX_GAP_BETWEEN_HALVES = 35
WARM_UP_MAX = 40
ET_MIN, ET_MAX = 10, 20


def normalize(name: str) -> str:
    """'1ª Parte' → '1 a parte'; 'Rondo_19v3' → 'rondo 19 v 3'; '2ndHalf' → '2 nd half'."""
    # Strip accents from Latin letters only ('ª' → 'a', 'ç' → 'c'); keep Cyrillic intact ('й' stays 'й').
    out: list[str] = []
    for c in unicodedata.normalize('NFKD', name or ''):
        if unicodedata.combining(c) and out and out[-1] < '\u0250':
            continue
        out.append(c)
    s = unicodedata.normalize('NFC', ''.join(out)).lower()
    s = re.sub(r"[_\-./,:;()\[\]#'’]+", ' ', s)
    s = re.sub(r'(?<=\d)(?=[^\d\s])|(?<=[^\d\s])(?=\d)', ' ', s)   # split digits from letters
    s = re.sub(r'(?<=[a-z])(?=half|halbzeit|tempo|parte)', ' ', s)  # '2ndhalf' → '2nd half'
    return re.sub(r'\s+', ' ', s).strip()


def _has(tokens: list[str], words: set[str], stems: tuple[str, ...] = ()) -> bool:
    return any(t in words or t.startswith(stems) for t in tokens) if stems else any(t in words for t in tokens)


def _is(token: str, words: set[str], stems: tuple[str, ...] = ()) -> bool:
    return token in words or (bool(stems) and token.startswith(stems))


def _ordinal(token: str) -> int:
    if _is(token, FIRST_WORDS, FIRST_STEMS):
        return 1
    if _is(token, SECOND_WORDS, SECOND_STEMS):
        return 2
    return 0


def dictionary_role(name: str) -> str | None:
    n = normalize(name)
    if not n:
        return None
    for role, rx in PATTERNS:
        if rx.search(n):
            return role
    tokens = [t for t in n.split() if t not in SUFFIX_TOKENS]
    extra = any(_is(t, EXTRA_WORDS, EXTRA_STEMS) for t in tokens)
    # The ordinal must sit right next to a half word: "1 тайм", "half 2", "segundo tiempo".
    # A digit elsewhere ("Game 10v10 2-3 pitch") says nothing about halves.
    found = set()
    for a, b in zip(tokens, tokens[1:]):
        for num_tok, word in ((a, b), (b, a)):
            k = _ordinal(num_tok)
            if not k:
                continue
            if _is(word, HALF_WORDS, HALF_STEMS) or (extra and (_is(word, EXTRA_WORDS, EXTRA_STEMS)
                                                                or word in TIME_WORDS)):
                found.add(k)
    if len(found) != 1:          # none, or ambiguous ("1st half 2nd part")
        return None
    k = found.pop()
    if extra:
        return ET1 if k == 1 else ET2
    return FIRST if k == 1 else SECOND


@dataclass
class PeriodInput:
    key: str
    name: str
    start: datetime
    end: datetime
    tags: dict[str, list[str]] = field(default_factory=dict)
    manual_role: str | None = None        # a staff decision always stands

    @property
    def minutes(self) -> float:
        return (self.end - self.start).total_seconds() / 60


@dataclass
class RoleDecision:
    role: str
    source: str
    confidence: float


def _tag_role(p: PeriodInput, tag_type: str | None) -> str | None:
    if not tag_type:
        return None
    for value in p.tags.get(tag_type, []):
        v = normalize(value).replace(' ', '_')
        if v in ALL_ROLES:
            return v
        role = dictionary_role(value)
        if role:
            return role
    return None


def classify(periods: list[PeriodInput], *, is_match: bool, club_map: dict[str, str] | None = None,
             tag_type: str | None = None) -> dict[str, RoleDecision]:
    club_map = club_map or {}
    out: dict[str, RoleDecision] = {}
    for p in periods:
        if p.manual_role:
            out[p.key] = RoleDecision(p.manual_role, 'manual', 1.0)
        elif (r := _tag_role(p, tag_type)):
            out[p.key] = RoleDecision(r, 'tag', 1.0)
        elif (r := club_map.get(normalize(p.name))):
            out[p.key] = RoleDecision(r, 'club', 0.95)
        elif (r := dictionary_role(p.name)):
            out[p.key] = RoleDecision(r, 'dictionary', 0.9)
        else:
            out[p.key] = RoleDecision(UNKNOWN, 'none', 0.0)

    ordered = sorted(periods, key=lambda p: p.start)
    if is_match:
        _demote_nested_halves(ordered, out)
        _apply_structure(ordered, out)
        _demote_nested_halves(ordered, out)
    else:
        for p in ordered:
            d = out[p.key]
            # Training has no halves: "1st half" of a game drill is just that drill.
            # Explicit staff signals (manual, tag, club mapping) are left alone.
            if d.role == UNKNOWN or (d.role in HALVES + (PENALTIES,) and d.source == 'dictionary'):
                out[p.key] = RoleDecision(DRILL, 'default', 0.5)
    return out


def _demote_nested_halves(ordered: list[PeriodInput], out: dict[str, RoleDecision]) -> None:
    """'1st Half 0-15' inside '1st Half' must not be counted twice: keep the longest as the half."""
    for role in HALVES:
        same = [p for p in ordered if out[p.key].role == role]
        if len(same) > 1:
            keep = max(same, key=lambda p: p.minutes)
            for p in same:
                if p is not keep and out[p.key].source != 'manual':
                    out[p.key] = RoleDecision(SEGMENT, out[p.key].source, out[p.key].confidence)
    # An unnamed period fully inside a playing period is a segment of it. Named parallel work
    # ("Warm up" of the subs during the 1st half, "Top ups") keeps its own role.
    halves = [p for p in ordered if out[p.key].role in HALVES]
    for p in ordered:
        if out[p.key].role not in (UNKNOWN, DRILL) or out[p.key].source == 'manual':
            continue
        if any(h.start <= p.start and p.end <= h.end and h is not p for h in halves):
            out[p.key] = RoleDecision(SEGMENT, 'structure', 0.8)


def _apply_structure(ordered: list[PeriodInput], out: dict[str, RoleDecision]) -> None:
    role_of = lambda p: out[p.key].role  # noqa: E731
    open_ = lambda p: role_of(p) == UNKNOWN  # noqa: E731

    first = next((p for p in ordered if role_of(p) == FIRST), None)
    second = next((p for p in ordered if role_of(p) == SECOND), None)
    long_unknown = [p for p in ordered if open_(p) and HALF_MIN <= p.minutes <= HALF_MAX]

    if first is None and second is None:
        for a, b in zip(long_unknown, long_unknown[1:]):
            gap = (b.start - a.end).total_seconds() / 60
            if 0 <= gap <= MAX_GAP_BETWEEN_HALVES:
                out[a.key] = RoleDecision(FIRST, 'structure', 0.75)
                out[b.key] = RoleDecision(SECOND, 'structure', 0.75)
                first, second = a, b
                break
    elif first is not None and second is None:
        b = next((p for p in long_unknown if p.start >= first.end), None)
        if b is not None:
            out[b.key] = RoleDecision(SECOND, 'structure', 0.7)
            second = b
    elif second is not None and first is None:
        a = next((p for p in reversed(long_unknown) if p.end <= second.start), None)
        if a is not None:
            out[a.key] = RoleDecision(FIRST, 'structure', 0.7)
            first = a

    if first is not None and not any(role_of(p) == WARM_UP for p in ordered):
        before = [p for p in ordered if open_(p) and p.end <= first.start and p.minutes <= WARM_UP_MAX]
        if before:
            out[before[-1].key] = RoleDecision(WARM_UP, 'structure', 0.6)

    if second is not None:
        after = [p for p in ordered if open_(p) and p.start >= second.end and ET_MIN <= p.minutes <= ET_MAX]
        if len(after) >= 2 and not any(role_of(p) in (ET1, ET2) for p in ordered):
            out[after[0].key] = RoleDecision(ET1, 'structure', 0.6)
            out[after[1].key] = RoleDecision(ET2, 'structure', 0.6)
