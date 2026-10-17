# Changelog

## 0.4.0

ga4gh2abusua now reads GA4GH files through
[pedigree-ga4gh](https://github.com/comparativechrono/pedigree-ga4gh), the one
GA4GH implementation shared by the lab's pedigree tools, and depends on it.
Version 0.3 read the files abusua2ga4gh 0.2 wrote, which were not in the
standard's form, and several other non-standard forms besides. It could not
read the standard's own form properly: conditions sit beside `subject` in a
Phenopacket, not inside it, so a GA4GH Pedigree in the standard form came back
without any.

- **One form is read.** GA4GH Pedigrees in the Phenopackets form of the
  published standard and Phenopackets v2 Families, in either JSON spelling.
  Files in the older forms (abusua2ga4gh up to 0.2, studio2ga4gh up to 0.3) are
  refused with a message saying to upgrade them first, once, with
  `pedigree-ga4gh upgrade`; the draft of version 1 of the standard is refused
  with a message saying it is not yet approved.
- **Social and foster parents** are read from their own KIN terms:
  `KIN:021` *isFosterParentOf* (and `KIN:022` *isAdoptiveParentOf*) give a
  social parent of a child fostered in, and `KIN:020` *isParentFigureOf* a
  social father or another social parent. 0.3 read only `KIN:022`, as
  abusua2ga4gh 0.2 wrote all of them.
- **The narrative is read** for what abusua2ga4gh 0.3 writes there:
  - reported paternity, and a recorded father whose paternity is unknown;
  - fostering;
  - carriers;
  - conditions without an ontology term;
  - who is affected with no condition recorded, and who is unaffected.

  So is what `pedigree-ga4gh upgrade` keeps of an abusua2ga4gh 0.2 file. A
  session converted to GA4GH and back now comes back as it was, apart from
  names, and converting it again gives the same files.
- **Carriers** are no longer read from the phenotypic feature `HP:0032500`.
  That is the HPO's *Exacerbated by tobacco use*, which abusua2ga4gh 0.2 used
  by mistake. They come from the narrative instead.
- **Conditions keep their terms.** Each one is written with its ontology id in
  brackets (`sickle cell disease [MONDO:0011382]`), which abusua2ga4gh 0.3
  reads, so a round trip gives every condition the same term. 0.3 kept only
  the label.
- **More relationships are read.** Biological parents of unknown sex are
  placed by pedigree-ga4gh, and so are donors and the parents of twins given
  for only one twin. Partners of every kind become unions. Relationships
  Abusua has no place for are listed in the notes instead of being dropped
  without a word.
- **Ids no longer clash.** 0.3 kept Abusua ids (`i3`) and numbered the rest
  from `i1`, so a file mixing the two could give two people the same id. Ids
  are now reserved first. Someone renumbered keeps their GA4GH id in their
  notes ("GA4GH id: II-3").
- **The command takes the file as its argument** (`ga4gh2abusua FILE -o
  OUT`), whichever kind it is. `--pedigree` and `--family` still work. The
  session never replaces its input: 0.3 wrote `fam.json` into the current
  folder for an input named `fam.json`.
- **Names cannot come back.** Phenopackets have no field for a name, and
  abusua2ga4gh 0.3 never writes one. 0.3 restored the names that
  abusua2ga4gh 0.2 put in `subject` against the schema; `pedigree-ga4gh
  upgrade` removes them.
- `--version` and `python -m ga4gh2abusua` are new. Python 3.9 or later is
  needed, as for pedigree-ga4gh.
- `__version__` now matches the release (0.3.0 reported 0.1.0). There are
  tests on fictional families, including the round trip with abusua2ga4gh, run
  on Python 3.9 to 3.14.

## 0.3.0

Released on PyPI on 1 June 2026.

## 0.2.0

Released on PyPI on 1 June 2026.

## 0.1.0

Released on PyPI on 31 May 2026.
