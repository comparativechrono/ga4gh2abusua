"""
Reconstruct an Abusua Pedigree Studio session from GA4GH inputs:

* a **GA4GH Pedigree Standard** message (KIN-relationship graph), and/or
* a **Phenopackets v2 Family** (proband + relatives + native PED-style pedigree).

Either input alone yields a usable session; supplying both gives the most
complete reconstruction, and the two are merged by shared individual id.

Mapping back to Abusua's dual-layer model
-----------------------------------------
From the **GA4GH Pedigree** relationships:
  KIN:027 isBiologicalMotherOf  -> bioMotherId
  KIN:028 isBiologicalFatherOf  -> bioFatherId (paternity 'confirmed', or
                                    'reported' if the edge says so)
  KIN:022 isAdoptiveParentOf    -> socialMother/FatherId + fosteredIn = true

From the **Family.pedigree** (native PED rows):
  maternalId / paternalId       -> bioMotherId / bioFatherId ('0' => none)
  sex, affectedStatus           -> sex, affected
  (a paternalId of '0' on someone who has a mother is left as unknown paternity)

From the **phenopackets** (proband + relatives, or pedigree subjects):
  diseases[].term.label         -> condition (free text restored)
  phenotypicFeature HP:0032500  -> 'carrier' token appended to condition
  vital_status DECEASED         -> deceased = true
  subject.sex                   -> sex (if not already set)
  Family.proband                -> proband = true

Honest limitations
------------------
* Abusua-specific lineage attributes (abusua/ntoro manual overrides) are NOT
  present in the GA4GH artefacts, so they are left unset; the tool re-derives
  clan from the maternal chain on load. A round-trip therefore preserves
  topology and clinical data but not a founder's *manually pinned* clan unless
  it was also encoded elsewhere (it is not, by either standard).
* Condition ontology ids are dropped back to their free-text labels, matching
  how Abusua stores conditions.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .session import SessionBuilder


_SEX_BACK = {"MALE": "M", "FEMALE": "F", "UNKNOWN_SEX": "U", "OTHER_SEX": "U"}
_AFFECTED_BACK = {"AFFECTED": "affected", "UNAFFECTED": "unaffected", "MISSING": "unknown"}

# KIN term ids (string-compared so we don't depend on the forward package)
KIN_BIO_MOTHER = "KIN:027"
KIN_BIO_FATHER = "KIN:028"
KIN_ADOPTIVE = "KIN:022"

CARRIER_HP = "HP:0032500"


# ----------------------------------------------------------------- helpers

def _subject_of(individual_or_phenopacket: Dict[str, Any]) -> Dict[str, Any]:
    """Return the Individual fields for a pedigree member or phenopacket.

    Phenopackets and GA4GH-standard pedigrees nest an Individual under
    'subject'. Some tools instead put the fields (id, name, sex, affected,
    diseases, ...) directly on the individual object with no 'subject' wrapper.
    We support both: if a 'subject' is present and non-empty we use it,
    otherwise we treat the object itself as the subject.
    """
    subj = individual_or_phenopacket.get("subject")
    if isinstance(subj, dict) and subj:
        return subj
    return individual_or_phenopacket


def _name_from_subject(subj: Dict[str, Any]) -> str:
    """Recover a human name from a subject Individual.

    Phenopackets has no dedicated name field (it is designed to be
    de-identifiable), so a name, when present, may appear under ``name`` (how
    abusua2ga4gh writes it), as a ``label``, or as the first ``alternate_ids``
    entry. We check them in that order.
    """
    if subj.get("name"):
        return str(subj["name"])
    if subj.get("label"):
        return str(subj["label"])
    alt = subj.get("alternate_ids") or subj.get("alternateIds") or []
    return str(alt[0]) if alt else ""


def _conditions_from_phenopacket(pp: Dict[str, Any]) -> Tuple[List[str], bool]:
    """Return (condition_labels, is_carrier) from a phenopacket.

    Conditions are gathered from BOTH ``diseases`` and ``phenotypicFeatures``
    (excluding the special carrier feature), so a pedigree exported with
    conditions recorded as phenotypes is read back the same way as one that
    recorded them as diseases. An excluded disease/feature (an explicitly absent
    finding) is skipped.
    """
    labels: List[str] = []
    for d in pp.get("diseases", []):
        if d.get("excluded"):
            continue
        term = d.get("term", {}) or {}
        label = term.get("label") or term.get("id") or ""
        if label:
            labels.append(label)
    is_carrier = False
    for f in pp.get("phenotypicFeatures", []) or pp.get("phenotypic_features", []) or []:
        term = f.get("type", {}) or {}
        if term.get("id") == CARRIER_HP:
            is_carrier = True
            continue
        if f.get("excluded"):
            continue
        label = term.get("label") or term.get("id") or ""
        if label:
            labels.append(label)
    return labels, is_carrier


def _apply_phenopacket(builder: SessionBuilder, pp: Dict[str, Any], *, is_proband: bool) -> None:
    subj = _subject_of(pp)
    sid = subj.get("id")
    if not sid:
        return
    person = builder.person(sid)
    # name
    nm = _name_from_subject(subj)
    if nm and not person.name:
        person.name = nm
    # sex
    sex = _SEX_BACK.get(subj.get("sex", "UNKNOWN_SEX"), "U")
    if person.sex == "U":
        person.sex = sex
    # vital status
    vs = (subj.get("vital_status") or subj.get("vitalStatus") or {}).get("status")
    if vs == "DECEASED":
        person.deceased = True
    # conditions + carrier
    labels, is_carrier = _conditions_from_phenopacket(pp)
    tokens = [t for t in (person.condition.split(";") if person.condition else []) if t.strip()]
    for label in labels:
        if label not in tokens:
            tokens.append(label)
    if is_carrier and "carrier" not in [t.strip().lower() for t in tokens]:
        tokens.append("carrier")
    person.condition = ";".join(tokens)
    # affected: any non-excluded disease => affected (unless already set affected/unaffected)
    if labels and person.affected in ("unknown", ""):
        person.affected = "affected"
    if is_proband:
        person.proband = True


# ----------------------------------------------------------------- pedigree (GA4GH)

def apply_ga4gh_pedigree(builder: SessionBuilder, pedigree: Dict[str, Any]) -> List[str]:
    """Populate the builder from a GA4GH Pedigree Standard message."""
    warns: List[str] = []
    if not isinstance(pedigree, dict) or "individuals" not in pedigree:
        warns.append("ga4gh-pedigree: no 'individuals' field; skipped.")
        return warns

    if pedigree.get("id"):
        builder.family_id = pedigree["id"]

    # individuals carry the real identity in subject.id
    probands = set(pedigree.get("index_patients") or pedigree.get("indexPatients") or [])
    for ind in pedigree["individuals"]:
        subj = _subject_of(ind)
        sid = subj.get("id")
        if not sid:
            warns.append("ga4gh-pedigree: an individual has no subject.id; skipped.")
            continue
        person = builder.person(sid)
        nm = _name_from_subject(subj)
        if nm and not person.name:
            person.name = nm
        if person.sex == "U":
            person.sex = _SEX_BACK.get(subj.get("sex", "UNKNOWN_SEX"), "U")
        vs = (subj.get("vital_status") or subj.get("vitalStatus") or {}).get("status")
        if vs == "DECEASED":
            person.deceased = True
        # affected status may appear as an individual-level boolean/string in some
        # tools' output (subject has no diseases but flags affected directly)
        aff = subj.get("affected")
        if isinstance(aff, bool):
            if person.affected in ("unknown", ""):
                person.affected = "affected" if aff else "unaffected"
        elif isinstance(aff, str) and aff.lower() in ("affected", "unaffected"):
            if person.affected in ("unknown", ""):
                person.affected = aff.lower()
        # diseases optionally attached to the subject
        for d in subj.get("diseases", []) or []:
            term = d.get("term", {}) or {}
            label = term.get("label") or term.get("id") or ""
            if label:
                toks = [t for t in (person.condition.split(";") if person.condition else []) if t.strip()]
                if label not in toks:
                    toks.append(label)
                person.condition = ";".join(toks)
                if person.affected in ("unknown", ""):
                    person.affected = "affected"
        if sid in probands:
            person.proband = True

    # relationships -> parentage edges
    for rel in pedigree.get("relationships", []):
        relation = (rel.get("relation") or {}).get("id")
        subject_id = (rel.get("individual_id") or rel.get("individualId")
                      or rel.get("individual"))
        relative_id = (rel.get("relative_id") or rel.get("relativeId")
                       or rel.get("relative"))
        desc = (rel.get("description") or "").lower()
        if not relation or not subject_id or not relative_id:
            continue
        # relation reads "subject <relation> relative": e.g. mother isBiologicalMotherOf child
        parent_src, child_src = subject_id, relative_id
        child = builder.person(child_src)
        parent_aid = builder.abusua_id_for(parent_src)
        builder.person(parent_src)  # ensure exists
        if relation == KIN_BIO_MOTHER:
            child.bioMotherId = parent_aid
        elif relation == KIN_BIO_FATHER:
            child.bioFatherId = parent_aid
            child.paternity = "reported" if "report" in desc else "confirmed"
        elif relation == KIN_ADOPTIVE:
            # social/foster parent; route by the parent's known sex if available
            par = builder.people.get(parent_aid)
            child.fosteredIn = True
            if par and par.sex == "M":
                child.socialFatherId = parent_aid
            elif par and par.sex == "F":
                child.socialMotherId = parent_aid
            else:
                # unknown sex: prefer the empty social slot
                if not child.socialMotherId:
                    child.socialMotherId = parent_aid
                else:
                    child.socialFatherId = parent_aid
        else:
            warns.append(f"ga4gh-pedigree: unmapped relation '{relation}' (kept out of session).")
    return warns


# ----------------------------------------------------------------- family (Phenopackets)

def apply_family(builder: SessionBuilder, family: Dict[str, Any]) -> List[str]:
    """Populate the builder from a Phenopackets Family message."""
    warns: List[str] = []
    if not isinstance(family, dict):
        warns.append("family: not an object; skipped.")
        return warns
    if family.get("id"):
        builder.family_id = family["id"]

    # 1) native pedigree rows give topology + sex + affected status
    pedigree = family.get("pedigree") or {}
    persons = pedigree.get("persons", [])
    for row in persons:
        sid = row.get("individualId") or row.get("individual_id")
        if not sid:
            continue
        person = builder.person(sid)
        person.sex = _SEX_BACK.get(row.get("sex", "UNKNOWN_SEX"), person.sex or "U")
        person.affected = _AFFECTED_BACK.get(row.get("affectedStatus")
                                             or row.get("affected_status"), person.affected)
        mat = row.get("maternalId") or row.get("maternal_id") or "0"
        pat = row.get("paternalId") or row.get("paternal_id") or "0"
        if mat and mat != "0":
            person.bioMotherId = builder.abusua_id_for(mat)
            builder.person(mat)
        if pat and pat != "0":
            person.bioFatherId = builder.abusua_id_for(pat)
            builder.person(pat)
            # native pedigree carries no certainty; default to confirmed unless a
            # GA4GH relationship later refines it
            if person.paternity not in ("reported", "social-only", "unknown"):
                person.paternity = "confirmed"
        else:
            # father absent in PED: if a mother exists, mark paternity unknown
            if person.bioMotherId and not person.bioFatherId:
                person.paternity = "unknown"

    # 2) consanguinity note on the proband's parents (informational)
    consang = family.get("consanguinousParents")
    if consang is None:
        consang = family.get("consanguinous_parents")

    # 3) proband + relatives phenopackets give names/conditions/carrier/deceased
    proband = family.get("proband")
    if proband:
        _apply_phenopacket(builder, proband, is_proband=True)
        if consang:
            subj = _subject_of(proband)
            pid = subj.get("id")
            if pid:
                bp = builder.person(pid)
                note = "parents consanguineous (from Phenopackets Family)."
                bp.notes = (bp.notes + " " + note).strip() if bp.notes else note
    for rel in family.get("relatives", []) or []:
        _apply_phenopacket(builder, rel, is_proband=False)

    return warns


# ----------------------------------------------------------------- public API

def to_abusua_session(
    *,
    ga4gh_pedigree: Optional[Dict[str, Any]] = None,
    family: Optional[Dict[str, Any]] = None,
    family_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    """Reconstruct an Abusua session dict from GA4GH inputs.

    At least one of ``ga4gh_pedigree`` or ``family`` must be provided. Returns
    ``(session_dict, conversion_warnings)``.

    When both are provided, the Family is applied first (it gives topology, sex,
    affected status and clinical detail), then the GA4GH Pedigree is layered on
    to refine the biological/social edge distinction and paternity certainty.
    """
    if ga4gh_pedigree is None and family is None:
        raise ValueError("Provide at least one of ga4gh_pedigree or family.")

    builder = SessionBuilder(family_id=family_id or "FAM1")
    warns: List[str] = []

    if family is not None:
        warns += apply_family(builder, family)
    if ga4gh_pedigree is not None:
        warns += apply_ga4gh_pedigree(builder, ga4gh_pedigree)

    # ensure co-parents are linked as unions (Abusua infers partnerships, but we
    # add explicit ones so childless display and clustering behave)
    builder.infer_unions_from_parents()

    if family_id:
        builder.family_id = family_id

    # final integrity sweep: null out parent refs that point nowhere
    ids = set(builder.people)
    for p in builder.people.values():
        for attr in ("bioMotherId", "bioFatherId", "socialMotherId", "socialFatherId"):
            ref = getattr(p, attr)
            if ref and ref not in ids:
                warns.append(f"{p.id}: {attr} -> unknown id '{ref}' (cleared).")
                setattr(p, attr, None)

    return builder.to_session(), warns
