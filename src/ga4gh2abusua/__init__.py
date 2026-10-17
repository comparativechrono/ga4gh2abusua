"""
ga4gh2abusua \u2014 reconstruct an Abusua Pedigree Studio session (.json) from GA4GH
inputs: a GA4GH Pedigree Standard message and/or a Phenopackets v2 Family.

This is the inverse of ``abusua2ga4gh``.

Quick start
-----------
>>> import json
>>> from ga4gh2abusua import to_abusua_session
>>> family = json.load(open("fam.family.json"))
>>> pedigree = json.load(open("fam.ga4gh-pedigree.json"))
>>> session, warns = to_abusua_session(ga4gh_pedigree=pedigree, family=family)
>>> json.dump(session, open("fam.json", "w"), indent=2)

Or from the command line::

    ga4gh2abusua --family fam.family.json --pedigree fam.ga4gh-pedigree.json -o fam.json
"""
from __future__ import annotations

from .convert import (
    to_abusua_session,
    apply_ga4gh_pedigree,
    apply_family,
)
from .session import SessionBuilder, BuildPerson

__all__ = [
    "to_abusua_session",
    "apply_ga4gh_pedigree",
    "apply_family",
    "SessionBuilder",
    "BuildPerson",
]

__version__ = "0.1.0"
