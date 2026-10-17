"""
Tests for ga4gh2abusua, including a round-trip from the original Abusua
example sessions through the forward GA4GH outputs and back.

The forward GA4GH artefacts are produced into /tmp/fwd by the test setup in the
project's build step; here we read whatever family/pedigree pairs are bundled in
examples/ plus any present in /tmp/fwd.

Run with:  pytest
"""
from __future__ import annotations

import json
import pathlib

import pytest

from ga4gh2abusua import to_abusua_session

HERE = pathlib.Path(__file__).resolve().parents[1]
EXAMPLES = HERE / "examples"
FWD = pathlib.Path("/tmp/fwd")

# discover family/pedigree pairs by stem
def _pairs():
    out = []
    for d in (EXAMPLES, FWD):
        if not d.exists():
            continue
        for fam in sorted(d.glob("*.family.json")):
            stem = fam.name[: -len(".family.json")]
            ped = d / f"{stem}.ga4gh-pedigree.json"
            out.append((stem, fam, ped if ped.exists() else None))
    # de-dup by stem, preferring a pair that has both files
    best = {}
    for stem, fam, ped in out:
        if stem not in best or (ped and not best[stem][1]):
            best[stem] = (fam, ped)
    return [(s, f, p) for s, (f, p) in best.items()]


PAIRS = _pairs()
IDS = [s for s, _, _ in PAIRS]


def _load(p):
    return json.loads(p.read_text()) if p else None


def test_pairs_present():
    assert PAIRS, "expected at least one family/pedigree pair to test"


@pytest.mark.parametrize("pair", PAIRS, ids=IDS)
def test_session_shape(pair):
    stem, fam, ped = pair
    session, warns = to_abusua_session(
        ga4gh_pedigree=_load(ped), family=_load(fam))
    assert session["v"] == 1
    assert session["fam"]
    assert session["people"]
    # every person record has the dual-layer fields
    for pid, rec in session["people"].items():
        for field in ("bioMotherId", "bioFatherId", "paternity",
                      "socialMotherId", "socialFatherId", "fosteredIn",
                      "affected", "condition", "sex"):
            assert field in rec
    # parent + union references all resolve
    ids = set(session["people"])
    for rec in session["people"].values():
        for k in ("bioMotherId", "bioFatherId", "socialMotherId", "socialFatherId"):
            assert rec[k] is None or rec[k] in ids
    for u in session["unions"]:
        assert u["a"] in ids and u["b"] in ids


@pytest.mark.parametrize("pair", PAIRS, ids=IDS)
def test_family_only_reconstructs(pair):
    stem, fam, ped = pair
    session, _ = to_abusua_session(family=_load(fam))
    assert session["people"]
    # at least one affected and exactly one proband (the example design)
    affected = [r for r in session["people"].values() if r["affected"] == "affected"]
    probands = [r for r in session["people"].values() if r["proband"]]
    assert affected
    assert len(probands) == 1


@pytest.mark.parametrize("pair", PAIRS, ids=IDS)
def test_pedigree_only_reconstructs(pair):
    stem, fam, ped = pair
    if not ped:
        pytest.skip("no pedigree file for this pair")
    session, _ = to_abusua_session(ga4gh_pedigree=_load(ped))
    assert session["people"]
    # bio mother edges should exist (the mogya line is always emitted forward)
    has_mother = any(r["bioMotherId"] for r in session["people"].values())
    assert has_mother


def test_unknown_paternity_restored_from_family():
    # the sickle example's fostered child has paternalId '0' in the native pedigree
    fam = _load(EXAMPLES / "example-sickle-cell.family.json")
    if not fam:
        pytest.skip("sickle family not bundled")
    session, _ = to_abusua_session(family=fam)
    # find someone with a mother but no father => paternity unknown
    found = [r for r in session["people"].values()
             if r["bioMotherId"] and not r["bioFatherId"]]
    assert found
    assert all(r["paternity"] == "unknown" for r in found)


def test_carrier_token_restored():
    fam = _load(EXAMPLES / "example-sickle-cell.family.json")
    if not fam:
        pytest.skip("sickle family not bundled")
    session, _ = to_abusua_session(family=fam)
    carriers = [r for r in session["people"].values()
                if "carrier" in r["condition"].lower()]
    assert carriers, "carrier phenotype should be restored as a 'carrier' token"


def test_both_inputs_merge_consistently():
    fam = _load(EXAMPLES / "example-sickle-cell.family.json")
    ped = _load(EXAMPLES / "example-sickle-cell.ga4gh-pedigree.json")
    if not (fam and ped):
        pytest.skip("sickle pair not bundled")
    session, warns = to_abusua_session(ga4gh_pedigree=ped, family=fam)
    ids = set(session["people"])
    # references still resolve after merging two sources
    for rec in session["people"].values():
        for k in ("bioMotherId", "bioFatherId"):
            assert rec[k] is None or rec[k] in ids


def test_requires_an_input():
    with pytest.raises(ValueError):
        to_abusua_session()


def test_roundtrip_preserves_core_facts():
    """Abusua -> forward GA4GH -> back to Abusua preserves topology & key fields."""
    orig_path = None
    for cand in (FWD, EXAMPLES):
        pass
    # use the bundled sickle pair, compare against the original session
    fam = _load(EXAMPLES / "example-sickle-cell.family.json")
    ped = _load(EXAMPLES / "example-sickle-cell.ga4gh-pedigree.json")
    if not (fam and ped):
        pytest.skip("sickle pair not bundled")
    # original abusua session is bundled alongside the forward package; locate it
    orig_candidates = list(FWD.glob("example-sickle-cell.json")) + \
        list((HERE.parent / "abusua2ga4gh" / "examples").glob("example-sickle-cell.json"))
    if not orig_candidates:
        pytest.skip("original session not available for comparison")
    orig = json.loads(orig_candidates[0].read_text())
    session, _ = to_abusua_session(ga4gh_pedigree=ped, family=fam)

    # same number of people
    assert len(session["people"]) == len(orig["people"])
    # affected set matches (by name, since ids are reconstructed-stable here)
    def affected_names(s):
        return {p.get("name", "") for p in s["people"].values()
                if p.get("affected") == "affected"}
    # names only survive if include_names was used; if absent, compare counts
    if any(p.get("name") for p in session["people"].values()):
        assert affected_names(session) == affected_names(orig)
    else:
        assert (sum(1 for p in session["people"].values() if p["affected"] == "affected")
                == sum(1 for p in orig["people"].values() if p.get("affected") == "affected"))


def test_names_recovered_from_pedigree_subjects():
    """Names present on GA4GH pedigree individuals must populate Abusua 'name'."""
    ped = _load(EXAMPLES / "example-sickle-cell.ga4gh-pedigree.json")
    if not ped:
        pytest.skip("sickle pedigree not bundled")
    # only meaningful if the bundled file was exported with names
    has_names = any(
        (ind.get("subject", {}).get("name")
         or ind.get("subject", {}).get("label")
         or ind.get("subject", {}).get("alternate_ids"))
        for ind in ped.get("individuals", [])
    )
    if not has_names:
        pytest.skip("bundled pedigree has no names (exported without --include-names)")
    session, _ = to_abusua_session(ga4gh_pedigree=ped)
    named = [p for p in session["people"].values() if p["name"]]
    # every individual carrying a label/alt-id should have a name in the session
    assert len(named) == len(ped["individuals"])


def test_name_field_used_for_name():
    # a subject with a 'name' field should use it as the name
    fam = {
        "id": "T",
        "proband": {"subject": {"id": "i1", "sex": "MALE", "name": "Bob"},
                    "metaData": {"phenopacketSchemaVersion": "2.0"}},
        "pedigree": {"persons": [
            {"familyId": "T", "individualId": "i1", "paternalId": "0",
             "maternalId": "0", "sex": "MALE", "affectedStatus": "AFFECTED"}]},
    }
    session, _ = to_abusua_session(family=fam)
    assert session["people"]["i1"]["name"] == "Bob"


def test_phenotype_conditions_read_back():
    """Conditions recorded as phenotypicFeatures must come back as Abusua conditions."""
    fam = {
        "id": "T",
        "proband": {"subject": {"id": "i1", "sex": "MALE", "name": "Bob"},
                    "phenotypicFeatures": [{"type": {"id": "", "label": "Seizures"}}],
                    "metaData": {"phenopacketSchemaVersion": "2.0"}},
        "pedigree": {"persons": [
            {"familyId": "T", "individualId": "i1", "paternalId": "0",
             "maternalId": "0", "sex": "MALE", "affectedStatus": "AFFECTED"}]},
    }
    session, _ = to_abusua_session(family=fam)
    assert session["people"]["i1"]["condition"] == "Seizures"
    assert session["people"]["i1"]["affected"] == "affected"


def test_phenotype_and_carrier_both_read():
    fam = {
        "id": "T",
        "proband": {"subject": {"id": "i1", "sex": "FEMALE"},
                    "phenotypicFeatures": [
                        {"type": {"id": "", "label": "Pallor"}},
                        {"type": {"id": "HP:0032500", "label": "Heterozygous carrier"}}],
                    "metaData": {"phenopacketSchemaVersion": "2.0"}},
        "pedigree": {"persons": [
            {"familyId": "T", "individualId": "i1", "paternalId": "0",
             "maternalId": "0", "sex": "FEMALE", "affectedStatus": "AFFECTED"}]},
    }
    session, _ = to_abusua_session(family=fam)
    cond = session["people"]["i1"]["condition"].lower()
    assert "pallor" in cond and "carrier" in cond


# --------------------------------- alternate GA4GH serialisations (other tools)

def test_flat_individual_schema_names_and_affected():
    """Individuals with fields directly on the object (no 'subject' wrapper),
    individual-level 'affected' booleans, and 'individual'/'relative' relationship
    keys must all be read (as produced by some other pedigree tools)."""
    ped = {
        "id": "FAM1",
        "individuals": [
            {"id": "bob", "sex": "MALE", "name": "bob", "affected": True},
            {"id": "person-7", "sex": "FEMALE", "name": "person-7"},
            {"id": "person-3", "sex": "MALE", "name": "person-3", "affected": True},
        ],
        "relationships": [
            {"individual": "person-7", "relation": {"id": "KIN:027",
             "label": "isBiologicalMotherOf"}, "relative": "bob"},
            {"individual": "person-3", "relation": {"id": "KIN:028",
             "label": "isBiologicalFatherOf"}, "relative": "bob"},
        ],
    }
    session, _ = to_abusua_session(ga4gh_pedigree=ped)
    by_name = {p["name"]: p for p in session["people"].values()}
    assert set(by_name) == {"bob", "person-7", "person-3"}
    assert by_name["bob"]["affected"] == "affected"
    # bob's parents resolved from individual/relative relationship keys
    bob = by_name["bob"]
    assert bob["bioMotherId"] == by_name["person-7"]["id"]
    assert bob["bioFatherId"] == by_name["person-3"]["id"]


def test_uploaded_test3_pair_full():
    """The user-supplied test3 pair: every individual named, topology intact."""
    fam_p = EXAMPLES / "test3_phenopackets.json"
    ped_p = EXAMPLES / "test3_ga4gh.json"
    if not (fam_p.exists() and ped_p.exists()):
        pytest.skip("test3 pair not bundled")
    session, _ = to_abusua_session(
        ga4gh_pedigree=json.loads(ped_p.read_text()),
        family=json.loads(fam_p.read_text()))
    assert len(session["people"]) == 16
    assert all(p["name"] for p in session["people"].values()), "every person should be named"
    bob = next(p for p in session["people"].values() if p["name"] == "bob")
    assert bob["affected"] == "affected"
    assert "sickle cell" in bob["condition"]
    assert bob["bioMotherId"] and bob["bioFatherId"]
