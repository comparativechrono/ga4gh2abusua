# ga4gh2abusua

Reconstruct an **Abusua Pedigree Studio** session file (`.json`) from GA4GH inputs:

- a **GA4GH Pedigree Standard** message (KIN-relationship graph), and/or
- a **Phenopackets v2 Family** (proband + relatives + native PED-style pedigree).

This is the inverse of [`abusua2ga4gh`](../abusua2ga4gh). Pure Python, no runtime dependencies, Python ≥ 3.8.

---

## What it does

Given either or both GA4GH artefacts, it rebuilds an Abusua session that the tool can open directly — restoring family topology, sex, affected status, conditions, carrier state, deceased status, and the proband, and mapping parentage back into Abusua's dual-layer model.

| Source field | → | Abusua field |
|---|---|---|
| `KIN:027 isBiologicalMotherOf` | → | `bioMotherId` |
| `KIN:028 isBiologicalFatherOf` | → | `bioFatherId` (+ `paternity` = `reported` if the edge says so, else `confirmed`) |
| `KIN:022 isAdoptiveParentOf` | → | `socialMotherId`/`socialFatherId` + `fosteredIn` |
| Family native pedigree `maternalId`/`paternalId` (`0` = none) | → | `bioMotherId`/`bioFatherId` (a `0` father with a known mother ⇒ `paternity` = `unknown`) |
| native pedigree `sex`, `affectedStatus` | → | `sex`, `affected` |
| phenopacket `diseases[].term.label` | → | `condition` (free text) |
| phenopacket `phenotypicFeatures[].type.label` (non-carrier) | → | `condition` (free text) |
| phenopacket feature `HP:0032500` | → | `carrier` token in `condition` |
| subject `vital_status = DECEASED` | → | `deceased` |
| `Family.proband` | → | `proband` |
| `Family.consanguinousParents = true` | → | a note on the proband |

When **both** inputs are supplied, the Family is applied first (topology, sex, affected status, clinical detail) and the GA4GH Pedigree is layered on to refine the biological-vs-social edge distinction and paternity certainty.

---

## Install

```bash
pip install -e .
```

## Command line

```bash
# Most complete: both inputs
ga4gh2abusua --family fam.family.json --pedigree fam.ga4gh-pedigree.json -o fam.json

# From a Family alone
ga4gh2abusua --family fam.family.json -o fam.json

# From a GA4GH Pedigree alone, to stdout
ga4gh2abusua --pedigree fam.ga4gh-pedigree.json --stdout
```

## Python API

```python
import json
from ga4gh2abusua import to_abusua_session

family   = json.load(open("fam.family.json"))
pedigree = json.load(open("fam.ga4gh-pedigree.json"))

session, warnings = to_abusua_session(ga4gh_pedigree=pedigree, family=family)
json.dump(session, open("fam.json", "w"), indent=2)
for w in warnings:
    print("note:", w)
```

The reconstructed session opens directly in Abusua Pedigree Studio (load via the **Open / Load** button).

---

## Round-trip fidelity and limitations

The conversion preserves the genetically and clinically meaningful content. We verified that `Abusua → abusua2ga4gh → ga4gh2abusua` reproduces, for the bundled examples, the same number of individuals and unions, the same affected/carrier/deceased/proband sets, the same unknown-paternity cases, names (when exported), and a session that loads, lays out, renders, and compiles to a valid PED in the tool.

**Names.** Phenopackets has no dedicated name field (the schema is designed to be de-identifiable), so names are PII and are only present in GA4GH output when it was produced with `--include-names`. When present, `ga4gh2abusua` restores them. Two practical points:

- For names to come back for **every** individual, convert from the **GA4GH Pedigree** (its `individuals` cover everyone), or from both inputs. A Phenopackets **Family** only carries names for members who have a phenopacket (the proband and relatives *with findings*), so an unaffected relative's name is absent in a Family-only conversion.
- This converter reads the name from a subject's `name` field first, then falls back to `label` or the first `alternate_ids` entry, matching how `abusua2ga4gh` writes them.

**Input compatibility.** GA4GH Pedigree files from different tools vary in shape, and this converter accepts the common variants: individual fields may be nested under a `subject` object or placed directly on the individual (a flat `{"id", "name", "sex", "affected"}` form); affected status may be a `subject.diseases` list, an individual-level `affected` boolean, or an `affectedStatus` enum; and relationship endpoints may use the keys `individual`/`relative` or `individual_id`/`relative_id`. Names are read from whichever of `name`, `label`, or `alternate_ids` is present.

Some information is **not** representable in the GA4GH artefacts and therefore cannot survive a round-trip:

- **Abusua-specific lineage overrides (`abusuaManual`, `ntoroManual`).** Neither standard has a place for a manually pinned matriclan or ntoro, so these are not exported by `abusua2ga4gh` and cannot be restored here. On load, Abusua re-derives clan from the maternal chain, so a *derived* clan is unaffected; only a founder's *manually set* clan is lost.
- **The `fosteredIn` flag when the foster parents are unknown.** The native PED pedigree correctly represents an unknown father as `paternalId = 0` (so `paternity = unknown` is restored), but the boolean "this child was fostered in" is only recoverable when the source carried an explicit `KIN:022` adoptive edge in the GA4GH Pedigree. A fostered child with *unrecorded* social parents will come back with the correct biology but without the `fosteredIn` flag set.
- **Layout coordinates and free-text notes** are not part of the GA4GH artefacts; the tool re-lays-out on load, and notes are regenerated only where this converter adds them (e.g. the consanguinity note).
- **Condition ontology ids** are reduced to their free-text labels, matching how Abusua stores conditions; the MONDO/HPO ids in the source are not retained in the session.

All such losses are inherent to what the standards model, not to this converter, and the converter reports the notable ones in its warnings.

## Tests

```bash
pytest
```

The suite includes a round-trip from the original Abusua example sessions through the forward GA4GH outputs and back.

## Layout

```
src/ga4gh2abusua/
  convert.py    # GA4GH Pedigree / Phenopackets Family -> Abusua session
  session.py    # internal builder + Abusua .json serialisation
  cli.py        # command-line interface
examples/       # a sample family + ga4gh-pedigree pair
tests/          # pytest suite (incl. round-trip)
```

## References

- GA4GH Pedigree Standard — https://pedigree.readthedocs.io/
- GA4GH Phenopacket Schema v2 (Family) — https://phenopacket-schema.readthedocs.io/

## License

MIT.
