"""Rebuild an Abusua Pedigree Studio session from GA4GH files.

The file is read through pedigree-ga4gh, the one GA4GH implementation that
the lab's pedigree tools share, so ga4gh2abusua reads exactly the standard
form that abusua2ga4gh, studio2ga4gh and the phenopacket toolkit write: a
GA4GH Pedigree (Phenopackets form) or a Phenopackets v2 Family, in either
JSON spelling. The family is then put back into Abusua's two layers:

==================================================  =================================================
In the GA4GH files                                  In the Abusua session
==================================================  =================================================
isBiologicalMotherOf (KIN:027), isOvumDonorOf       ``bioMotherId``
isBiologicalFatherOf (KIN:028), isSpermDonorOf      ``bioFatherId``, paternity ``confirmed``, or
                                                    ``reported`` if the narrative says so
isBiologicalParentOf (KIN:003)                      mother or father, by the parent's sex
isParentFigureOf (KIN:020) from a social father     ``bioFatherId``, paternity ``social-only``, when
                                                    the narrative says he is the social father
isFosterParentOf (KIN:021), isAdoptiveParentOf      ``socialMotherId`` / ``socialFatherId``, and
(KIN:022)                                           ``fosteredIn``
other parent figures and step-parents               ``socialMotherId`` / ``socialFatherId``
partners of every kind                              a union (and every couple with a child together)
``indexPatients``, the Family's proband             ``proband``
vital status DECEASED                               ``deceased``
diseases and phenotypic features                    ``condition``, each written ``label [CURIE]`` so
                                                    that abusua2ga4gh gives it the same term again
an excluded condition                               the condition, on a person marked unaffected
the narrative's notes                               carriers, conditions without a term, who is
                                                    affected or unaffected, a father whose paternity
                                                    is unknown, and fostering
the Family's PED-style pedigree                     parents, sex, and affected or unaffected
==================================================  =================================================

The narrative's notes are the sentences abusua2ga4gh 0.3 writes, and those
``pedigree-ga4gh upgrade`` writes for a file from abusua2ga4gh 0.2, so a
session survives the round trip. Names cannot: Phenopackets have no field for
a name, so the GA4GH files have none to give back.

Files in the older, non-standard forms (studio2ga4gh up to 0.3 and
abusua2ga4gh up to 0.2) are refused with a message saying to upgrade them
first, once, with ``pedigree-ga4gh upgrade``.
"""
from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional, Tuple

from pedigree_ga4gh import Kindred, detect, from_document, identify_legacy, kin

from .session import SessionBuilder

_SEX_BACK = {"MALE": "M", "FEMALE": "F"}


class LegacyFileError(ValueError):
    """The file is in an older, non-standard form and must be upgraded first."""


# -- the narrative ---------------------------------------------------------------------------------------------

_ID = r"(?<!\S)(?P<{}>\S+?)"
_LIST = r"(?P<{}>[^.:;]+?)"
_TEXT = r"(?P<{}>(?:(?!\. ).)+?)"


def _p(pattern: str, **parts: str) -> "re.Pattern":
    return re.compile(pattern.format(**{name: kind.format(name) for name, kind in parts.items()}))


NOTES = {
    "reported": _p(r"{child}'s biological father, {father}, is reported, not confirmed\.", child=_ID, father=_ID),
    "social_father": _p(r"{father} is the social father of {child}, not the biological father\.",
                        father=_ID, child=_ID),
    "unknown_father": _p(r"{child}'s father is recorded as {father}, but it is not known whether he is the "
                         r"biological father\.", child=_ID, father=_ID),
    "fostered": _p(r"{child} was fostered in(?: by {by})?\.", child=_ID, by=_LIST),
    "social_parent": _p(r"{parent} is the social (?P<role>mother|father) of {child}\.(?!\S)", parent=_ID,
                        child=_ID),
    "carrier": _p(r"{person} is a carrier\.", person=_ID),
    "carriers": _p(r"{people} are each a carrier\.", people=_LIST),
    "unmatched": _p(r"{person} has {condition}, which has no ontology term yet\.", person=_ID, condition=_TEXT),
    "unmatched_excluded": _p(r"{person} is unaffected by {condition}, which has no ontology term yet\.",
                             person=_ID, condition=_TEXT),
    "affected": _p(r"{person} is affected, but no condition is recorded\.", person=_ID),
    "unaffected": _p(r"Recorded as unaffected: {people}\.", people=_LIST),
    # what pedigree-ga4gh upgrade keeps of an abusua2ga4gh 0.2 relationship's description
    "legacy": _p(r"{a} and {b}: (?P<desc>paternity reported, not confirmed|social/levirate father "
                 r"\(non-biological\)|social/foster parent \(child fostered in\))\.", a=_ID, b=_ID),
}


def _split_list(text: str) -> List[str]:
    return [x.strip() for x in re.split(r",\s*|\s+and\s+", text or "") if x.strip()]


def read_notes(narrative: Optional[str]) -> Dict[str, Any]:
    """What the narrative's notes say, keyed by the GA4GH ids they name."""
    text = narrative or ""
    out: Dict[str, Any] = {"reported": set(), "social_father": set(), "unknown_father": {}, "fostered": {},
                           "social_parent": [], "carrier": [], "unmatched": [], "affected": [], "unaffected": []}
    for m in NOTES["reported"].finditer(text):
        out["reported"].add((m["child"], m["father"]))
    for m in NOTES["social_father"].finditer(text):
        out["social_father"].add((m["father"], m["child"]))
    for m in NOTES["unknown_father"].finditer(text):
        out["unknown_father"].setdefault(m["child"], m["father"])
    for m in NOTES["fostered"].finditer(text):
        out["fostered"].setdefault(m["child"], _split_list(m["by"]) if m["by"] else [])
    for m in NOTES["social_parent"].finditer(text):
        out["social_parent"].append((m["parent"], m["role"], m["child"]))
    for m in NOTES["carrier"].finditer(text):
        out["carrier"].append(m["person"])
    for m in NOTES["carriers"].finditer(text):
        out["carrier"].extend(_split_list(m["people"]))
    for m in NOTES["unmatched"].finditer(text):
        out["unmatched"].append((m["person"], m["condition"], False))
    for m in NOTES["unmatched_excluded"].finditer(text):
        out["unmatched"].append((m["person"], m["condition"], True))
    for m in NOTES["affected"].finditer(text):
        out["affected"].append(m["person"])
    for m in NOTES["unaffected"].finditer(text):
        out["unaffected"].extend(_split_list(m["people"]))
    for m in NOTES["legacy"].finditer(text):
        a, b, desc = m["a"], m["b"], m["desc"]
        if desc.startswith("paternity"):
            out["reported"].add((b, a))
        elif desc.startswith("social/levirate"):
            out["social_father"].add((a, b))
        else:
            out["fostered"].setdefault(b, [])
    return out


# -- a Kindred into a session ----------------------------------------------------------------------------------

def _term_token(t) -> str:
    """A condition as the session records it: its label, then its ontology id in brackets."""
    if t.matched:
        return "{} [{}]".format(t.label or t.id, t.id)
    return t.label or t.id


def _slot(child, parent_id: str, sex: str) -> None:
    """Put a social parent in the social mother's or father's place, by their sex."""
    if sex == "F" and not child.socialMotherId:
        child.socialMotherId = parent_id
    elif sex == "M" and not child.socialFatherId:
        child.socialFatherId = parent_id
    elif sex not in ("M", "F"):
        if not child.socialMotherId:
            child.socialMotherId = parent_id
        elif not child.socialFatherId:
            child.socialFatherId = parent_id


_FOSTER = {kin.FOSTER_PARENT, kin.ADOPTIVE_PARENT}
_PARTNERS = {kin.PARTNER, kin.CONSANGUINEOUS_PARTNER, kin.SEPARATED_PARTNER, kin.SEPARATED_CONSANGUINEOUS_PARTNER}
_NOT_KEPT = {kin.GESTATIONAL_CARRIER: "a gestational carrier", kin.HAS_GESTATIONAL_CARRIER: "a gestational carrier",
             kin.MITOCHONDRIAL_DONOR: "a mitochondrial donor"}


def apply_kindred(builder: SessionBuilder, k: Kindred, *, fill_only: bool = False) -> List[str]:
    """Put a Kindred into the session being built. Returns notes about the conversion.

    With ``fill_only``, only what the session does not have yet is filled in,
    so that a Family can add the affected status a GA4GH Pedigree may lack.
    """
    warnings: List[str] = []
    if not fill_only:
        builder.family_id = k.id or builder.family_id
    builder.reserve(m.id for m in k.members)
    known = {m.id for m in k.members}
    hints = read_notes(k.narrative)
    sex_of = {m.id: _SEX_BACK.get(m.sex, "U") for m in k.members}
    aid = builder.abusua_id_for

    for m in k.members:
        new = aid(m.id) not in builder.people
        p = builder.person(m.id)
        if fill_only and not new:
            if p.sex == "U":
                p.sex = sex_of[m.id]
            if p.affected == "unknown" and m.affected is not None:
                p.affected = "affected" if m.affected else "unaffected"
            continue
        if fill_only:
            warnings.append("{} is in the Family but not in the GA4GH Pedigree".format(m.id))
        p.sex = sex_of[m.id]
        p.deceased = m.vital_status == "DECEASED"
        p.proband = p.proband or m.index
        if aid(m.id) != m.id:
            p.add_note("GA4GH id: {}".format(m.id))
        included = [_term_token(t) for t in m.terms if not t.excluded]
        excluded = [_term_token(t) for t in m.terms if t.excluded]
        for token in included or excluded:
            p.add_condition(token)
        if included and excluded:
            warnings.append("{}: Abusua cannot record that someone does not have a condition beside conditions "
                            "they have, so {} {} left out".format(m.id, ", ".join(excluded),
                                                                 "was" if len(excluded) == 1 else "were"))
        if m.affected is True or included:
            p.affected = "affected"
        elif m.affected is False or excluded:
            p.affected = "unaffected"

    # biological parents: pedigree-ga4gh places donors, parents of unknown sex and the parents of twins
    social_fathers = {(f, c) for f, c in hints["social_father"] if f in known and c in known}
    for m in k.members:
        child = builder.person(m.id)
        if fill_only and (child.bioMotherId or child.bioFatherId):
            continue
        father, mother, notes = k.genetic_parents(m.id)
        warnings.extend(notes)
        for r in k.relations_to(m.id):
            if r.kin in (kin.SPERM_DONOR, kin.OVUM_DONOR, kin.SURROGATE_OVUM_DONOR):
                warnings.append("{}: {} is {}, recorded as the biological {} (Abusua has no field for a "
                                "donor)".format(m.id, r.individual, kin.TERMS[r.kin].label,
                                                "father" if r.kin == kin.SPERM_DONOR else "mother"))
            elif r.kin in _NOT_KEPT:
                warnings.append("{}: {} is {}, which Abusua has no field for".format(
                    m.id, r.individual, _NOT_KEPT[r.kin]))
        if mother:
            child.bioMotherId = aid(mother)
        if father:
            child.bioFatherId = aid(father)
            child.paternity = "reported" if (m.id, father) in hints["reported"] else "confirmed"
        else:
            social = [f for f, c in social_fathers if c == m.id]
            recorded = hints["unknown_father"].get(m.id)
            if social:
                child.bioFatherId, child.paternity = aid(social[0]), "social-only"
            elif recorded in known:
                child.bioFatherId, child.paternity = aid(recorded), "unknown"
            elif mother:
                child.paternity = "unknown"

    # social parents, partners, and the relationships Abusua has no place for
    for r in k.relations:
        a, b = r.individual, r.relative
        if a not in known or b not in known:
            continue
        child = builder.person(b)
        if r.kin in _FOSTER:
            if (a, b) in social_fathers:
                continue                      # 0.2 wrote a social father as an adoptive parent
            if not (fill_only and (child.socialMotherId or child.socialFatherId)):
                _slot(child, aid(a), sex_of.get(a, "U"))
                child.fosteredIn = True
            if r.kin == kin.ADOPTIVE_PARENT:
                warnings.append("{}: {} is an adoptive parent, recorded as the social parent of a child fostered "
                                "in (Abusua has no field for adoption)".format(b, a))
        elif r.kin in (kin.PARENT_FIGURE, kin.STEP_PARENT):
            if (a, b) in social_fathers:
                continue
            _slot(child, aid(a), sex_of.get(a, "U"))
            if r.kin == kin.STEP_PARENT:
                warnings.append("{}: {} is a step-parent, recorded as a social parent".format(b, a))
        elif r.kin in _PARTNERS:
            builder.add_union(a, b)
        elif kin.is_a(r.kin, kin.BIOLOGICAL_PARENT) or r.kin in _NOT_KEPT:
            continue                          # done above
        elif kin.is_a(r.kin, "KIN:007"):
            continue                          # siblings and twins: they share parents, which are recorded
        elif not fill_only:
            warnings.append("{} {} {}: Abusua has no field for this relationship, so it is not kept".format(
                a, kin.TERMS[r.kin].label if r.kin in kin.TERMS else r.kin, b))

    # what the narrative says that the structure cannot
    for child_id, by in hints["fostered"].items():
        if child_id in known:
            child = builder.person(child_id)
            child.fosteredIn = True
            for parent in by:
                if parent in known and aid(parent) not in (child.socialMotherId, child.socialFatherId):
                    _slot(child, aid(parent), sex_of.get(parent, "U"))
    for parent, role, child_id in hints["social_parent"]:
        if parent in known and child_id in known:
            _slot(builder.person(child_id), aid(parent), "F" if role == "mother" else "M")
    for person in hints["carrier"]:
        if person in known:
            builder.person(person).add_condition("carrier")
    for person, condition, excluded in hints["unmatched"]:
        if person in known:
            p = builder.person(person)
            p.add_condition(condition)
            if p.affected == "unknown":
                p.affected = "unaffected" if excluded else "affected"
    for person in hints["affected"]:
        if person in known:
            builder.person(person).affected = "affected"
    for person in hints["unaffected"]:
        if person in known and builder.person(person).affected == "unknown":
            builder.person(person).affected = "unaffected"
    return warnings


# -- reading files ---------------------------------------------------------------------------------------------

def check_form(doc: Dict[str, Any], what: str = "file") -> None:
    """Raise :class:`LegacyFileError` for a file in an older, non-standard form."""
    old = identify_legacy(doc)
    if old is None:
        return
    if not old.upgradable:
        raise LegacyFileError(old.description)
    raise LegacyFileError("{} Upgrade it first, once: pedigree-ga4gh upgrade FILE -o NEW.json".format(
        old.description))


def _kindred(doc: Dict[str, Any], expect: Optional[str], warnings: List[str]) -> Kindred:
    if not isinstance(doc, dict):
        raise ValueError("the file must hold a JSON object")
    check_form(doc)
    kind = detect(doc)
    if expect and kind != expect:
        warnings.append("the file given as a {} is a {}; it was read as one".format(
            {"pedigree": "GA4GH Pedigree", "family": "Phenopackets Family"}[expect],
            {"pedigree": "GA4GH Pedigree", "family": "Phenopackets Family", "cohort": "Phenopackets Cohort",
             "phenopacket": "Phenopacket"}.get(kind, "file of unknown kind")))
    k, w = from_document(copy.deepcopy(doc))
    warnings.extend(w)
    return k


def apply_ga4gh_pedigree(builder: SessionBuilder, pedigree: Dict[str, Any]) -> List[str]:
    """Put a GA4GH Pedigree into the session being built."""
    warnings: List[str] = []
    k = _kindred(pedigree, "pedigree", warnings)
    return warnings + apply_kindred(builder, k)


def apply_family(builder: SessionBuilder, family: Dict[str, Any], *, fill_only: bool = False) -> List[str]:
    """Put a Phenopackets Family into the session being built."""
    warnings: List[str] = []
    k = _kindred(family, "family", warnings)
    return warnings + apply_kindred(builder, k, fill_only=fill_only)


def to_abusua_session(
    *,
    ga4gh_pedigree: Optional[Dict[str, Any]] = None,
    family: Optional[Dict[str, Any]] = None,
    family_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    """Rebuild an Abusua session from a GA4GH Pedigree, a Phenopackets Family, or both.

    Returns ``(session, notes)``. With both, the GA4GH Pedigree is read first,
    as it holds more (social and foster parents, and the narrative's notes),
    and the Family then fills in what it lacks, such as who is unaffected.
    Raises :class:`LegacyFileError` for a file in an older form, which must be
    upgraded first with ``pedigree-ga4gh upgrade``.
    """
    if ga4gh_pedigree is None and family is None:
        raise ValueError("Provide at least one of ga4gh_pedigree or family.")
    builder = SessionBuilder(family_id=family_id or "FAM1")
    warnings: List[str] = []
    if ga4gh_pedigree is not None:
        warnings += apply_ga4gh_pedigree(builder, ga4gh_pedigree)
    if family is not None:
        warnings += apply_family(builder, family, fill_only=ga4gh_pedigree is not None)
    builder.infer_unions_from_parents()
    if family_id:
        builder.family_id = family_id
    ids = set(builder.people)
    for p in builder.people.values():
        for attr in ("bioMotherId", "bioFatherId", "socialMotherId", "socialFatherId"):
            ref = getattr(p, attr)
            if ref and ref not in ids:
                warnings.append("{}: {} -> unknown id '{}' (cleared).".format(p.id, attr, ref))
                setattr(p, attr, None)
    return builder.to_session(), list(dict.fromkeys(warnings))


def to_session(doc: Dict[str, Any], family_id: Optional[str] = None) -> Tuple[Dict[str, Any], List[str]]:
    """Rebuild a session from one file, whichever of the two it is."""
    if not isinstance(doc, dict):
        raise ValueError("the file must hold a JSON object")
    check_form(doc)
    kind = detect(doc)
    if kind == "family":
        return to_abusua_session(family=doc, family_id=family_id)
    if kind == "pedigree":
        return to_abusua_session(ga4gh_pedigree=doc, family_id=family_id)
    raise ValueError("this is not a GA4GH Pedigree or a Phenopackets Family")


__all__ = ["LegacyFileError", "NOTES", "apply_family", "apply_ga4gh_pedigree", "apply_kindred", "check_form",
           "read_notes", "to_abusua_session", "to_session"]
