"""
Internal representation used while reconstructing an Abusua Pedigree Studio
session from GA4GH inputs, plus serialisation to the Abusua ``.json`` format.

The Abusua session shape we emit::

    {
      "v": 1,
      "fam": "FAMILY-ID",
      "people": { "i1": {<person>}, ... },
      "unions": [ {"a": "i1", "b": "i2"}, ... ],
      "_n": <next id counter>
    }

A ``person`` carries the dual-layer fields Abusua expects: biological parentage
(``bioMotherId`` / ``bioFatherId``) and a ``paternity`` certainty flag, social
parentage (``socialMotherId`` / ``socialFatherId`` / ``fosteredIn``), lineage
overrides, and clinical attributes. We reconstruct as many of these as the
source GA4GH artefacts contain, and leave the rest at Abusua's own defaults.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# Abusua person defaults (mirror the tool's MODEL.add defaults)
_DEFAULTS: Dict[str, Any] = {
    "name": "",
    "sex": "U",
    "bioMotherId": None,
    "bioFatherId": None,
    "paternity": "confirmed",
    "socialMotherId": None,
    "socialFatherId": None,
    "fosteredIn": False,
    "abusuaManual": None,
    "ntoroManual": None,
    "affected": "unknown",
    "condition": "",
    "deceased": False,
    "proband": False,
    "notes": "",
}


@dataclass
class BuildPerson:
    """A person under construction, keyed by the final Abusua id (e.g. 'i3')."""

    id: str
    name: str = ""
    sex: str = "U"
    bioMotherId: Optional[str] = None
    bioFatherId: Optional[str] = None
    paternity: str = "confirmed"
    socialMotherId: Optional[str] = None
    socialFatherId: Optional[str] = None
    fosteredIn: bool = False
    abusuaManual: Optional[str] = None
    ntoroManual: Optional[str] = None
    affected: str = "unknown"
    condition: str = ""
    deceased: bool = False
    proband: bool = False
    notes: str = ""

    def to_json(self) -> Dict[str, Any]:
        rec = {"id": self.id}
        rec.update({k: getattr(self, k) for k in _DEFAULTS})
        return rec


class SessionBuilder:
    """Accumulates people and unions, then serialises an Abusua session dict."""

    def __init__(self, family_id: str = "FAM1") -> None:
        self.family_id = family_id
        self.people: Dict[str, BuildPerson] = {}
        self.unions: List[Dict[str, str]] = []
        self._n = 1
        # maps a source identifier (GA4GH subject.id or pedigree individualId)
        # to our Abusua id, so the two inputs can be merged consistently
        self.id_map: Dict[str, str] = {}

    # -- id handling -----------------------------------------------------

    def abusua_id_for(self, source_id: str) -> str:
        """Return (creating if needed) the Abusua id for a source identifier.

        If the source id already looks like an Abusua id ('i' + digits) we keep
        it verbatim so a round-trip from Abusua is identity-stable; otherwise we
        allocate a fresh i-id.
        """
        if source_id in self.id_map:
            return self.id_map[source_id]
        if isinstance(source_id, str) and source_id.startswith("i") and source_id[1:].isdigit():
            aid = source_id
            n = int(source_id[1:])
            if n >= self._n:
                self._n = n + 1
        else:
            aid = f"i{self._n}"
            self._n += 1
        self.id_map[source_id] = aid
        return aid

    def person(self, source_id: str) -> BuildPerson:
        aid = self.abusua_id_for(source_id)
        if aid not in self.people:
            self.people[aid] = BuildPerson(id=aid)
        return self.people[aid]

    # -- unions ----------------------------------------------------------

    def add_union(self, a_src: str, b_src: str) -> None:
        a, b = self.abusua_id_for(a_src), self.abusua_id_for(b_src)
        if a == b:
            return
        for u in self.unions:
            if {u["a"], u["b"]} == {a, b}:
                return
        self.unions.append({"a": a, "b": b})

    def infer_unions_from_parents(self) -> None:
        """Add a union for every pair of co-parents not already linked."""
        pairs = set()
        for p in self.people.values():
            if p.bioMotherId and p.bioFatherId:
                pairs.add((p.bioMotherId, p.bioFatherId))
        for mom, dad in pairs:
            self.add_union(mom, dad)

    # -- output ----------------------------------------------------------

    def to_session(self) -> Dict[str, Any]:
        return {
            "v": 1,
            "fam": self.family_id,
            "people": {pid: bp.to_json() for pid, bp in self.people.items()},
            "unions": list(self.unions),
            "_n": self._n,
        }
