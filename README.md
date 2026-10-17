# ga4gh2abusua

Rebuild an **Abusua Pedigree Studio** session (`.json`) from a **GA4GH
Pedigree** or a **Phenopackets v2 Family**. It is the reverse of
[abusua2ga4gh](https://github.com/comparativechrono/abusua2ga4gh): a session
converted to GA4GH and back keeps its family, its biological and social
parentage, and its conditions with their ontology terms.

Files are read through [pedigree-ga4gh](https://github.com/comparativechrono/pedigree-ga4gh),
the one GA4GH implementation that the lab's pedigree tools share, so
ga4gh2abusua reads exactly the standard form that abusua2ga4gh, studio2ga4gh
and the phenopacket toolkit write, in either JSON spelling (`indexPatients` or
`index_patients`).

## Installation

```bash
pip install ga4gh2abusua
```

It needs Python 3.9 or later and installs pedigree-ga4gh with it.

## Usage

```bash
ga4gh2abusua asante.ga4gh-pedigree.json                  # writes asante.json
ga4gh2abusua asante.family.json -o asante.json
ga4gh2abusua --pedigree asante.ga4gh-pedigree.json --family asante.family.json -o asante.json
ga4gh2abusua asante.ga4gh-pedigree.json --stdout
```

Give either file. The GA4GH Pedigree holds more than the Family (social and
foster parents, couples without children, carriers and the like, in its
narrative), so if you have only one, give the Pedigree. Given both, as with
version 0.3's `--pedigree` and `--family`, the Pedigree is read first and the
Family fills in anything it lacks.

The session is written to the current folder under the input's name, without
`.ga4gh-pedigree.json` or `.family.json`. It never replaces the input: if the
names would be the same, it is written as `<name>.abusua.json` instead. Open it
in Abusua Pedigree Studio with **Open / Load**.

## What the files become

| In the GA4GH files | In the Abusua session |
|---|---|
| `KIN:027` isBiologicalMotherOf (or an ovum donor) | `bioMotherId` |
| `KIN:028` isBiologicalFatherOf (or a sperm donor) | `bioFatherId`, paternity `confirmed`, or `reported` if the narrative says so |
| `KIN:003` isBiologicalParentOf | mother or father, by the parent's sex |
| `KIN:020` isParentFigureOf, for a social father | `bioFatherId`, paternity `social-only` (the narrative says which) |
| `KIN:021` isFosterParentOf, `KIN:022` isAdoptiveParentOf | `socialMotherId` / `socialFatherId`, and `fosteredIn` |
| other parent figures and step-parents | `socialMotherId` / `socialFatherId` |
| partners of every kind, and every couple with a child together | a union |
| twins and siblings | the same parents, if only one of them has them recorded |
| `indexPatients`, or the Family's proband | `proband` |
| vital status `DECEASED` | `deceased` |
| diseases and phenotypic features | `condition`, each written with its term: `sickle cell disease [MONDO:0011382]` |
| an excluded disease or feature | the condition, on someone marked unaffected |
| the Family's PED-style pedigree | parents, sex, and affected or unaffected |

The ontology id written after each condition is what lets abusua2ga4gh give it
the same term when the session is converted again.

abusua2ga4gh says in the narrative what the GA4GH structure cannot, in fixed
sentences that ga4gh2abusua reads back: who is a carrier, who has a condition
without an ontology term, who is affected with no condition recorded or
unaffected, who is recorded as a father although paternity is unknown, and who
was fostered in. ga4gh2abusua also reads the notes that `pedigree-ga4gh
upgrade` keeps of an abusua2ga4gh 0.2 file (reported paternity, social and
foster parents).

A person whose id in the file is not an Abusua id (`i1`, `i2` …), such as a
pedigree number from studio2ga4gh, is given the next free one, and their own id
is kept in their notes ("GA4GH id: II-3"). Relationships Abusua has no place
for, such as a gestational carrier, a mitochondrial donor or cousins given on
their own, are listed in the notes the command prints.

## What cannot come back

- **Names.** Phenopackets have no field for a name, so the GA4GH files have
  none to give back.
- **The manually set abusua and ntoro, layout and notes**, which neither
  standard has a place for. Abusua works out the abusua from the mother's line
  again when the session is opened, so only a founder's manually set one is
  lost.
- **A condition's own wording.** A matched condition comes back with its
  term's label: "Sickle cell anaemia (HbSS)" becomes `sickle cell disease
  [MONDO:0011382]`.
- **From a Family alone**, less again: a Family has no social or foster
  parents, couples without children or narrative, and a person without their
  own Phenopacket (an unaffected relative) has no vital status.

## Older files

Files written by abusua2ga4gh up to 0.2 or studio2ga4gh up to 0.3 are not in
the standard's form. ga4gh2abusua recognises them and asks you to upgrade them
first, once, with `pedigree-ga4gh upgrade FILE -o NEW.json`, which lists every
change it makes. The upgrade removes names, as the standard has no place for
them; if you still have the session, it already has them. Files in the form of
the draft of version 1 of the GA4GH Pedigree Standard, which is not yet
approved, are recognised and refused with a message saying so.

## In Python

```python
import json
from ga4gh2abusua import to_abusua_session

with open("asante.ga4gh-pedigree.json") as fh:
    pedigree = json.load(fh)
with open("asante.family.json") as fh:
    family = json.load(fh)

session, notes = to_abusua_session(ga4gh_pedigree=pedigree, family=family)   # or either one alone
with open("asante.json", "w") as fh:
    json.dump(session, fh, indent=2)
```

`to_session(doc)` takes one document of either kind, and
`ga4gh2abusua.LegacyFileError` is raised for a file in an older form.

## Development

```bash
pip install -e ".[test]"
pytest
```

The tests use fictional families in `tests/data`. The round-trip test converts
each session back with abusua2ga4gh, which the `test` extra installs.

## References

- GA4GH Pedigree Standard: https://pedigree.readthedocs.io/
- GA4GH Phenopacket Schema v2 (Family): https://phenopacket-schema.readthedocs.io/

## Licence

MIT
