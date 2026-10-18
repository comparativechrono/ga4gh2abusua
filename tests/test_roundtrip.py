"""Tests for ga4gh2abusua: GA4GH files rebuilt as the Abusua sessions they came from.

tests/data/sessions holds fictional Abusua sessions (the same as abusua2ga4gh's tests use); the GA4GH files beside
them were written from those sessions by abusua2ga4gh 0.3.0. tests/data/legacy holds files in the older forms,
and one from abusua2ga4gh 0.2 after `pedigree-ga4gh upgrade`; tests/data/other holds a GA4GH Pedigree written by
studio2ga4gh 0.4.0 from a Pedigree Studio drawing.
"""
from __future__ import annotations

import contextlib
import io
import json
import pathlib

import pytest

from ga4gh2abusua import LegacyFileError, SessionBuilder, read_notes, to_abusua_session, to_session
from ga4gh2abusua.cli import main

DATA = pathlib.Path(__file__).resolve().parent / "data"
NAMES = ["asante", "boateng", "owusu", "mensah", "adjei"]
FIELDS = ["sex", "bioMotherId", "bioFatherId", "paternity", "socialMotherId", "socialFatherId", "fosteredIn",
          "affected", "deceased", "proband"]


def load(path):
    return json.loads((DATA / path).read_text(encoding="utf-8"))


def facts(rec):
    """What a session records about a person that the GA4GH files can carry."""
    out = {f: rec.get(f) for f in FIELDS}
    out["sex"] = out["sex"] or "U"
    out["paternity"] = out["paternity"] or "confirmed"
    out["affected"] = out["affected"] or "unknown"
    for f in ("fosteredIn", "deceased", "proband"):
        out[f] = bool(out[f])
    if out["bioMotherId"] and not out["bioFatherId"] and out["paternity"] == "confirmed":
        out["paternity"] = "unknown"         # a mother and no father: the father is not known
    out["carrier"] = "carrier" in (rec.get("condition") or "").lower()
    out["conditions"] = len([c for c in (rec.get("condition") or "").split(";")
                             if c.strip() and c.strip().lower() != "carrier"])
    return out


def unions(session):
    return {frozenset((u["a"], u["b"])) for u in session["unions"]}


# -- abusua2ga4gh's files come back as the sessions they were made from ---------------------------------------

@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("inputs", ["pedigree", "both"])
def test_every_session_comes_back(name, inputs):
    original = load("sessions/{}.json".format(name))
    pedigree = load("{}.ga4gh-pedigree.json".format(name))
    family = load("{}.family.json".format(name)) if inputs == "both" else None
    session, _ = to_abusua_session(ga4gh_pedigree=pedigree, family=family)
    assert session["fam"] == original["fam"] and list(session["people"]) == list(original["people"])
    for pid, rec in original["people"].items():
        assert facts(session["people"][pid]) == facts(rec), pid
    assert unions(session) == unions(original)
    assert session["_n"] == len(original["people"]) + 1


def test_conditions_keep_their_terms():
    session, _ = to_abusua_session(ga4gh_pedigree=load("asante.ga4gh-pedigree.json"))
    people = session["people"]
    assert people["i3"]["condition"] == "sickle cell disease [MONDO:0011382]"
    assert people["i5"]["condition"] == "Night blindness"        # no term: from the narrative
    assert people["i2"]["condition"] == "carrier"


def test_a_family_alone():
    """A Family has the PED-style pedigree, and Phenopackets only for those with findings, so less comes back:
    no social or foster parents, no carriers, and vital status only for people with a Phenopacket."""
    original = load("sessions/asante.json")
    session, _ = to_abusua_session(family=load("asante.family.json"))
    people = session["people"]
    assert len(people) == len(original["people"])
    assert people["i3"]["bioMotherId"] == "i2" and people["i3"]["bioFatherId"] == "i1"
    assert people["i5"]["bioFatherId"] is None and people["i5"]["paternity"] == "unknown"
    assert people["i4"]["affected"] == "unaffected" and people["i3"]["proband"] is True
    assert not people["i6"]["fosteredIn"]


def test_round_trip_is_stable():
    """GA4GH -> session -> GA4GH gives the same files again (needs abusua2ga4gh 0.3)."""
    abusua2ga4gh = pytest.importorskip("abusua2ga4gh")
    if tuple(int(x) for x in abusua2ga4gh.__version__.split(".")[:2]) < (0, 3):
        pytest.skip("needs abusua2ga4gh 0.3 or later")
    for name in NAMES:
        p1, f1 = load("{}.ga4gh-pedigree.json".format(name)), load("{}.family.json".format(name))
        session, _ = to_abusua_session(ga4gh_pedigree=p1, family=f1)
        ped = abusua2ga4gh.Pedigree.from_dict(session)
        p2, _ = abusua2ga4gh.to_ga4gh_pedigree(ped, created="2026-10-17T12:00:00Z", date="2026-10-17")
        f2, _ = abusua2ga4gh.to_family(ped, created="2026-10-17T12:00:00Z")
        assert p2 == p1, name
        assert f2 == f1, name


# -- the narrative ---------------------------------------------------------------------------------------------

def test_the_narrative_is_read():
    notes = read_notes(
        "Seen at the clinic. Pedigree from Abusua Pedigree Studio: 6 people; proband i3. Conditions: x. "
        "i3's biological father, i1, is reported, not confirmed. i1 is the social father of i5, not the "
        "biological father. i8's father is recorded as i9, but it is not known whether he is the biological "
        "father. i6 was fostered in. i2 is the social mother of i6. i7 is the social father of i6. "
        "i9 is the social mother of i4. i2 is a carrier. i5 has \"Night blindness\", which has no ontology "
        "term yet. i4 is unaffected by \"Long QT syndrome (type 1). Or so\", which has no ontology term yet. "
        "i5 has \"An \\\"odd\\\" one\", which has no ontology term yet. i13 is affected, but no condition "
        "is recorded. Recorded as unaffected: i14, i15 and i16.")
    assert notes["reported"] == {("i3", "i1")}
    assert notes["social_father"] == {("i1", "i5")}
    assert notes["unknown_father"] == {"i8": "i9"}
    assert notes["fostered"] == {"i6"}
    assert notes["social_parent"] == [("i2", "mother", "i6"), ("i7", "father", "i6"), ("i9", "mother", "i4")]
    assert notes["carrier"] == ["i2"]
    assert notes["unmatched"] == [("i5", "Night blindness", False), ("i5", 'An "odd" one', False),
                                  ("i4", "Long QT syndrome (type 1). Or so", True)]
    assert notes["affected"] == ["i13"] and notes["unaffected"] == ["i14", "i15", "i16"]


def test_a_persons_own_narrative_is_not_read_as_notes():
    """Text before abusua2ga4gh's own part of the narrative, as --narrative gives it, is never a note; and a
    note must start a sentence."""
    notes = read_notes(
        "The mother of i3 is a carrier. It is not known whether i4 is a carrier. We are not sure i6 was "
        "fostered in. Neither i2 nor i7 is affected, but no condition is recorded. i2 has \"asthma\", which has "
        "no ontology term yet. i9 was fostered in. Pedigree from Abusua Pedigree Studio: 9 people.")
    assert notes["carrier"] == [] and notes["fostered"] == set() and notes["affected"] == []
    assert notes["unmatched"] == []
    session, _ = to_abusua_session(ga4gh_pedigree=load("asante.ga4gh-pedigree.json"))
    assert session["people"]["i3"]["condition"] == "sickle cell disease [MONDO:0011382]"


def test_an_upgraded_file_from_abusua2ga4gh_0_2():
    """pedigree-ga4gh upgrade keeps 0.2's relationship descriptions in the narrative; they are read too."""
    session, notes = to_abusua_session(ga4gh_pedigree=load("legacy/abusua2ga4gh-0.2_ga4gh.upgraded.json"))
    people = session["people"]
    assert people["i3"]["paternity"] == "reported" and people["i3"]["bioFatherId"] == "i1"
    assert people["i5"]["bioFatherId"] == "i1" and people["i5"]["paternity"] == "social-only"
    assert people["i5"]["socialFatherId"] is None and not people["i5"]["fosteredIn"]
    assert people["i6"]["socialMotherId"] == "i2" and people["i6"]["fosteredIn"]
    assert people["i3"]["condition"] == "Sickle cell anaemia (HbSS)"     # the upgrade keeps an empty id
    assert all(p["name"] == "" for p in people.values())                  # and removes names


# -- other files -----------------------------------------------------------------------------------------------

def test_random_sessions_survive_the_round_trip():
    """Random sessions, odd ones included (social parents of unknown sex, the same person as both social
    parents, related couples, conditions with full stops and quotation marks, free text in brackets):
    converting the session that comes back gives the same GA4GH files again, from the GA4GH Pedigree with
    the Family, from the Pedigree alone, and from the Family alone. Needs abusua2ga4gh 0.3."""
    import random
    abusua2ga4gh = pytest.importorskip("abusua2ga4gh")
    if tuple(int(x) for x in abusua2ga4gh.__version__.split(".")[:2]) < (0, 3):
        pytest.skip("needs abusua2ga4gh 0.3 or later")
    conditions = ["Sickle cell anaemia (HbSS)", "Huntington disease", "Breast cancer", "Night blindness",
                  "Hypertension (dx. 2019)", 'An "odd" one', "Asthma [HP:0002099]", "Pain (BP:160/95)", "carrier"]

    def make(rng):
        people = {}
        for i in range(1, rng.randint(3, 12) + 1):
            pid, rec = "i%d" % i, {"sex": rng.choice("MFFMU")}
            earlier = list(people)
            if earlier and rng.random() < 0.75:
                moms = [q for q in earlier if people[q]["sex"] == "F"]
                dads = [q for q in earlier if people[q]["sex"] == "M"]
                if moms and rng.random() < 0.9:
                    rec["bioMotherId"] = rng.choice(moms)
                if dads and rng.random() < 0.8:
                    rec["bioFatherId"] = rng.choice(dads)
                    rec["paternity"] = rng.choice(["confirmed", "confirmed", "reported", "social-only", "unknown"])
            if earlier and rng.random() < 0.2:
                rec["fosteredIn"] = True
            if earlier and rng.random() < 0.35:
                others = [q for q in earlier if q not in (rec.get("bioMotherId"), rec.get("bioFatherId"))]
                for slot in rng.sample(["socialMotherId", "socialFatherId"], rng.choice([1, 1, 2])) if others else []:
                    rec[slot] = rng.choice(others)
            rec["affected"] = rng.choice(["affected", "unaffected", "unknown"])
            if rng.random() < 0.6:
                rec["condition"] = ";".join(rng.sample(conditions, rng.choice([1, 1, 2])))
            rec["deceased"] = rng.random() < 0.2
            people[pid] = rec
        rng.choice(list(people.values()))["proband"] = True
        unions = {tuple(sorted((r["bioMotherId"], r["bioFatherId"]))) for r in people.values()
                  if r.get("bioMotherId") and r.get("bioFatherId") and rng.random() < 0.7}
        if rng.random() < 0.5:
            unions.add(tuple(sorted(rng.sample(list(people), 2))))
        return {"v": 1, "fam": "R", "people": people, "unions": [{"a": a, "b": b} for a, b in sorted(unions)]}

    def convert(session):
        ped = abusua2ga4gh.Pedigree.from_dict(session)
        p, _ = abusua2ga4gh.to_ga4gh_pedigree(ped, date="2026-10-17", created="2026-10-17T12:00:00Z",
                                              narrative="The mother of i3 is a carrier")
        f, _ = abusua2ga4gh.to_family(ped, created="2026-10-17T12:00:00Z")
        return p, f

    for seed in range(150):
        p1, f1 = convert(make(random.Random(seed)))
        assert convert(to_abusua_session(ga4gh_pedigree=p1, family=f1 or None)[0]) == (p1, f1), seed
        assert convert(to_abusua_session(ga4gh_pedigree=p1)[0])[0] == p1, seed
        if f1:
            assert convert(to_abusua_session(family=f1)[0])[1] == f1, seed


def test_social_parents_keep_their_roles():
    """The narrative says which social parent is the mother and which the father, so their places survive even
    when their sex is not recorded."""
    abusua2ga4gh = pytest.importorskip("abusua2ga4gh")
    session = {"fam": "T", "people": {"i1": {"sex": "U"}, "i2": {"sex": "U"},
                                      "i3": {"sex": "F", "proband": True, "fosteredIn": True,
                                             "socialMotherId": "i2", "socialFatherId": "i1"}}}
    pedigree, _ = abusua2ga4gh.to_ga4gh_pedigree(abusua2ga4gh.Pedigree.from_dict(session))
    back = to_abusua_session(ga4gh_pedigree=pedigree)[0]["people"]["i3"]
    assert (back["socialMotherId"], back["socialFatherId"], back["fosteredIn"]) == ("i2", "i1", True)


def test_a_pedigree_from_studio2ga4gh():
    session, notes = to_abusua_session(ga4gh_pedigree=load("other/okafor_ga4gh-pedigree.json"))
    people = session["people"]
    assert len(people) == 16 and set(people) == {"i{}".format(n) for n in range(1, 17)}
    by_id = {p["notes"].replace("GA4GH id: ", ""): p for p in people.values()}
    proband = by_id["IV-3"]
    assert proband["proband"] and "[HP:0000365]" in proband["condition"]
    mother, father = people[proband["bioMotherId"]], people[proband["bioFatherId"]]
    assert mother["notes"] == "GA4GH id: III-3" and mother["sex"] == "F"
    assert father["notes"] == "GA4GH id: III-2" and proband["paternity"] == "confirmed"
    twin = by_id["IV-4"]                                   # identical twins: Abusua records their parents
    assert (twin["bioMotherId"], twin["bioFatherId"]) == (proband["bioMotherId"], proband["bioFatherId"])
    assert {"a": father["id"], "b": mother["id"]} in session["unions"]    # the consanguineous couple
    assert any("[MONDO:0007254]" in p["condition"] for p in people.values())


def test_older_files_are_refused_with_a_clear_message():
    for name, as_family in (("legacy/abusua2ga4gh-0.2_ga4gh.json", False),
                            ("legacy/abusua2ga4gh-0.2_family.json", True),
                            ("legacy/abusua2ga4gh-0.2_family_no-names.json", True),   # 0.2's usual Family
                            ("legacy/studio2ga4gh-0.3_ga4gh.json", False)):
        with pytest.raises(LegacyFileError) as err:
            if as_family:
                to_abusua_session(family=load(name))
            else:
                to_abusua_session(ga4gh_pedigree=load(name))
        assert "pedigree-ga4gh upgrade" in str(err.value)


def test_the_draft_of_version_1_is_refused():
    draft = {"id": "FAM1", "individuals": [{"id": "MOTHER", "sexAssignedAtBirth": "ASSIGNED_FEMALE"},
                                           {"id": "CHILD", "eggParentId": "MOTHER"}],
             "relationships": [{"individual": "MOTHER", "relative": "CHILD",
                                "biologicalRelationship": [{"id": "KIN:027", "label": "isBiologicalMotherOf"}]}]}
    with pytest.raises(LegacyFileError) as err:
        to_session(draft)
    assert "draft of version 1" in str(err.value) and "upgrade" not in str(err.value)


def test_requires_an_input():
    with pytest.raises(ValueError):
        to_abusua_session()


def test_ids_never_clash():
    b = SessionBuilder()
    b.reserve(["II-3", "i1", "i4", "III-1"])
    assert b.id_map == {"i1": "i1", "i4": "i4", "II-3": "i5", "III-1": "i6"}
    assert b.abusua_id_for("IV-1") == "i7"


# -- the command line ------------------------------------------------------------------------------------------

def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main([str(a) for a in argv])
    return code, out.getvalue(), err.getvalue()


def test_command_line(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, out, err = run(DATA / "asante.ga4gh-pedigree.json")
    assert code == 0, err
    assert json.loads((tmp_path / "asante.json").read_text(encoding="utf-8"))["fam"] == "ASANTE"
    code, out, err = run(DATA / "asante.family.json", "-o", tmp_path / "sub" / "fam.json")
    assert code == 0 and (tmp_path / "sub" / "fam.json").exists()
    # version 0.3's options, both files at once
    code, out, err = run("--pedigree", DATA / "mensah.ga4gh-pedigree.json", "--family", DATA / "mensah.family.json",
                         "--stdout")
    assert code == 0 and json.loads(out)["people"]["i8"]["socialMotherId"] == "i9"
    # an old file is refused
    code, out, err = run(DATA / "legacy" / "abusua2ga4gh-0.2_ga4gh.json", "-o", tmp_path / "x.json")
    assert code == 2 and "pedigree-ga4gh upgrade" in err and not (tmp_path / "x.json").exists()
    # the session never replaces its input
    src = tmp_path / "boateng.json"
    src.write_text((DATA / "boateng.ga4gh-pedigree.json").read_text(encoding="utf-8"), encoding="utf-8")
    code, out, err = run(src)
    assert code == 2 and "is the file being read" in err and json.loads(src.read_text(encoding="utf-8"))["individuals"]
    # nor, unasked, a session already there: asante.json was written above
    before = (tmp_path / "asante.json").read_text(encoding="utf-8")
    code, out, err = run(DATA / "asante.family.json")
    assert code == 2 and "already exists" in err and (tmp_path / "asante.json").read_text(encoding="utf-8") == before
    code, out, err = run(DATA / "asante.family.json", "--force")
    assert code == 0
    code, out, err = run()
    assert code == 2

