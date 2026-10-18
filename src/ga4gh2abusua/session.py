"""Building an Abusua Pedigree Studio session, and writing it as Abusua's ``.json``.

The session shape::

    {
      "v": 1,
      "fam": "FAMILY-ID",
      "people": { "i1": {<person>}, ... },
      "unions": [ {"a": "i1", "b": "i2"}, ... ],
      "_n": <the next id number>
    }

Each person carries Abusua's two layers: biological parentage
(``bioMotherId``, ``bioFatherId``) with a ``paternity`` flag saying how
certain the father is, and social parentage (``socialMotherId``,
``socialFatherId``, ``fosteredIn``), with the clinical fields beside them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

# Abusua's defaults for a new person (as the app's MODEL.add gives them)
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

_ABUSUA_ID = re.compile(r"^i([1-9][0-9]*)$")


@dataclass
class BuildPerson:
    """A person being built, under their Abusua id (``i3``)."""

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

    def add_condition(self, text: str) -> None:
        tokens = [t.strip() for t in self.condition.split(";") if t.strip()]
        if text and text.lower() not in [t.lower() for t in tokens]:
            tokens.append(text)
        self.condition = ";".join(tokens)

    def add_note(self, text: str) -> None:
        self.notes = (self.notes + " " + text).strip() if self.notes else text


class SessionBuilder:
    """Collects people and unions, then writes an Abusua session."""

    def __init__(self, family_id: str = "FAM1") -> None:
        self.family_id = family_id
        self.people: Dict[str, BuildPerson] = {}
        self.unions: List[Dict[str, str]] = []
        self._n = 1
        # the id each person has in the GA4GH file -> their Abusua id
        self.id_map: Dict[str, str] = {}

    # -- ids ------------------------------------------------------------------

    def reserve(self, source_ids: Iterable[str]) -> None:
        """Give every id in a file its Abusua id at once.

        Ids that already are Abusua ids (``i`` and a number, as abusua2ga4gh
        writes them) are kept, so a round trip gives people back their own ids;
        the others are numbered after the highest of those, so the two can never
        clash.
        """
        ids = [str(s) for s in source_ids if s]
        for sid in ids:
            m = _ABUSUA_ID.match(sid)
            if m and sid not in self.id_map and sid not in self.id_map.values():
                self.id_map[sid] = sid
                self._n = max(self._n, int(m.group(1)) + 1)
        for sid in ids:
            self.abusua_id_for(sid)

    def abusua_id_for(self, source_id: str) -> str:
        """The Abusua id for an id in the file, giving it the next free one if it has none yet."""
        source_id = str(source_id)
        if source_id in self.id_map:
            return self.id_map[source_id]
        m = _ABUSUA_ID.match(source_id)
        if m and source_id not in self.id_map.values():
            aid = source_id
            self._n = max(self._n, int(m.group(1)) + 1)
        else:
            taken = set(self.id_map.values())
            while "i{}".format(self._n) in taken:
                self._n += 1
            aid = "i{}".format(self._n)
            self._n += 1
        self.id_map[source_id] = aid
        return aid

    def person(self, source_id: str) -> BuildPerson:
        aid = self.abusua_id_for(source_id)
        if aid not in self.people:
            self.people[aid] = BuildPerson(id=aid)
        return self.people[aid]

    # -- unions ---------------------------------------------------------------

    def add_union(self, a_src: str, b_src: str) -> None:
        a, b = self.abusua_id_for(a_src), self.abusua_id_for(b_src)
        if a == b:
            return
        for u in self.unions:
            if {u["a"], u["b"]} == {a, b}:
                return
        self.unions.append({"a": a, "b": b})

    def infer_unions_from_parents(self) -> None:
        """Add a union for every couple who are a child's two biological parents and not yet a union."""
        for p in self.people.values():
            if p.bioMotherId and p.bioFatherId and p.paternity in ("confirmed", "reported"):
                self._add_union_ids(p.bioMotherId, p.bioFatherId)

    def _add_union_ids(self, a: str, b: str) -> None:
        if a != b and not any({u["a"], u["b"]} == {a, b} for u in self.unions):
            self.unions.append({"a": a, "b": b})

    # -- output ---------------------------------------------------------------

    def to_session(self) -> Dict[str, Any]:
        return {
            "v": 1,
            "fam": self.family_id,
            "people": {pid: bp.to_json() for pid, bp in self.people.items()},
            "unions": list(self.unions),
            "_n": self._n,
        }
