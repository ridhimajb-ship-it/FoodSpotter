"""Identity matching between records from different sources.

Guiding rule: a record is never attached to a restaurant on name similarity alone.
Name + neighbourhood + *address corroboration* are all required for an automatic match; anything weaker is
returned as `needs_review` (a candidate for manual verification) or `ambiguous`, and the review is NOT
attributed to any restaurant until a human confirms it.
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional

_PUNCT_RE = re.compile(r"[^a-z0-9 ]+")
_ADDR_NOISE = {"bangalore", "bengaluru", "karnataka", "india", "road", "rd", "main", "cross", "near", "opposite", "opp", "behind", "the", "and", "in"}

NAME_MATCH_MIN = 0.92
ADDRESS_MATCH_MIN = 0.5


def normalize_name(name: str | None) -> str:
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().replace("&", " and ")
    s = _PUNCT_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return re.sub(r"^the ", "", s)


def name_similarity(a: str | None, b: str | None) -> float:
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    # "Cafe 1" and "Cafe 2" are different outlets: differing numbers must never read as a near-match.
    if re.findall(r"\d+", na) != re.findall(r"\d+", nb):
        return min(0.5, SequenceMatcher(None, na, nb).ratio())
    return SequenceMatcher(None, na, nb).ratio()


def address_tokens(addr: str | None) -> set[str]:
    if not addr:
        return set()
    s = unicodedata.normalize("NFKD", addr).encode("ascii", "ignore").decode().lower()
    toks = re.findall(r"[a-z0-9]+", s)
    # "5th" == "5" style ordinals so "5th block" and "5 block" agree
    toks = [re.sub(r"^(\d+)(?:st|nd|rd|th)$", r"\1", t) for t in toks]
    return {t for t in toks if t not in _ADDR_NOISE and len(t) > 1}


def address_score(source_addr: str | None, osm_addr: str | None) -> Optional[float]:
    """Share of the OSM address tokens that also occur in the source address; None when there is no evidence."""
    osm = address_tokens(osm_addr)
    src = address_tokens(source_addr)
    if not osm or not src:
        return None
    return len(osm & src) / len(osm)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@dataclass
class Candidate:
    restaurant_id: int
    name: str
    address: Optional[str]
    neighborhood: Optional[str]


@dataclass
class MatchResult:
    status: str  # matched | needs_review | ambiguous | no_candidate
    restaurant_id: Optional[int] = None  # only set for `matched`
    candidate_id: Optional[int] = None
    confidence: float = 0.0
    evidence: dict = field(default_factory=dict)


def match_source_record(
    name: str, address: str | None, neighborhood: str | None, candidates: list[Candidate]
) -> MatchResult:
    """Match a source record (e.g. a Zomato row) against existing restaurants."""
    scored = []
    for c in candidates:
        if neighborhood and c.neighborhood and c.neighborhood != neighborhood:
            continue  # different area => different branch, never a match
        sim = name_similarity(name, c.name)
        if sim < NAME_MATCH_MIN:
            continue
        addr = address_score(address, c.address)
        scored.append((c, sim, addr))

    if not scored:
        return MatchResult("no_candidate", evidence={"reason": "no same-area restaurant with a matching name"})

    corroborated = [(c, s, a) for c, s, a in scored if a is not None and a >= ADDRESS_MATCH_MIN]
    if len(corroborated) == 1:
        c, s, a = corroborated[0]
        conf = round(0.5 * s + 0.5 * min(1.0, a), 3)
        return MatchResult("matched", c.restaurant_id, c.restaurant_id, conf,
                           {"name_similarity": round(s, 3), "address_score": round(a, 3), "rule": "name+area+address"})
    if len(corroborated) > 1:
        best = sorted(corroborated, key=lambda t: (t[2], t[1]), reverse=True)
        if best[0][2] - best[1][2] >= 0.25:  # clearly the better branch
            c, s, a = best[0]
            return MatchResult("matched", c.restaurant_id, c.restaurant_id, round(0.5 * s + 0.5 * min(1.0, a), 3),
                               {"name_similarity": round(s, 3), "address_score": round(a, 3), "rule": "name+area+best-address"})
        return MatchResult("ambiguous", None, None, 0.0,
                           {"reason": "several branches match name and address equally well",
                            "candidate_ids": [c.restaurant_id for c, _, _ in best]})

    # Name + area agree but nothing corroborates the address.
    if len(scored) == 1:
        c, s, a = scored[0]
        return MatchResult("needs_review", None, c.restaurant_id, round(0.5 * s, 3),
                           {"name_similarity": round(s, 3), "address_score": a,
                            "reason": "name and area agree but the address is not corroborated"})
    return MatchResult("ambiguous", None, None, 0.0,
                       {"reason": "several same-name branches in the area and no address evidence to choose between them",
                        "candidate_ids": [c.restaurant_id for c, _, _ in scored]})
